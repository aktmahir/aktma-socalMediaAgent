from collections import defaultdict
import json
import logging
import threading
from typing import Any, Dict, Tuple


class RequestMetrics:
    DURATION_BUCKETS = (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0)

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._request_counts: Dict[Tuple[str, int], int] = defaultdict(int)
        self._duration_counts: Dict[Tuple[str, int], int] = defaultdict(int)
        self._duration_sums: Dict[Tuple[str, int], float] = defaultdict(float)
        self._duration_buckets: Dict[Tuple[str, int, float], int] = defaultdict(int)

    def observe_request(self, method: str, status_code: int, duration_seconds: float) -> None:
        tracked_methods = {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"}
        method_label = method if method in tracked_methods else "OTHER"
        key = (method_label, status_code)
        with self._lock:
            self._request_counts[key] += 1
            self._duration_counts[key] += 1
            self._duration_sums[key] += duration_seconds
            for bucket in self.DURATION_BUCKETS:
                if duration_seconds <= bucket:
                    self._duration_buckets[(method_label, status_code, bucket)] += 1

    def render_prometheus(self) -> str:
        lines = [
            "# HELP social_media_agent_http_requests_total Total HTTP requests.",
            "# TYPE social_media_agent_http_requests_total counter",
        ]
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


def configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )


def log_event(logger: logging.Logger, event: str, **fields: Any) -> None:
    logger.info(
        "%s",
        json.dumps({"event": event, **fields}, sort_keys=True, separators=(",", ":")),
    )
