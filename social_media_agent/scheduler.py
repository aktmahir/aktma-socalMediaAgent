import json
import logging
import sqlite3
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from .generator import SocialMediaPostGenerator

logger = logging.getLogger(__name__)


def parse_interval(interval: str) -> int:
    if not interval or not interval.strip():
        return 0

    value = interval.strip()
    unit = value[-1].lower()
    try:
        amount = int(value[:-1])
    except ValueError as exc:
        raise ValueError("Interval must be a positive integer followed by s, m, h, or d.") from exc

    if amount <= 0:
        raise ValueError("Interval must be a positive integer value.")

    multipliers = {"s": 1, "m": 60, "h": 3600, "d": 86400}
    try:
        return amount * multipliers[unit]
    except KeyError as exc:
        raise ValueError("Interval must end with s, m, h, or d.") from exc


def parse_count(value: str) -> int:
    try:
        count = int(value)
    except ValueError as exc:
        raise ValueError("Scheduled post count must be a non-negative integer.") from exc

    if count < 0:
        raise ValueError("Scheduled post count must be a non-negative integer.")
    return count


class PeriodicPostScheduler:
    WORKER_LEASE_SECONDS = 120
    WORKER_HEARTBEAT_SECONDS = 20
    MAX_GENERATION_ATTEMPTS = 3
    RETRY_BASE_DELAY_SECONDS = 1

    def __init__(
        self,
        generator: SocialMediaPostGenerator,
        output_dir: Optional[str] = None,
        database_path: Optional[str] = None,
    ) -> None:
        self.generator = generator
        self.output_dir = Path(output_dir or Path.cwd() / "scheduled_posts")
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.database_path = Path(database_path) if database_path else self.output_dir / "scheduler.sqlite3"
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._supervisor_lock = threading.Lock()
        self._supervisor_workers: Dict[str, threading.Thread] = {}
        self._initialize_database()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(str(self.database_path), timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout = 10000")
        return connection

    def _initialize_database(self) -> None:
        connection = self._connect()
        try:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS scheduled_jobs (
                    id TEXT PRIMARY KEY,
                    post_config TEXT NOT NULL,
                    interval_seconds INTEGER NOT NULL,
                    target_count INTEGER NOT NULL,
                    completed_count INTEGER NOT NULL DEFAULT 0,
                    generation_attempts INTEGER NOT NULL DEFAULT 0,
                    status TEXT NOT NULL,
                    output_dir TEXT NOT NULL,
                    next_run_at REAL NOT NULL,
                    last_error TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS scheduled_job_workers (
                    job_id TEXT PRIMARY KEY,
                    owner_token TEXT NOT NULL,
                    lease_expires_at REAL NOT NULL,
                    FOREIGN KEY (job_id) REFERENCES scheduled_jobs (id) ON DELETE CASCADE
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS scheduled_job_outputs (
                    job_id TEXT NOT NULL,
                    iteration INTEGER NOT NULL,
                    payload_json TEXT NOT NULL,
                    output_path TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY (job_id, iteration),
                    FOREIGN KEY (job_id) REFERENCES scheduled_jobs (id) ON DELETE CASCADE
                )
                """
            )
            job_columns = {
                str(row["name"])
                for row in connection.execute("PRAGMA table_info(scheduled_jobs)").fetchall()
            }
            if "generation_attempts" not in job_columns:
                connection.execute(
                    """
                    ALTER TABLE scheduled_jobs
                    ADD COLUMN generation_attempts INTEGER NOT NULL DEFAULT 0
                    """
                )
            connection.commit()
        finally:
            connection.close()

    def _get_job(self, job_id: str) -> Optional[Dict[str, object]]:
        connection = self._connect()
        try:
            row = connection.execute(
                "SELECT * FROM scheduled_jobs WHERE id = ?",
                (job_id,),
            ).fetchone()
            return dict(row) if row is not None else None
        finally:
            connection.close()

    def _set_job_status(self, job_id: str, status: str, *, next_run_now: bool = False) -> None:
        connection = self._connect()
        try:
            now = datetime.now().isoformat()
            if next_run_now:
                cursor = connection.execute(
                    """
                    UPDATE scheduled_jobs
                    SET status = ?, next_run_at = ?, updated_at = ?, last_error = NULL
                    WHERE id = ?
                    """,
                    (status, time.time(), now, job_id),
                )
            else:
                cursor = connection.execute(
                    """
                    UPDATE scheduled_jobs
                    SET status = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (status, now, job_id),
                )
            if cursor.rowcount == 0:
                raise ValueError(f"Scheduled job not found: {job_id}")
            connection.commit()
        finally:
            connection.close()

    def _create_job(self, post_config: Dict[str, object], interval_seconds: int, count: int) -> str:
        job_id = uuid.uuid4().hex
        now = datetime.now().isoformat()
        connection = self._connect()
        try:
            connection.execute(
                """
                INSERT INTO scheduled_jobs (
                    id, post_config, interval_seconds, target_count, completed_count,
                    status, output_dir, next_run_at, created_at, updated_at
                ) VALUES (?, ?, ?, ?, 0, 'running', ?, ?, ?, ?)
                """,
                (
                    job_id,
                    json.dumps(post_config, ensure_ascii=False),
                    interval_seconds,
                    count,
                    str(self.output_dir),
                    time.time(),
                    now,
                    now,
                ),
            )
            connection.commit()
            return job_id
        finally:
            connection.close()

    def list_jobs(self) -> List[Dict[str, object]]:
        connection = self._connect()
        try:
            rows = connection.execute(
                "SELECT * FROM scheduled_jobs ORDER BY created_at DESC"
            ).fetchall()
            jobs = []
            for row in rows:
                job = dict(row)
                job["post_config"] = json.loads(str(job["post_config"]))
                jobs.append(job)
            return jobs
        finally:
            connection.close()

    def pause_job(self, job_id: str) -> None:
        job = self._get_job(job_id)
        if job is None:
            raise ValueError(f"Scheduled job not found: {job_id}")
        if job["status"] != "running":
            raise ValueError(f"Cannot pause a job with status '{job['status']}'.")
        self._set_job_status(job_id, "paused")

    def resume_job(self, job_id: str) -> None:
        job = self._get_job(job_id)
        if job is None:
            raise ValueError(f"Scheduled job not found: {job_id}")
        if job["status"] != "paused":
            raise ValueError(f"Cannot resume a job with status '{job['status']}'.")
        self._set_job_status(job_id, "running", next_run_now=True)

    def cancel_job(self, job_id: str) -> None:
        job = self._get_job(job_id)
        if job is None:
            raise ValueError(f"Scheduled job not found: {job_id}")
        if job["status"] not in ("running", "paused"):
            raise ValueError(f"Cannot cancel a job with status '{job['status']}'.")
        self._set_job_status(job_id, "cancelled")

    def retry_failed_job(self, job_id: str) -> None:
        connection = self._connect()
        try:
            cursor = connection.execute(
                """
                UPDATE scheduled_jobs
                SET status = 'running',
                    generation_attempts = 0,
                    last_error = NULL,
                    next_run_at = ?,
                    updated_at = ?
                WHERE id = ? AND status = 'failed'
                """,
                (time.time(), datetime.now().isoformat(), job_id),
            )
            if cursor.rowcount == 0:
                exists = connection.execute(
                    "SELECT status FROM scheduled_jobs WHERE id = ?",
                    (job_id,),
                ).fetchone()
                if exists is None:
                    raise ValueError(f"Scheduled job not found: {job_id}")
                raise ValueError(f"Cannot retry a job with status '{exists['status']}'.")
            connection.commit()
        finally:
            connection.close()

        self.run_scheduled_job(job_id)

    def schedule(
        self,
        post_config: Dict[str, object],
        interval_seconds: int,
        count: int = 0,
    ) -> str:
        job_id = self.create_job(post_config, interval_seconds, count)
        print(f"Starting scheduled job {job_id} every {interval_seconds} seconds.")
        print("Use --pause-job, --resume-job, or --cancel-job with this job ID to control it.")
        try:
            self.run_job(job_id)
        except KeyboardInterrupt:
            print(f"Scheduled job {job_id} stopped. Its state is saved and can be resumed.")
        return job_id

    def create_job(
        self,
        post_config: Dict[str, object],
        interval_seconds: int,
        count: int = 0,
    ) -> str:
        if interval_seconds <= 0:
            raise ValueError("Interval must be a positive number of seconds.")
        if count < 0:
            raise ValueError("Scheduled post count must be non-negative.")
        return self._create_job(post_config, interval_seconds, count)

    def run_job(self, job_id: str) -> None:
        owner_token = uuid.uuid4().hex
        if not self._claim_worker(job_id, owner_token):
            return

        stop_heartbeat = threading.Event()
        heartbeat_errors: List[Exception] = []
        heartbeat_thread = threading.Thread(
            target=self._heartbeat_worker,
            args=(job_id, owner_token, stop_heartbeat, heartbeat_errors),
            daemon=True,
        )
        heartbeat_thread.start()
        try:
            while True:
                if heartbeat_errors:
                    raise RuntimeError("Scheduled job worker lease could not be renewed.") from heartbeat_errors[0]

                job = self._get_job(job_id)
                if job is None:
                    raise ValueError(f"Scheduled job not found: {job_id}")
                if job["status"] == "paused":
                    time.sleep(1)
                    continue
                if job["status"] != "running":
                    return

                next_run_at = float(job["next_run_at"])
                delay = next_run_at - time.time()
                if delay > 0:
                    time.sleep(min(delay, 1))
                    continue

                post_config = json.loads(str(job["post_config"]))
                iteration = int(job["completed_count"]) + 1
                stored_output = self._get_iteration_output(job_id, iteration)
                if stored_output is None:
                    try:
                        post = self.generator.generate_post(**post_config)
                    except Exception as exc:
                        attempt = self._record_generation_failure(job_id, owner_token, exc)
                        if attempt >= self.MAX_GENERATION_ATTEMPTS:
                            logger.error(
                                "Scheduled job %s failed after %s generation attempts.",
                                job_id,
                                attempt,
                            )
                            raise
                        retry_delay = self.RETRY_BASE_DELAY_SECONDS * (2 ** (attempt - 1))
                        logger.warning(
                            "Generation attempt %s/%s failed for scheduled job %s; retrying in %s seconds: %s: %s",
                            attempt,
                            self.MAX_GENERATION_ATTEMPTS,
                            job_id,
                            retry_delay,
                            type(exc).__name__,
                            exc,
                        )
                        self._set_next_run(job_id, owner_token, time.time() + retry_delay)
                        continue

                    if heartbeat_errors:
                        raise RuntimeError(
                            "Scheduled job worker lease could not be renewed."
                        ) from heartbeat_errors[0]
                    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
                    filename = (
                        Path(str(job["output_dir"]))
                        / f"scheduled_post_{timestamp}_{job_id[:8]}_{iteration}.json"
                    )
                    try:
                        self._store_iteration_output(
                            job_id,
                            owner_token,
                            iteration,
                            post,
                            filename,
                        )
                    except Exception as exc:
                        self._mark_failed(job_id, owner_token, exc)
                        raise
                else:
                    post, filename = stored_output
                try:
                    filename.parent.mkdir(parents=True, exist_ok=True)
                    with filename.open("w", encoding="utf-8") as out_file:
                        json.dump(post, out_file, ensure_ascii=False, indent=2)
                except Exception as exc:
                    self._mark_failed(job_id, owner_token, exc)
                    raise

                completed_count = int(job["completed_count"]) + 1
                target_count = int(job["target_count"])
                status = "completed" if target_count > 0 and completed_count >= target_count else "running"
                self._record_iteration(
                    job_id,
                    owner_token,
                    completed_count,
                    status,
                    time.time() + int(job["interval_seconds"]),
                )
                print(f"[{datetime.now().isoformat()}] Generated scheduled post #{completed_count}: {filename}")
                if status == "completed":
                    return
        finally:
            stop_heartbeat.set()
            heartbeat_thread.join()
            self._release_worker(job_id, owner_token)

    def run_scheduled_job(self, job_id: str) -> None:
        job = self._get_job(job_id)
        if job is None:
            raise ValueError(f"Scheduled job not found: {job_id}")
        if job["status"] != "running":
            raise ValueError(f"Cannot run a job with status '{job['status']}'.")
        self.run_job(job_id)

    def start_available_jobs(self, max_workers: int = 4) -> int:
        if max_workers < 1:
            raise ValueError("Maximum scheduled workers must be a positive integer.")

        running_jobs = [
            str(job["id"])
            for job in self.list_jobs()
            if job["status"] == "running"
        ]
        started = 0
        with self._supervisor_lock:
            active_workers = sum(worker.is_alive() for worker in self._supervisor_workers.values())
            for job_id in running_jobs:
                worker = self._supervisor_workers.get(job_id)
                if worker is not None and worker.is_alive():
                    continue
                if active_workers >= max_workers:
                    break

                worker = threading.Thread(
                    target=self._run_supervised_job,
                    args=(job_id,),
                    name=f"scheduled-job-{job_id[:8]}",
                    daemon=True,
                )
                self._supervisor_workers[job_id] = worker
                worker.start()
                active_workers += 1
                started += 1
        return started

    def run_supervisor(self, poll_interval_seconds: int = 5, max_workers: int = 4) -> None:
        if poll_interval_seconds < 1:
            raise ValueError("Supervisor poll interval must be a positive integer.")
        if max_workers < 1:
            raise ValueError("Maximum scheduled workers must be a positive integer.")

        print(
            f"Supervising scheduled jobs every {poll_interval_seconds} seconds "
            f"(max workers: {max_workers})."
        )
        print("Press Ctrl+C to stop the supervisor.")
        try:
            while True:
                self.start_available_jobs(max_workers=max_workers)
                time.sleep(poll_interval_seconds)
        except KeyboardInterrupt:
            print("Scheduler supervisor stopped. Running jobs remain persisted for recovery.")

    def _run_supervised_job(self, job_id: str) -> None:
        try:
            self.run_scheduled_job(job_id)
        except ValueError as exc:
            if "already has an active worker" in str(exc):
                logger.debug("Another supervisor owns scheduled job %s.", job_id)
            else:
                logger.exception("Could not run scheduled job %s.", job_id)
        except Exception:
            logger.exception("Supervised scheduled job %s stopped unexpectedly.", job_id)
        finally:
            with self._supervisor_lock:
                if self._supervisor_workers.get(job_id) is threading.current_thread():
                    del self._supervisor_workers[job_id]

    def _claim_worker(self, job_id: str, owner_token: str) -> bool:
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            job = connection.execute(
                "SELECT status FROM scheduled_jobs WHERE id = ?",
                (job_id,),
            ).fetchone()
            if job is None:
                raise ValueError(f"Scheduled job not found: {job_id}")
            if job["status"] != "running":
                connection.commit()
                return False

            now = time.time()
            worker = connection.execute(
                "SELECT owner_token, lease_expires_at FROM scheduled_job_workers WHERE job_id = ?",
                (job_id,),
            ).fetchone()
            if worker is not None and float(worker["lease_expires_at"]) > now:
                raise ValueError(f"Scheduled job {job_id} already has an active worker.")

            connection.execute(
                """
                INSERT INTO scheduled_job_workers (job_id, owner_token, lease_expires_at)
                VALUES (?, ?, ?)
                ON CONFLICT(job_id) DO UPDATE SET
                    owner_token = excluded.owner_token,
                    lease_expires_at = excluded.lease_expires_at
                """,
                (job_id, owner_token, now + self.WORKER_LEASE_SECONDS),
            )
            connection.commit()
            return True
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _heartbeat_worker(
        self,
        job_id: str,
        owner_token: str,
        stop_event: threading.Event,
        errors: List[Exception],
    ) -> None:
        while not stop_event.wait(self.WORKER_HEARTBEAT_SECONDS):
            connection: Optional[sqlite3.Connection] = None
            try:
                connection = self._connect()
                cursor = connection.execute(
                    """
                    UPDATE scheduled_job_workers
                    SET lease_expires_at = ?
                    WHERE job_id = ? AND owner_token = ?
                    """,
                    (time.time() + self.WORKER_LEASE_SECONDS, job_id, owner_token),
                )
                connection.commit()
                if cursor.rowcount == 0:
                    errors.append(RuntimeError("Scheduled job worker lease was lost."))
                    return
            except sqlite3.Error as exc:
                errors.append(exc)
                logger.exception("Could not renew scheduler worker lease for job %s.", job_id)
                return
            finally:
                if connection is not None:
                    connection.close()

    def _release_worker(self, job_id: str, owner_token: str) -> None:
        connection = self._connect()
        try:
            connection.execute(
                "DELETE FROM scheduled_job_workers WHERE job_id = ? AND owner_token = ?",
                (job_id, owner_token),
            )
            connection.commit()
        finally:
            connection.close()

    def _record_iteration(
        self,
        job_id: str,
        owner_token: str,
        completed_count: int,
        status: str,
        next_run_at: float,
    ) -> None:
        connection = self._connect()
        try:
            cursor = connection.execute(
                """
                UPDATE scheduled_jobs
                SET completed_count = ?,
                    generation_attempts = 0,
                    last_error = NULL,
                    status = CASE WHEN ? = 'completed' THEN 'completed' ELSE status END,
                    next_run_at = ?, updated_at = ?
                WHERE id = ? AND EXISTS (
                    SELECT 1 FROM scheduled_job_workers
                    WHERE job_id = ? AND owner_token = ? AND lease_expires_at > ?
                )
                """,
                (
                    completed_count,
                    status,
                    next_run_at,
                    datetime.now().isoformat(),
                    job_id,
                    job_id,
                    owner_token,
                    time.time(),
                ),
            )
            if cursor.rowcount == 0:
                raise RuntimeError("Scheduled job worker lease was lost before recording progress.")
            connection.commit()
        finally:
            connection.close()

    def _record_generation_failure(
        self,
        job_id: str,
        owner_token: str,
        error: Exception,
    ) -> int:
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            cursor = connection.execute(
                """
                UPDATE scheduled_jobs
                SET generation_attempts = generation_attempts + 1,
                    last_error = ?,
                    status = CASE
                        WHEN generation_attempts + 1 >= ? THEN 'failed'
                        ELSE status
                    END,
                    updated_at = ?
                WHERE id = ? AND status = 'running' AND EXISTS (
                    SELECT 1 FROM scheduled_job_workers
                    WHERE job_id = ? AND owner_token = ? AND lease_expires_at > ?
                )
                """,
                (
                    f"{type(error).__name__}: {error}",
                    self.MAX_GENERATION_ATTEMPTS,
                    datetime.now().isoformat(),
                    job_id,
                    job_id,
                    owner_token,
                    time.time(),
                ),
            )
            if cursor.rowcount == 0:
                raise RuntimeError("Scheduled job worker lease was lost before recording generation failure.")
            row = connection.execute(
                "SELECT generation_attempts FROM scheduled_jobs WHERE id = ?",
                (job_id,),
            ).fetchone()
            connection.commit()
            return int(row["generation_attempts"])
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _set_next_run(self, job_id: str, owner_token: str, next_run_at: float) -> None:
        connection = self._connect()
        try:
            cursor = connection.execute(
                """
                UPDATE scheduled_jobs
                SET next_run_at = ?, updated_at = ?
                WHERE id = ? AND status = 'running' AND EXISTS (
                    SELECT 1 FROM scheduled_job_workers
                    WHERE job_id = ? AND owner_token = ? AND lease_expires_at > ?
                )
                """,
                (
                    next_run_at,
                    datetime.now().isoformat(),
                    job_id,
                    job_id,
                    owner_token,
                    time.time(),
                ),
            )
            if cursor.rowcount == 0:
                raise RuntimeError("Scheduled job worker lease was lost before scheduling a retry.")
            connection.commit()
        finally:
            connection.close()

    def _get_iteration_output(
        self,
        job_id: str,
        iteration: int,
    ) -> Optional[tuple[Dict[str, object], Path]]:
        connection = self._connect()
        try:
            row = connection.execute(
                """
                SELECT payload_json, output_path
                FROM scheduled_job_outputs
                WHERE job_id = ? AND iteration = ?
                """,
                (job_id, iteration),
            ).fetchone()
            if row is None:
                return None
            payload = json.loads(str(row["payload_json"]))
            if not isinstance(payload, dict):
                raise ValueError(f"Stored output for scheduled job {job_id} is not a JSON object.")
            return payload, Path(str(row["output_path"]))
        finally:
            connection.close()

    def _store_iteration_output(
        self,
        job_id: str,
        owner_token: str,
        iteration: int,
        post: Dict[str, object],
        output_path: Path,
    ) -> None:
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            cursor = connection.execute(
                """
                INSERT INTO scheduled_job_outputs (
                    job_id, iteration, payload_json, output_path, created_at
                )
                SELECT ?, ?, ?, ?, ?
                WHERE EXISTS (
                    SELECT 1 FROM scheduled_job_workers
                    WHERE job_id = ? AND owner_token = ? AND lease_expires_at > ?
                )
                """,
                (
                    job_id,
                    iteration,
                    json.dumps(post, ensure_ascii=False),
                    str(output_path),
                    datetime.now().isoformat(),
                    job_id,
                    owner_token,
                    time.time(),
                ),
            )
            if cursor.rowcount == 0:
                raise RuntimeError("Scheduled job worker lease was lost before storing generated output.")
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _mark_failed(self, job_id: str, owner_token: str, error: Exception) -> None:
        connection = self._connect()
        try:
            cursor = connection.execute(
                """
                UPDATE scheduled_jobs
                SET status = 'failed', last_error = ?, updated_at = ?
                WHERE id = ? AND EXISTS (
                    SELECT 1 FROM scheduled_job_workers
                    WHERE job_id = ? AND owner_token = ? AND lease_expires_at > ?
                )
                """,
                (
                    f"{type(error).__name__}: {error}",
                    datetime.now().isoformat(),
                    job_id,
                    job_id,
                    owner_token,
                    time.time(),
                ),
            )
            if cursor.rowcount == 0:
                logger.warning(
                    "Could not mark scheduled job %s as failed because its worker lease was lost.",
                    job_id,
                )
            connection.commit()
        finally:
            connection.close()
