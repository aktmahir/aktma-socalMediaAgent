from collections import defaultdict
from datetime import datetime, timezone
import importlib
import json
import logging
import os
import sqlite3
import threading
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any, Dict, Optional, Tuple


class RequestMetrics:
    DURATION_BUCKETS = (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0)
    ERROR_RETENTION_LIMIT = 1000

    def __init__(self, database_path: Optional[Path] = None) -> None:
        self._lock = threading.Lock()
        self._request_counts: Dict[Tuple[str, int], int] = defaultdict(int)
        self._duration_counts: Dict[Tuple[str, int], int] = defaultdict(int)
        self._duration_sums: Dict[Tuple[str, int], float] = defaultdict(float)
        self._duration_buckets: Dict[Tuple[str, int, float], int] = defaultdict(int)
        self.database_path = Path(database_path) if database_path is not None else None
        if self.database_path is not None:
            self.database_path.parent.mkdir(parents=True, exist_ok=True)
            self._initialize_database()

    def _connect(self) -> sqlite3.Connection:
        if self.database_path is None:
            raise RuntimeError("Persistent observability storage is not configured.")
        connection = sqlite3.connect(str(self.database_path), timeout=10)
        connection.execute("PRAGMA busy_timeout = 10000")
        return connection

    def _initialize_database(self) -> None:
        bucket_columns = ", ".join(
            f"bucket_{index} INTEGER NOT NULL DEFAULT 0"
            for index in range(len(self.DURATION_BUCKETS))
        )
        connection = self._connect()
        try:
            connection.execute(
                f"""
                CREATE TABLE IF NOT EXISTS http_request_metrics (
                    method TEXT NOT NULL,
                    status_code INTEGER NOT NULL,
                    request_count INTEGER NOT NULL DEFAULT 0,
                    duration_sum REAL NOT NULL DEFAULT 0,
                    {bucket_columns},
                    PRIMARY KEY (method, status_code)
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS application_errors (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    occurred_at TEXT NOT NULL,
                    request_id TEXT NOT NULL,
                    method TEXT NOT NULL,
                    path TEXT NOT NULL,
                    error_type TEXT NOT NULL
                )
                """
            )
            connection.commit()
        finally:
            connection.close()

    def check_storage(self) -> bool:
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute("SELECT 1 FROM http_request_metrics LIMIT 1").fetchone()
            connection.rollback()
            return True
        finally:
            connection.close()

    def observe_request(self, method: str, status_code: int, duration_seconds: float) -> None:
        tracked_methods = {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"}
        method_label = method if method in tracked_methods else "OTHER"
        key = (method_label, status_code)
        observed_buckets = [
            duration_seconds <= bucket for bucket in self.DURATION_BUCKETS
        ]
        with self._lock:
            self._request_counts[key] += 1
            self._duration_counts[key] += 1
            self._duration_sums[key] += duration_seconds
            for bucket, observed in zip(self.DURATION_BUCKETS, observed_buckets):
                if observed:
                    self._duration_buckets[(method_label, status_code, bucket)] += 1
        if self.database_path is not None:
            self._persist_request(method_label, status_code, duration_seconds, observed_buckets)

    def _persist_request(
        self,
        method: str,
        status_code: int,
        duration_seconds: float,
        observed_buckets: list[bool],
    ) -> None:
        bucket_columns = [f"bucket_{index}" for index in range(len(self.DURATION_BUCKETS))]
        columns = ["method", "status_code", "request_count", "duration_sum", *bucket_columns]
        placeholders = ", ".join("?" for _ in columns)
        updates = [
            "request_count = http_request_metrics.request_count + 1",
            "duration_sum = http_request_metrics.duration_sum + excluded.duration_sum",
        ]
        updates.extend(
            f"{column} = http_request_metrics.{column} + excluded.{column}"
            for column in bucket_columns
        )
        values = [
            method,
            status_code,
            1,
            duration_seconds,
            *(int(observed) for observed in observed_buckets),
        ]
        connection = self._connect()
        try:
            connection.execute(
                f"""
                INSERT INTO http_request_metrics ({", ".join(columns)})
                VALUES ({placeholders})
                ON CONFLICT (method, status_code) DO UPDATE SET {", ".join(updates)}
                """,
                values,
            )
            connection.commit()
        finally:
            connection.close()

    def report_error(self, request_id: str, method: str, path: str, error_type: str) -> None:
        if self.database_path is None:
            return
        connection = self._connect()
        try:
            connection.execute(
                """
                INSERT INTO application_errors (occurred_at, request_id, method, path, error_type)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    datetime.now(timezone.utc).isoformat(),
                    request_id,
                    method,
                    path,
                    error_type,
                ),
            )
            connection.execute(
                """
                DELETE FROM application_errors
                WHERE id NOT IN (
                    SELECT id FROM application_errors ORDER BY id DESC LIMIT ?
                )
                """,
                (self.ERROR_RETENTION_LIMIT,),
            )
            connection.commit()
        finally:
            connection.close()

    def render_prometheus(self) -> str:
        lines = [
            "# HELP social_media_agent_http_requests_total Total HTTP requests.",
            "# TYPE social_media_agent_http_requests_total counter",
        ]
        if self.database_path is not None:
            request_counts, duration_counts, duration_sums, duration_buckets = (
                self._load_persisted_metrics()
            )
        else:
            with self._lock:
                request_counts = dict(self._request_counts)
                duration_counts = dict(self._duration_counts)
                duration_sums = dict(self._duration_sums)
                duration_buckets = dict(self._duration_buckets)

        for (method, status_code), count in sorted(request_counts.items()):
            labels = f'method="{method}",status_code="{status_code}"'
            lines.append(f"social_media_agent_http_requests_total{{{labels}}} {count}")

        lines.extend(
            (
                "# HELP social_media_agent_http_request_duration_seconds HTTP request duration.",
                "# TYPE social_media_agent_http_request_duration_seconds histogram",
            )
        )
        for method, status_code in sorted(duration_counts):
            labels = f'method="{method}",status_code="{status_code}"'
            for bucket in self.DURATION_BUCKETS:
                bucket_labels = f'method="{method}",status_code="{status_code}",le="{bucket:g}"'
                count = duration_buckets.get((method, status_code, bucket), 0)
                lines.append(
                    f"social_media_agent_http_request_duration_seconds_bucket{{{bucket_labels}}} {count}"
                )
            infinite_labels = f'method="{method}",status_code="{status_code}",le="+Inf"'
            lines.append(
                f"social_media_agent_http_request_duration_seconds_bucket{{{infinite_labels}}} "
                f"{duration_counts[(method, status_code)]}"
            )
            lines.append(
                f"social_media_agent_http_request_duration_seconds_sum{{{labels}}} "
                f"{duration_sums[(method, status_code)]:.6f}"
            )
            lines.append(
                f"social_media_agent_http_request_duration_seconds_count{{{labels}}} "
                f"{duration_counts[(method, status_code)]}"
            )
        return "\n".join(lines) + "\n"

    def _load_persisted_metrics(self):
        connection = self._connect()
        try:
            rows = connection.execute(
                "SELECT * FROM http_request_metrics ORDER BY method, status_code"
            ).fetchall()
        finally:
            connection.close()
        request_counts = {}
        duration_counts = {}
        duration_sums = {}
        duration_buckets = {}
        for row in rows:
            method = str(row[0])
            status_code = int(row[1])
            count = int(row[2])
            key = (method, status_code)
            request_counts[key] = count
            duration_counts[key] = count
            duration_sums[key] = float(row[3])
            for index, bucket in enumerate(self.DURATION_BUCKETS):
                duration_buckets[(method, status_code, bucket)] = int(row[4 + index])
        return request_counts, duration_counts, duration_sums, duration_buckets


def configure_logging() -> None:
    try:
        max_bytes = int(os.environ.get("APP_LOG_MAX_BYTES", str(10 * 1024 * 1024)))
        backup_count = int(os.environ.get("APP_LOG_BACKUP_COUNT", "3"))
    except ValueError as error:
        raise ValueError(
            "APP_LOG_MAX_BYTES and APP_LOG_BACKUP_COUNT must be integers."
        ) from error
    if max_bytes <= 0:
        raise ValueError("APP_LOG_MAX_BYTES must be a positive integer.")
    if backup_count < 0:
        raise ValueError("APP_LOG_BACKUP_COUNT must be a non-negative integer.")

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    log_file = os.environ.get("APP_LOG_FILE", "").strip()
    if not log_file:
        return

    log_path = Path(log_file).expanduser().resolve()
    if any(
        isinstance(handler, RotatingFileHandler)
        and Path(handler.baseFilename) == log_path
        for handler in root_logger.handlers
    ):
        return
    log_path.parent.mkdir(parents=True, exist_ok=True)
    file_handler = RotatingFileHandler(
        log_path,
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding="utf-8",
    )
    file_handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
    )
    root_logger.addHandler(file_handler)


def log_event(logger: logging.Logger, event: str, **fields: Any) -> None:
    logger.info(
        "%s",
        json.dumps({"event": event, **fields}, sort_keys=True, separators=(",", ":")),
    )


def log_exception_event(logger: logging.Logger, event: str, **fields: Any) -> None:
    logger.exception(
        "%s",
        json.dumps({"event": event, **fields}, sort_keys=True, separators=(",", ":")),
    )


def scrub_sentry_event(event: Dict[str, Any], _hint: Dict[str, Any]) -> Dict[str, Any]:
    _ = _hint
    safe_event_fields = {
        "event_id",
        "timestamp",
        "platform",
        "level",
        "environment",
        "sdk",
        "tags",
        "exception",
    }
    for field in tuple(event):
        if field not in safe_event_fields:
            event.pop(field)

    tags = event.get("tags")
    if isinstance(tags, dict):
        event["tags"] = {
            "request_id": tags["request_id"]
        } if "request_id" in tags else {}
    else:
        event.pop("tags", None)

    exception = event.get("exception")
    if isinstance(exception, dict):
        values = exception.get("values")
        if isinstance(values, list):
            for value in values:
                if not isinstance(value, dict):
                    continue
                exception_type = value.get("type")
                sanitized_value: Dict[str, Any] = {
                    "type": exception_type or "Exception",
                    "value": exception_type or "Unhandled exception",
                }
                stacktrace = value.get("stacktrace")
                if isinstance(stacktrace, dict):
                    frames = stacktrace.get("frames")
                    if isinstance(frames, list):
                        sanitized_frames = []
                        for frame in frames:
                            if not isinstance(frame, dict):
                                continue
                            sanitized_frame = {
                                key: frame[key]
                                for key in ("function", "lineno", "in_app")
                                if key in frame
                            }
                            filename = frame.get("filename")
                            if isinstance(filename, str):
                                sanitized_frame["filename"] = filename.replace(
                                    "\\", "/"
                                ).rsplit("/", 1)[-1]
                            sanitized_frames.append(sanitized_frame)
                        sanitized_value["stacktrace"] = {"frames": sanitized_frames}
                value.clear()
                value.update(sanitized_value)
    return event


def configure_sentry(dsn: str, environment: str) -> bool:
    if not dsn:
        return False
    try:
        sentry_sdk = importlib.import_module("sentry_sdk")
        flask_integration = importlib.import_module("sentry_sdk.integrations.flask")
        logging_integration = importlib.import_module("sentry_sdk.integrations.logging")
    except ImportError as error:
        raise RuntimeError(
            "Sentry reporting is enabled, but sentry-sdk is not installed. "
            'Install the optional dependency with `pip install ".[monitoring]"`.'
        ) from error

    sentry_sdk.init(
        dsn=dsn,
        environment=environment,
        integrations=[
            flask_integration.FlaskIntegration(),
            logging_integration.LoggingIntegration(level=None, event_level=None),
        ],
        send_default_pii=False,
        include_source_context=False,
        include_local_variables=False,
        before_send=scrub_sentry_event,
    )
    return True


def capture_sentry_exception(error: Exception, request_id: str) -> None:
    sentry_sdk = importlib.import_module("sentry_sdk")

    with sentry_sdk.new_scope() as scope:
        scope.set_tag("request_id", request_id)
        sentry_sdk.capture_exception(error)
