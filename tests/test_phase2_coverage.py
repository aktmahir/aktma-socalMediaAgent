import json
import os
import re
import sqlite3
import sys
import threading
import time
import tempfile
import unittest
from contextlib import redirect_stdout
from io import BytesIO, StringIO
from pathlib import Path
from unittest.mock import Mock, patch

from PIL import Image

import app as cli_module
from social_media_agent.observability import RequestMetrics
from social_media_agent.scheduler import PeriodicPostScheduler
from social_media_agent.web import MAX_UPLOAD_BYTES, _has_matching_signature, create_app


def _make_png() -> bytes:
    image = Image.new("RGB", (16, 8), (220, 80, 35))
    output = BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


def _post_with_csrf(client, *args, **kwargs):
    page = client.get("/")
    match = re.search(
        r'<input type="hidden" name="csrf_token" value="([^"]+)"',
        page.get_data(as_text=True),
    )
    if match is None:
        raise AssertionError("The web form did not contain a CSRF token.")
    data = dict(kwargs.get("data") or {})
    data["csrf_token"] = match.group(1)
    kwargs["data"] = data
    return client.post(*args, **kwargs)


class PhaseTwoCoverageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.observability_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.observability_dir.cleanup)
        self.observability_env = patch.dict(
            os.environ,
            {
                "OBSERVABILITY_DB_PATH": str(
                    Path(self.observability_dir.name) / "observability.sqlite3"
                )
            },
        )
        self.observability_env.start()
        self.addCleanup(self.observability_env.stop)

    def test_web_form_includes_csrf_token_and_rejects_missing_token(self) -> None:
        with patch("social_media_agent.web.SocialMediaPostGenerator", return_value=Mock()):
            client = create_app().test_client()
            page = client.get("/")
            response = client.post("/", data={"topic": "AI marketing"})

        self.assertEqual(page.status_code, 200)
        self.assertRegex(page.get_data(as_text=True), r'name="csrf_token" value="[^"]+"')
        self.assertEqual(response.status_code, 400)
        self.assertIn("security token", response.get_data(as_text=True))

    def test_web_rate_limits_generation_posts_per_client_ip(self) -> None:
        with patch("social_media_agent.web.SocialMediaPostGenerator", return_value=Mock()):
            client = create_app().test_client()
            responses = [
                _post_with_csrf(client, "/", data={"topic": ""})
                for _ in range(11)
            ]

        self.assertTrue(all(response.status_code == 200 for response in responses[:10]))
        self.assertEqual(responses[-1].status_code, 429)

    def test_health_route_reports_application_liveness(self) -> None:
        with patch("social_media_agent.web.SocialMediaPostGenerator", return_value=Mock()):
            response = create_app().test_client().get("/health")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {"status": "ok"})

    def test_readiness_route_reports_failed_production_configuration(self) -> None:
        with patch.dict(
            os.environ,
            {"FLASK_SECRET_KEY": "", "RATELIMIT_STORAGE_URI": "memory://"},
        ), patch("social_media_agent.web.SocialMediaPostGenerator", return_value=Mock()):
            response = create_app().test_client().get("/ready")

        self.assertEqual(response.status_code, 503)
        self.assertEqual(
            response.get_json(),
            {
                "status": "not_ready",
                "checks": {
                    "metrics_storage": True,
                    "upload_storage": True,
                    "session_secret": False,
                    "secure_session_cookie": False,
                    "debug_mode_disabled": True,
                    "shared_rate_limit_storage": False,
                },
            },
        )

    def test_readiness_route_returns_ready_when_required_dependencies_are_healthy(self) -> None:
        with patch("social_media_agent.web.SocialMediaPostGenerator", return_value=Mock()):
            app = create_app()
        limiter = next(iter(app.extensions["limiter"]))
        app.config["PRODUCTION_SECRET_CONFIGURED"] = True
        app.config["SESSION_COOKIE_SECURE"] = True
        app.config["RATELIMIT_SHARED_STORAGE"] = True
        with patch.object(limiter.storage, "check", return_value=True):
            response = app.test_client().get("/ready")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["status"], "ready")
        self.assertTrue(all(response.get_json()["checks"].values()))

    def test_metrics_route_reports_request_count_and_latency_without_scrape_counts(self) -> None:
        with patch("social_media_agent.web.SocialMediaPostGenerator", return_value=Mock()):
            app = create_app()
            client = app.test_client()
            _post_with_csrf(client, "/", data={"topic": ""})

            first_metrics_response = client.get("/metrics")
            first_metrics = first_metrics_response.get_data(as_text=True)
            second_metrics = client.get("/metrics").get_data(as_text=True)

        self.assertEqual(first_metrics_response.status_code, 200)
        self.assertTrue(
            first_metrics_response.content_type.startswith("text/plain"),
            first_metrics_response.content_type,
        )
        self.assertIn(
            'social_media_agent_http_requests_total{method="GET",status_code="200"} 1',
            first_metrics,
        )
        self.assertIn(
            'social_media_agent_http_requests_total{method="POST",status_code="200"} 1',
            first_metrics,
        )
        self.assertIn(
            'social_media_agent_http_request_duration_seconds_count{method="GET",status_code="200"} 1',
            first_metrics,
        )
        self.assertIn(
            'social_media_agent_http_request_duration_seconds_bucket{method="GET",status_code="200",le="+Inf"} 1',
            first_metrics,
        )
        self.assertEqual(first_metrics, second_metrics)
        self.assertNotIn("/metrics", first_metrics)
        self.assertNotIn("topic", first_metrics)

    def test_metrics_persist_across_request_metrics_instances(self) -> None:
        database_path = Path(self.observability_dir.name) / "persistent.sqlite3"
        first_instance = RequestMetrics(database_path)
        first_instance.observe_request("GET", 200, 0.02)
        first_instance.observe_request("POST", 503, 0.3)

        restored_instance = RequestMetrics(database_path)
        output = restored_instance.render_prometheus()

        self.assertIn(
            'social_media_agent_http_requests_total{method="GET",status_code="200"} 1',
            output,
        )
        self.assertIn(
            'social_media_agent_http_request_duration_seconds_sum{method="POST",status_code="503"} 0.300000',
            output,
        )

    def test_persistent_error_reporting_retains_only_recent_events(self) -> None:
        database_path = Path(self.observability_dir.name) / "retained-errors.sqlite3"
        metrics = RequestMetrics(database_path)
        metrics.ERROR_RETENTION_LIMIT = 2
        for request_id in ("first", "second", "third"):
            metrics.report_error(request_id, "GET", "/test", "RuntimeError")

        connection = sqlite3.connect(database_path)
        try:
            retained = connection.execute(
                "SELECT request_id FROM application_errors ORDER BY id"
            ).fetchall()
        finally:
            connection.close()

        self.assertEqual(retained, [("second",), ("third",)])

    def test_unhandled_web_exceptions_are_reported_without_exposing_messages(self) -> None:
        with patch("social_media_agent.web.SocialMediaPostGenerator", return_value=Mock()):
            app = create_app()

        @app.get("/test-unhandled-error")
        def raise_unhandled_error():
            raise RuntimeError("private exception details")

        with self.assertLogs("social_media_agent.web", level="ERROR") as captured:
            response = app.test_client().get("/test-unhandled-error")
        database_path = Path(app.config["OBSERVABILITY_DB_PATH"])
        connection = sqlite3.connect(database_path)
        try:
            error_row = connection.execute(
                "SELECT request_id, method, path, error_type FROM application_errors"
            ).fetchone()
        finally:
            connection.close()

        self.assertEqual(response.status_code, 500)
        self.assertNotIn("private exception details", response.get_data(as_text=True))
        self.assertIn("private exception details", captured.output[0])
        self.assertEqual(error_row[0], response.headers["X-Request-ID"])
        self.assertEqual(error_row[1:], ("GET", "/test-unhandled-error", "RuntimeError"))

    def test_metrics_normalize_unrecognized_methods_to_bound_label(self) -> None:
        metrics = RequestMetrics()
        metrics.observe_request("CUSTOM-UNTRUSTED-METHOD", 200, 0.02)

        output = metrics.render_prometheus()

        self.assertIn('method="OTHER",status_code="200"', output)
        self.assertNotIn("CUSTOM-UNTRUSTED-METHOD", output)

    def test_metrics_histogram_buckets_are_cumulative(self) -> None:
        metrics = RequestMetrics()
        metrics.observe_request("GET", 200, 0.02)

        output = metrics.render_prometheus()

        self.assertIn(
            'social_media_agent_http_request_duration_seconds_bucket{method="GET",status_code="200",le="0.01"} 0',
            output,
        )
        self.assertIn(
            'social_media_agent_http_request_duration_seconds_bucket{method="GET",status_code="200",le="0.025"} 1',
            output,
        )
        self.assertIn(
            'social_media_agent_http_request_duration_seconds_sum{method="GET",status_code="200"} 0.020000',
            output,
        )

    def test_web_logs_request_id_and_status_without_logging_form_content(self) -> None:
        with patch("social_media_agent.web.SocialMediaPostGenerator", return_value=Mock()):
            app = create_app()
            with self.assertLogs("social_media_agent.web", level="INFO") as captured:
                response = app.test_client().get("/")

        self.assertEqual(response.status_code, 200)
        request_events = [json.loads(record.getMessage()) for record in captured.records]
        self.assertEqual(len(request_events), 1)
        event = request_events[0]
        self.assertEqual(event["event"], "http.request")
        self.assertEqual(event["method"], "GET")
        self.assertEqual(event["status_code"], 200)
        self.assertEqual(event["request_id"], response.headers["X-Request-ID"])
        self.assertGreaterEqual(event["duration_ms"], 0)
        self.assertNotIn("topic", event)

    def test_scheduler_logs_job_lifecycle_without_post_configuration(self) -> None:
        generator = Mock()
        generator.generate_post.return_value = {
            "caption": "Generated",
            "generation_source": "local",
        }
        with tempfile.TemporaryDirectory() as tmp_dir:
            scheduler = PeriodicPostScheduler(generator, output_dir=tmp_dir)
            with self.assertLogs("social_media_agent.scheduler", level="INFO") as captured:
                job_id = scheduler.create_job(
                    {"topic": "private topic"},
                    interval_seconds=60,
                    count=1,
                )
                scheduler.run_scheduled_job(job_id)

        events = [json.loads(record.getMessage()) for record in captured.records]
        event_names = [event["event"] for event in events]
        self.assertEqual(
            event_names,
            [
                "scheduler.job_created",
                "scheduler.worker_started",
                "scheduler.iteration_completed",
                "scheduler.worker_stopped",
            ],
        )
        self.assertTrue(all(event.get("job_id") == job_id for event in events))
        self.assertEqual(events[0]["target_count"], 1)
        self.assertEqual(events[2]["completed_count"], 1)
        self.assertEqual(events[2]["status"], "completed")
        self.assertEqual(events[2]["generation_source"], "local")
        self.assertNotIn("private topic", "\n".join(record.getMessage() for record in captured.records))

    def test_scheduler_logs_failure_type_without_error_details(self) -> None:
        generator = Mock()
        generator.generate_post.side_effect = RuntimeError("sensitive provider response")
        with tempfile.TemporaryDirectory() as tmp_dir:
            scheduler = PeriodicPostScheduler(generator, output_dir=tmp_dir)
            job_id = scheduler.create_job(
                {"topic": "topic"},
                interval_seconds=1,
                count=1,
            )
            with patch("social_media_agent.scheduler.time.sleep"), self.assertLogs(
                "social_media_agent.scheduler",
                level="INFO",
            ) as captured, self.assertRaisesRegex(RuntimeError, "sensitive provider response"):
                scheduler.run_scheduled_job(job_id)

        events = [
            json.loads(record.getMessage())
            for record in captured.records
            if record.getMessage().startswith("{")
        ]
        failure_events = [event for event in events if event["event"] == "scheduler.worker_failed"]
        self.assertEqual(len(failure_events), 1)
        self.assertEqual(failure_events[0]["job_id"], job_id)
        self.assertEqual(failure_events[0]["error_type"], "RuntimeError")
        self.assertNotIn("sensitive provider response", "\n".join(
            record.getMessage() for record in captured.records
        ))

    def test_web_signature_validation_covers_all_allowed_media_extensions(self) -> None:
        signatures = {
            ".png": b"\x89PNG\r\n\x1a\n",
            ".jpg": b"\xff\xd8\xff",
            ".jpeg": b"\xff\xd8\xff",
            ".gif": b"GIF89a",
            ".mp4": b"\x00\x00\x00\x18ftypisom",
            ".mov": b"\x00\x00\x00\x18ftypqt  ",
            ".avi": b"RIFF\x00\x00\x00\x00AVI ",
            ".webm": b"\x1a\x45\xdf\xa3\x42\x82\x84webm",
            ".m4v": b"\x00\x00\x00\x18ftypM4V ",
        }

        for extension, signature in signatures.items():
            with self.subTest(extension=extension):
                self.assertTrue(_has_matching_signature(extension, signature))
    def test_web_rejects_invalid_schedule_values(self) -> None:
        app = create_app()
        client = app.test_client()

        response = _post_with_csrf(
            client,
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
        self.assertIn(
            'class="field status-message status-error" role="alert" aria-live="assertive"',
            response_text,
        )
        self.assertTrue(
            "positive" in response_text or "non-negative" in response_text,
            response_text,
        )

    def test_web_generates_post_for_valid_submission(self) -> None:
        with patch.dict(os.environ, {"OPENAI_API_KEY": ""}):
            app = create_app()
            client = app.test_client()

            response = _post_with_csrf(
                client,
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
        self.assertIn(
            "Generated with the local template fallback; external provider output was not used.",
            response_text,
        )

    def test_web_upload_uses_unique_server_filename_and_checks_media_signature(self) -> None:
        generator = Mock()
        generator.generate_post.return_value = {
            "platform": "instagram",
            "media_type": "image",
            "media_filename": None,
            "title": "",
            "description": "",
            "tags": [],
            "caption": "Image post",
            "call_to_action": "",
            "hashtags": [],
        }
        generator.provider = "openai"
        png_data = _make_png()
        with tempfile.TemporaryDirectory() as upload_dir, patch(
            "social_media_agent.web.UPLOAD_FOLDER",
            Path(upload_dir),
        ), patch(
            "social_media_agent.web.SocialMediaPostGenerator",
            return_value=generator,
        ):
            app = create_app()
            client = app.test_client()
            responses = [
                _post_with_csrf(
                    client,
                    "/",
                    data={
                        "topic": "AI marketing",
                        "platform": "instagram",
                        "media_type": "image",
                        "tone": "friendly",
                        "length": "medium",
                        "language": "English",
                        "interval": "",
                        "count": "0",
                        "media_file": (BytesIO(png_data), "../../campaign.png"),
                    },
                    content_type="multipart/form-data",
                )
                for _ in range(2)
            ]

            stored_files = list(Path(upload_dir).iterdir())
            stored_payloads = [path.read_bytes() for path in stored_files]

        self.assertTrue(all(response.status_code == 200 for response in responses))
        self.assertEqual(len(stored_files), 2)
        self.assertNotEqual(stored_files[0].name, stored_files[1].name)
        self.assertTrue(all(path.suffix == ".png" for path in stored_files))
        self.assertTrue(all(len(path.stem) == 32 for path in stored_files))
        self.assertEqual(stored_payloads, [png_data, png_data])
        self.assertTrue(all("../../campaign.png" not in response.get_data(as_text=True) for response in responses))

    def test_web_rejects_upload_with_mismatched_content_without_saving(self) -> None:
        with tempfile.TemporaryDirectory() as upload_dir, patch(
            "social_media_agent.web.UPLOAD_FOLDER",
            Path(upload_dir),
        ), patch(
            "social_media_agent.web.SocialMediaPostGenerator",
            return_value=Mock(),
        ):
            app = create_app()
            response = _post_with_csrf(app.test_client(),
                "/",
                data={
                    "topic": "AI marketing",
                    "platform": "instagram",
                    "media_type": "image",
                    "tone": "friendly",
                    "length": "medium",
                    "language": "English",
                    "interval": "",
                    "count": "0",
                    "media_file": (BytesIO(b"not an image"), "campaign.png"),
                },
                content_type="multipart/form-data",
            )

            stored_files = list(Path(upload_dir).iterdir())

        self.assertEqual(response.status_code, 200)
        self.assertIn("contents do not match", response.get_data(as_text=True))
        self.assertEqual(stored_files, [])

    def test_web_rejects_upload_when_media_type_does_not_match(self) -> None:
        with tempfile.TemporaryDirectory() as upload_dir, patch(
            "social_media_agent.web.UPLOAD_FOLDER",
            Path(upload_dir),
        ), patch(
            "social_media_agent.web.SocialMediaPostGenerator",
            return_value=Mock(),
        ):
            app = create_app()
            response = _post_with_csrf(app.test_client(),
                "/",
                data={
                    "topic": "AI marketing",
                    "platform": "instagram",
                    "media_type": "video",
                    "tone": "friendly",
                    "length": "medium",
                    "language": "English",
                    "interval": "",
                    "count": "0",
                    "media_file": (
                        BytesIO(b"\x89PNG\r\n\x1a\nvalid-signature"),
                        "campaign.png",
                    ),
                },
                content_type="multipart/form-data",
            )

            stored_files = list(Path(upload_dir).iterdir())

        self.assertEqual(response.status_code, 200)
        self.assertIn("must match the selected", response.get_data(as_text=True))
        self.assertEqual(stored_files, [])

    def test_web_does_not_save_upload_when_other_form_validation_fails(self) -> None:
        with tempfile.TemporaryDirectory() as upload_dir, patch(
            "social_media_agent.web.UPLOAD_FOLDER",
            Path(upload_dir),
        ), patch(
            "social_media_agent.web.SocialMediaPostGenerator",
            return_value=Mock(),
        ):
            app = create_app()
            response = _post_with_csrf(app.test_client(),
                "/",
                data={
                    "topic": "",
                    "platform": "instagram",
                    "media_type": "image",
                    "tone": "friendly",
                    "length": "medium",
                    "language": "English",
                    "interval": "",
                    "count": "0",
                    "media_file": (
                        BytesIO(b"\x89PNG\r\n\x1a\nvalid-signature"),
                        "campaign.png",
                    ),
                },
                content_type="multipart/form-data",
            )

            stored_files = list(Path(upload_dir).iterdir())

        self.assertEqual(response.status_code, 200)
        self.assertIn("Topic is required", response.get_data(as_text=True))
        self.assertEqual(stored_files, [])

    def test_web_rejects_multiple_uploads_without_saving(self) -> None:
        with tempfile.TemporaryDirectory() as upload_dir, patch(
            "social_media_agent.web.UPLOAD_FOLDER",
            Path(upload_dir),
        ), patch(
            "social_media_agent.web.SocialMediaPostGenerator",
            return_value=Mock(),
        ):
            app = create_app()
            response = _post_with_csrf(app.test_client(),
                "/",
                data={
                    "topic": "AI marketing",
                    "platform": "instagram",
                    "media_type": "image",
                    "tone": "friendly",
                    "length": "medium",
                    "language": "English",
                    "interval": "",
                    "count": "0",
                    "media_file": [
                        (BytesIO(b"\x89PNG\r\n\x1a\nfirst"), "first.png"),
                        (BytesIO(b"\x89PNG\r\n\x1a\nsecond"), "second.png"),
                    ],
                },
                content_type="multipart/form-data",
            )

            stored_files = list(Path(upload_dir).iterdir())

        self.assertEqual(response.status_code, 200)
        self.assertIn("Upload only one", response.get_data(as_text=True))
        self.assertEqual(stored_files, [])

    def test_web_rejects_upload_larger_than_five_megabytes(self) -> None:
        with tempfile.TemporaryDirectory() as upload_dir, patch(
            "social_media_agent.web.UPLOAD_FOLDER",
            Path(upload_dir),
        ), patch(
            "social_media_agent.web.SocialMediaPostGenerator",
            return_value=Mock(),
        ):
            app = create_app()
            response = _post_with_csrf(app.test_client(),
                "/",
                data={
                    "topic": "AI marketing",
                    "platform": "instagram",
                    "media_type": "image",
                    "tone": "friendly",
                    "length": "medium",
                    "language": "English",
                    "interval": "",
                    "count": "0",
                    "media_file": (
                        BytesIO(b"\x89PNG\r\n\x1a\n" + b"x" * MAX_UPLOAD_BYTES),
                        "campaign.png",
                    ),
                },
                content_type="multipart/form-data",
            )

            stored_files = list(Path(upload_dir).iterdir())

        self.assertEqual(response.status_code, 413)
        response_text = response.get_data(as_text=True)
        self.assertIn("5 MB or smaller", response_text)
        self.assertIn(
            'class="field status-message status-error" role="alert" aria-live="assertive"',
            response_text,
        )
        self.assertEqual(stored_files, [])

    def test_web_accepts_upload_at_five_megabyte_limit(self) -> None:
        generator = Mock()
        generator.generate_post.return_value = {
            "platform": "instagram",
            "media_type": "image",
            "media_filename": None,
            "title": "",
            "description": "",
            "tags": [],
            "caption": "Image post",
            "call_to_action": "",
            "hashtags": [],
        }
        generator.provider = "openai"
        valid_png = _make_png()
        png_data = valid_png + b"x" * (MAX_UPLOAD_BYTES - len(valid_png))
        with tempfile.TemporaryDirectory() as upload_dir, patch(
            "social_media_agent.web.UPLOAD_FOLDER",
            Path(upload_dir),
        ), patch(
            "social_media_agent.web.SocialMediaPostGenerator",
            return_value=generator,
        ):
            app = create_app()
            response = _post_with_csrf(app.test_client(),
                "/",
                data={
                    "topic": "AI marketing",
                    "platform": "instagram",
                    "media_type": "image",
                    "tone": "friendly",
                    "length": "medium",
                    "language": "English",
                    "interval": "",
                    "count": "0",
                    "media_file": (BytesIO(png_data), "campaign.png"),
                },
                content_type="multipart/form-data",
            )
            stored_files = list(Path(upload_dir).iterdir())
            stored_sizes = [path.stat().st_size for path in stored_files]

        self.assertEqual(response.status_code, 200)
        self.assertEqual(stored_sizes, [MAX_UPLOAD_BYTES])

    def test_web_creates_persistent_job_and_starts_worker_for_schedule(self) -> None:
        scheduler = Mock()
        scheduler.create_job.return_value = "scheduled-job-id"
        worker_thread = Mock()
        with patch.dict(os.environ, {"OPENAI_API_KEY": ""}), patch(
            "social_media_agent.web.PeriodicPostScheduler",
            return_value=scheduler,
        ) as scheduler_class, patch(
            "social_media_agent.web.Thread",
            return_value=worker_thread,
        ) as thread_class, tempfile.TemporaryDirectory() as output_dir:
            app = create_app()
            client = app.test_client()
            response = _post_with_csrf(
                client,
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
        response_text = response.get_data(as_text=True)
        self.assertIn("scheduled-job-id", response_text)
        self.assertIn(
            'class="field status-message status-success" role="status" aria-live="polite"',
            response_text,
        )
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
            "generation_source": "local",
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
            self.assertEqual(payload["generation_source"], "local")
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

    def test_cli_identifies_local_fallback_in_generated_output(self) -> None:
        generator = Mock()
        generator.provider_model = "test-model"
        generator.generate_post.return_value = {
            "generation_source": "local",
            "platform": "instagram",
            "tone": "friendly",
            "language": "English",
            "topic": "AI marketing",
            "media_type": "text",
            "media_filename": None,
            "title": "",
            "description": "",
            "tags": [],
            "caption": "Local caption",
            "hashtags": ["marketing"],
            "call_to_action": "",
        }
        output = StringIO()
        with patch.object(
            sys,
            "argv",
            ["app.py", "--topic", "AI marketing"],
        ), patch.object(
            cli_module,
            "SocialMediaPostGenerator",
            return_value=generator,
        ), redirect_stdout(output):
            cli_module.main()

        self.assertIn("Generation source: Local template fallback", output.getvalue())
        self.assertNotIn("Provider: Openai", output.getvalue())
        self.assertNotIn("Model: test-model", output.getvalue())

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
