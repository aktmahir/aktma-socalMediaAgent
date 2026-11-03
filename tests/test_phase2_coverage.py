import json
import os
import sqlite3
import sys
import threading
import time
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import Mock, patch

import app as cli_module
from social_media_agent.scheduler import PeriodicPostScheduler
from social_media_agent.web import create_app


class PhaseTwoCoverageTests(unittest.TestCase):
    def test_web_rejects_invalid_schedule_values(self) -> None:
        app = create_app()
        client = app.test_client()

        response = client.post(
            "/",
            data={
                "topic": "AI marketing",
                "platform": "instagram",
                "media_type": "text",
                "tone": "friendly",
                "length": "medium",
                "language": "English",
                "interval": "0m",
                "count": "-1",
                "scheduled_output": "scheduled_posts",
            },
        )

        self.assertEqual(response.status_code, 200)
        response_text = response.get_data(as_text=True)
        self.assertIn("Status:", response_text)
        self.assertTrue(
            "positive" in response_text or "non-negative" in response_text,
            response_text,
        )

    def test_web_generates_post_for_valid_submission(self) -> None:
        with patch.dict(os.environ, {"OPENAI_API_KEY": ""}):
            app = create_app()
            client = app.test_client()

            response = client.post(
                "/",
                data={
                    "topic": "AI marketing",
                    "platform": "linkedin",
                    "media_type": "text",
                    "tone": "professional",
                    "length": "medium",
                    "language": "English",
                    "interval": "",
                    "count": "0",
                },
            )

        self.assertEqual(response.status_code, 200)
        response_text = response.get_data(as_text=True)
        self.assertIn("Generated Post", response_text)
        self.assertIn("AI marketing", response_text)

    def test_web_creates_persistent_job_and_starts_worker_for_schedule(self) -> None:
        scheduler = Mock()
        scheduler.create_job.return_value = "scheduled-job-id"
        worker_thread = Mock()
        with patch.dict(os.environ, {"OPENAI_API_KEY": ""}), patch(
            "social_media_agent.web.PeriodicPostScheduler",
            return_value=scheduler,
        ) as scheduler_class, patch(
            "social_media_agent.web.threading.Thread",
            return_value=worker_thread,
        ) as thread_class, tempfile.TemporaryDirectory() as output_dir:
            app = create_app()
            client = app.test_client()
            response = client.post(
                "/",
                data={
                    "topic": "AI marketing",
                    "platform": "linkedin",
                    "media_type": "text",
                    "tone": "professional",
                    "length": "medium",
                    "language": "English",
                    "interval": "1h",
                    "count": "2",
                    "scheduled_output": output_dir,
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertIn("scheduled-job-id", response.get_data(as_text=True))
        scheduler_class.assert_called_once()
        scheduler.create_job.assert_called_once_with(
            {
                "topic": "AI marketing",
                "platform": "linkedin",
                "tone": "professional",
                "length": "medium",
                "language": "English",
                "media_type": "text",
                "media_filename": None,
            },
            interval_seconds=3600,
            count=2,
        )
        thread_class.assert_called_once_with(
            target=scheduler.run_scheduled_job,
            kwargs={"job_id": "scheduled-job-id"},
            daemon=True,
        )
        worker_thread.start.assert_called_once_with()

    def test_scheduler_writes_output_file_per_iteration(self) -> None:
        generator = Mock()
        generator.generate_post.return_value = {
            "topic": "AI marketing",
            "platform": "instagram",
            "tone": "friendly",
            "length": "medium",
            "language": "English",
            "media_type": "text",
            "media_filename": None,
            "caption": "Example caption",
            "hashtags": ["ai", "marketing"],
            "call_to_action": "Share this!",
            "title": "",
            "description": "",
            "tags": [],
        }

        with tempfile.TemporaryDirectory() as tmp_dir:
            scheduler = PeriodicPostScheduler(generator, output_dir=tmp_dir)
            scheduler.schedule(
                {"topic": "AI marketing", "platform": "instagram"},
                interval_seconds=1,
                count=1,
            )

            output_files = sorted(Path(tmp_dir).glob("scheduled_post_*.json"))
            self.assertEqual(len(output_files), 1)
            payload = json.loads(output_files[0].read_text(encoding="utf-8"))
            self.assertEqual(payload["caption"], "Example caption")
            generator.generate_post.assert_called_once_with(topic="AI marketing", platform="instagram")

    def test_scheduler_job_state_persists_across_instances(self) -> None:
        generator = Mock()
        with tempfile.TemporaryDirectory() as tmp_dir:
            database_path = str(Path(tmp_dir) / "scheduler.sqlite3")
            first_scheduler = PeriodicPostScheduler(
                generator,
                output_dir=tmp_dir,
                database_path=database_path,
            )
            job_id = first_scheduler.create_job(
                {"topic": "AI marketing"},
                interval_seconds=60,
                count=2,
            )
            first_scheduler.pause_job(job_id)

            restarted_scheduler = PeriodicPostScheduler(
                generator,
                output_dir=tmp_dir,
                database_path=database_path,
            )
            job = restarted_scheduler.list_jobs()[0]
            self.assertEqual(job["id"], job_id)
            self.assertEqual(job["status"], "paused")
            self.assertEqual(job["completed_count"], 0)

            restarted_scheduler.resume_job(job_id)
            restarted_scheduler.cancel_job(job_id)
            self.assertEqual(restarted_scheduler.list_jobs()[0]["status"], "cancelled")

    def test_scheduler_adds_retry_state_to_existing_database(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            database_path = Path(tmp_dir) / "scheduler.sqlite3"
            connection = sqlite3.connect(str(database_path))
            try:
                connection.execute(
                    """
                    CREATE TABLE scheduled_jobs (
                        id TEXT PRIMARY KEY,
                        post_config TEXT NOT NULL,
                        interval_seconds INTEGER NOT NULL,
                        target_count INTEGER NOT NULL,
                        completed_count INTEGER NOT NULL DEFAULT 0,
                        status TEXT NOT NULL,
                        output_dir TEXT NOT NULL,
                        next_run_at REAL NOT NULL,
                        last_error TEXT,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    )
                    """
                )
                connection.commit()
            finally:
                connection.close()

            PeriodicPostScheduler(Mock(), output_dir=tmp_dir, database_path=str(database_path))

            connection = sqlite3.connect(str(database_path))
            try:
                columns = {
                    row[1] for row in connection.execute("PRAGMA table_info(scheduled_jobs)")
                }
            finally:
                connection.close()
            self.assertIn("generation_attempts", columns)

    def test_scheduler_recovers_and_completes_persisted_job(self) -> None:
        generator = Mock()
        generator.generate_post.return_value = {"caption": "Recovered caption"}
        with tempfile.TemporaryDirectory() as tmp_dir:
            database_path = str(Path(tmp_dir) / "scheduler.sqlite3")
            first_scheduler = PeriodicPostScheduler(
                generator,
                output_dir=tmp_dir,
                database_path=database_path,
            )
            job_id = first_scheduler.create_job(
                {"topic": "AI marketing"},
                interval_seconds=60,
                count=1,
            )

            restarted_scheduler = PeriodicPostScheduler(
                generator,
                output_dir=tmp_dir,
                database_path=database_path,
            )
            restarted_scheduler.run_scheduled_job(job_id)

            job = restarted_scheduler.list_jobs()[0]
            self.assertEqual(job["status"], "completed")
            self.assertEqual(job["completed_count"], 1)
            output_files = list(Path(tmp_dir).glob(f"scheduled_post_*_{job_id[:8]}_1.json"))
            self.assertEqual(len(output_files), 1)
            generator.generate_post.assert_called_once_with(topic="AI marketing")

    def test_scheduler_supervisor_recovers_running_persisted_job(self) -> None:
        generator = Mock()
        generator.generate_post.return_value = {"caption": "Supervised caption"}
        with tempfile.TemporaryDirectory() as tmp_dir:
            scheduler = PeriodicPostScheduler(generator, output_dir=tmp_dir)
            job_id = scheduler.create_job(
                {"topic": "AI marketing"},
                interval_seconds=60,
                count=1,
            )

            self.assertEqual(scheduler.start_available_jobs(), 1)
            deadline = time.monotonic() + 2
            while time.monotonic() < deadline:
                job = scheduler.list_jobs()[0]
                if job["status"] == "completed":
                    break
                time.sleep(0.01)

            self.assertEqual(job["id"], job_id)
            self.assertEqual(job["status"], "completed")
            self.assertEqual(job["completed_count"], 1)
            generator.generate_post.assert_called_once_with(topic="AI marketing")

    def test_scheduler_supervisor_rejects_non_positive_worker_limit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            scheduler = PeriodicPostScheduler(Mock(), output_dir=tmp_dir)
            with self.assertRaisesRegex(ValueError, "positive integer"):
                scheduler.start_available_jobs(max_workers=0)

    def test_scheduler_supervisor_respects_worker_limit(self) -> None:
        generator = Mock()
        active_generations = 0
        max_active_generations = 0
        generation_lock = threading.Lock()
        first_generation_started = threading.Event()
        release_generation = threading.Event()

        def generate_post(**_: object) -> dict:
            nonlocal active_generations, max_active_generations
            with generation_lock:
                active_generations += 1
                max_active_generations = max(max_active_generations, active_generations)
                first_generation_started.set()
            release_generation.wait(timeout=2)
            with generation_lock:
                active_generations -= 1
            return {"caption": "Supervised caption"}

        generator.generate_post.side_effect = generate_post
        with tempfile.TemporaryDirectory() as tmp_dir:
            scheduler = PeriodicPostScheduler(generator, output_dir=tmp_dir)
            scheduler.create_job({"topic": "First"}, interval_seconds=60, count=1)
            scheduler.create_job({"topic": "Second"}, interval_seconds=60, count=1)

            try:
                self.assertEqual(scheduler.start_available_jobs(max_workers=1), 1)
                self.assertTrue(first_generation_started.wait(timeout=1))
                self.assertEqual(scheduler.start_available_jobs(max_workers=1), 0)
                release_generation.set()

                deadline = time.monotonic() + 2
                while time.monotonic() < deadline:
                    jobs = scheduler.list_jobs()
                    if all(job["status"] == "completed" for job in jobs):
                        break
                    scheduler.start_available_jobs(max_workers=1)
                    time.sleep(0.01)

                self.assertTrue(all(job["status"] == "completed" for job in scheduler.list_jobs()))
                self.assertEqual(max_active_generations, 1)
                self.assertEqual(generator.generate_post.call_count, 2)
            finally:
                release_generation.set()

    def test_scheduler_replays_persisted_output_after_progress_write_failure(self) -> None:
        generator = Mock()
        generator.generate_post.return_value = {"caption": "Persisted caption"}
        with tempfile.TemporaryDirectory() as tmp_dir:
            scheduler = PeriodicPostScheduler(generator, output_dir=tmp_dir)
            job_id = scheduler.create_job(
                {"topic": "AI marketing"},
                interval_seconds=60,
                count=1,
            )

            with patch.object(
                scheduler,
                "_record_iteration",
                side_effect=RuntimeError("simulated interruption"),
            ), self.assertRaisesRegex(RuntimeError, "simulated interruption"):
                scheduler.run_scheduled_job(job_id)

            self.assertEqual(scheduler.list_jobs()[0]["completed_count"], 0)
            with patch.object(scheduler, "_record_iteration", wraps=scheduler._record_iteration):
                scheduler.run_scheduled_job(job_id)

            job = scheduler.list_jobs()[0]
            self.assertEqual(job["status"], "completed")
            self.assertEqual(job["completed_count"], 1)
            output_files = list(Path(tmp_dir).glob(f"scheduled_post_*_{job_id[:8]}_1.json"))
            self.assertEqual(len(output_files), 1)
            payload = json.loads(output_files[0].read_text(encoding="utf-8"))
            self.assertEqual(payload["caption"], "Persisted caption")
            generator.generate_post.assert_called_once_with(topic="AI marketing")

    def test_scheduler_rejects_second_active_worker_for_same_job(self) -> None:
        generation_started = threading.Event()
        allow_generation = threading.Event()
        generator = Mock()

        def wait_for_generation(**_: object) -> dict:
            generation_started.set()
            if not allow_generation.wait(timeout=5):
                raise TimeoutError("Test did not release scheduled generation.")
            return {"caption": "Single worker"}

        generator.generate_post.side_effect = wait_for_generation
        with tempfile.TemporaryDirectory() as tmp_dir:
            database_path = str(Path(tmp_dir) / "scheduler.sqlite3")
            first_scheduler = PeriodicPostScheduler(
                generator,
                output_dir=tmp_dir,
                database_path=database_path,
            )
            second_scheduler = PeriodicPostScheduler(
                generator,
                output_dir=tmp_dir,
                database_path=database_path,
            )
            job_id = first_scheduler.create_job(
                {"topic": "AI marketing"},
                interval_seconds=60,
                count=1,
            )
            worker = threading.Thread(target=first_scheduler.run_scheduled_job, args=(job_id,))
            worker.start()
            self.assertTrue(generation_started.wait(timeout=5))

            try:
                with self.assertRaisesRegex(ValueError, "active worker"):
                    second_scheduler.run_scheduled_job(job_id)
            finally:
                allow_generation.set()
                worker.join(timeout=5)

            self.assertFalse(worker.is_alive())
            self.assertEqual(generator.generate_post.call_count, 1)
            self.assertEqual(second_scheduler.list_jobs()[0]["status"], "completed")

    def test_scheduler_allows_recovery_after_worker_lease_expires(self) -> None:
        generator = Mock()
        generator.generate_post.return_value = {"caption": "Recovered"}
        with tempfile.TemporaryDirectory() as tmp_dir:
            database_path = str(Path(tmp_dir) / "scheduler.sqlite3")
            scheduler = PeriodicPostScheduler(
                generator,
                output_dir=tmp_dir,
                database_path=database_path,
            )
            job_id = scheduler.create_job(
                {"topic": "AI marketing"},
                interval_seconds=60,
                count=1,
            )
            connection = scheduler._connect()
            try:
                connection.execute(
                    """
                    INSERT INTO scheduled_job_workers (job_id, owner_token, lease_expires_at)
                    VALUES (?, ?, ?)
                    """,
                    (job_id, "stale-worker", time.time() - 1),
                )
                connection.commit()
            finally:
                connection.close()

            scheduler.run_scheduled_job(job_id)
            self.assertEqual(scheduler.list_jobs()[0]["status"], "completed")
            generator.generate_post.assert_called_once_with(topic="AI marketing")

    def test_scheduler_records_failed_job_and_reraises(self) -> None:
        generator = Mock()
        generator.generate_post.side_effect = RuntimeError("generation failed")
        with tempfile.TemporaryDirectory() as tmp_dir:
            scheduler = PeriodicPostScheduler(generator, output_dir=tmp_dir)
            job_id = scheduler.create_job({"topic": "AI marketing"}, interval_seconds=1, count=1)

            with patch("social_media_agent.scheduler.time.sleep"), self.assertRaisesRegex(
                RuntimeError,
                "generation failed",
            ):
                scheduler.run_scheduled_job(job_id)

            job = scheduler.list_jobs()[0]
            self.assertEqual(job["status"], "failed")
            self.assertIn("generation failed", job["last_error"])
            self.assertEqual(job["generation_attempts"], scheduler.MAX_GENERATION_ATTEMPTS)
            self.assertEqual(generator.generate_post.call_count, scheduler.MAX_GENERATION_ATTEMPTS)

    def test_operator_can_retry_a_failed_job(self) -> None:
        generator = Mock()
        generator.generate_post.side_effect = [
            RuntimeError("initial failure"),
            RuntimeError("initial failure"),
            RuntimeError("initial failure"),
            {"caption": "Operator retry succeeded"},
        ]
        with tempfile.TemporaryDirectory() as tmp_dir:
            scheduler = PeriodicPostScheduler(generator, output_dir=tmp_dir)
            job_id = scheduler.create_job({"topic": "AI marketing"}, interval_seconds=60, count=1)
            with patch("social_media_agent.scheduler.time.sleep"), self.assertRaisesRegex(
                RuntimeError,
                "initial failure",
            ):
                scheduler.run_scheduled_job(job_id)

            failed_job = scheduler.list_jobs()[0]
            self.assertEqual(failed_job["status"], "failed")
            self.assertEqual(failed_job["generation_attempts"], scheduler.MAX_GENERATION_ATTEMPTS)

            scheduler.retry_failed_job(job_id)

            retried_job = scheduler.list_jobs()[0]
            self.assertEqual(retried_job["status"], "completed")
            self.assertEqual(retried_job["completed_count"], 1)
            self.assertEqual(retried_job["generation_attempts"], 0)
            self.assertIsNone(retried_job["last_error"])
            self.assertEqual(generator.generate_post.call_count, 4)

    def test_operator_retry_rejects_non_failed_job(self) -> None:
        generator = Mock()
        with tempfile.TemporaryDirectory() as tmp_dir:
            scheduler = PeriodicPostScheduler(generator, output_dir=tmp_dir)
            job_id = scheduler.create_job({"topic": "AI marketing"}, interval_seconds=60, count=1)

            with self.assertRaisesRegex(ValueError, "status 'running'"):
                scheduler.retry_failed_job(job_id)

            self.assertEqual(scheduler.list_jobs()[0]["status"], "running")
            generator.generate_post.assert_not_called()

    def test_scheduler_retries_generation_and_resets_attempt_count_on_success(self) -> None:
        generator = Mock()
        generator.generate_post.side_effect = [
            RuntimeError("temporary failure"),
            RuntimeError("temporary failure"),
            {"caption": "Recovered after retry"},
        ]
        current_time = [0.0]
        retry_delays = []
        sleep_delays = []
        with tempfile.TemporaryDirectory() as tmp_dir:
            scheduler = PeriodicPostScheduler(generator, output_dir=tmp_dir)
            job_id = scheduler.create_job({"topic": "AI marketing"}, interval_seconds=60, count=1)
            current_time[0] = time.time()
            set_next_run = scheduler._set_next_run

            def capture_retry_time(job: str, owner: str, next_run_at: float) -> None:
                retry_delays.append(next_run_at - current_time[0])
                set_next_run(job, owner, next_run_at)

            def advance_clock(delay: float) -> None:
                sleep_delays.append(delay)
                current_time[0] += delay

            with patch(
                "social_media_agent.scheduler.time.time",
                side_effect=lambda: current_time[0],
            ), patch(
                "social_media_agent.scheduler.time.sleep",
                side_effect=advance_clock,
            ), patch.object(
                scheduler,
                "_set_next_run",
                side_effect=capture_retry_time,
            ):
                scheduler.run_scheduled_job(job_id)

            job = scheduler.list_jobs()[0]
            self.assertEqual(job["status"], "completed")
            self.assertEqual(job["completed_count"], 1)
            self.assertEqual(job["generation_attempts"], 0)
            self.assertIsNone(job["last_error"])
            self.assertEqual(generator.generate_post.call_count, 3)
            self.assertEqual(retry_delays, [1, 2])
            self.assertEqual(sleep_delays, [1, 1, 1])

    def test_running_worker_waits_while_paused_and_resumes(self) -> None:
        generator = Mock()
        generator.generate_post.return_value = {"caption": "Scheduled caption"}
        with tempfile.TemporaryDirectory() as tmp_dir:
            scheduler = PeriodicPostScheduler(generator, output_dir=tmp_dir)
            job_id = scheduler.create_job(
                {"topic": "AI marketing"},
                interval_seconds=60,
                count=2,
            )
            sleep_calls = 0

            def pause_then_resume(_: float) -> None:
                nonlocal sleep_calls
                sleep_calls += 1
                if sleep_calls == 1:
                    scheduler.pause_job(job_id)
                elif sleep_calls == 2:
                    scheduler.resume_job(job_id)

            with patch("social_media_agent.scheduler.time.sleep", side_effect=pause_then_resume):
                scheduler.run_scheduled_job(job_id)

            job = scheduler.list_jobs()[0]
            self.assertEqual(job["status"], "completed")
            self.assertEqual(job["completed_count"], 2)
            self.assertEqual(generator.generate_post.call_count, 2)

    def test_cli_lists_persisted_jobs_without_generation_arguments(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            database_path = str(Path(tmp_dir) / "scheduler.sqlite3")
            output = StringIO()
            with patch.object(
                sys,
                "argv",
                ["app.py", "--list-scheduled", "--scheduler-db", database_path],
            ), patch.object(
                cli_module,
                "SocialMediaPostGenerator",
                return_value=Mock(),
            ), redirect_stdout(output):
                cli_module.main()

            self.assertIn("No scheduled jobs found.", output.getvalue())

    def test_cli_retry_command_invokes_scheduler_retry(self) -> None:
        scheduler = Mock()
        with tempfile.TemporaryDirectory() as tmp_dir:
            database_path = str(Path(tmp_dir) / "scheduler.sqlite3")
            with patch.object(
                sys,
                "argv",
                [
                    "app.py",
                    "--retry-job",
                    "job-id",
                    "--scheduler-db",
                    database_path,
                ],
            ), patch.object(
                cli_module,
                "SocialMediaPostGenerator",
                return_value=Mock(),
            ), patch.object(
                cli_module,
                "PeriodicPostScheduler",
                return_value=scheduler,
            ):
                cli_module.main()

        scheduler.retry_failed_job.assert_called_once_with("job-id")

    def test_cli_supervisor_command_dispatches_scheduler_options(self) -> None:
        scheduler = Mock()
        with tempfile.TemporaryDirectory() as tmp_dir:
            database_path = str(Path(tmp_dir) / "scheduler.sqlite3")
            with patch.object(
                sys,
                "argv",
                [
                    "app.py",
                    "--supervise-scheduled",
                    "--scheduler-poll-seconds",
                    "3",
                    "--max-scheduled-workers",
                    "2",
                    "--scheduler-db",
                    database_path,
                ],
            ), patch.object(
                cli_module,
                "SocialMediaPostGenerator",
                return_value=Mock(),
            ), patch.object(
                cli_module,
                "PeriodicPostScheduler",
                return_value=scheduler,
            ):
                cli_module.main()

        scheduler.run_supervisor.assert_called_once_with(
            poll_interval_seconds=3,
            max_workers=2,
        )


if __name__ == "__main__":
    unittest.main()
