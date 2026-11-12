import os
import re
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from social_media_agent.accounts import AccountStore
from social_media_agent.web import create_app
from wsgi import create_wsgi_app


def _token_from(response) -> str:
    match = re.search(
        r'name="csrf_token" value="([^"]+)"',
        response.get_data(as_text=True),
    )
    if match is None:
        raise AssertionError("Expected a CSRF token in the response.")
    return match.group(1)


class MultiUserAuthenticationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.root = Path(self.temporary_directory.name)
        self.database_path = self.root / "accounts.sqlite3"
        self.output_root = self.root / "scheduled_posts"
        self.upload_root = self.root / "uploads"
        self.environment = patch.dict(
            os.environ,
            {
                "MULTI_USER_AUTH_ENABLED": "true",
                "AUTH_DATABASE_PATH": str(self.database_path),
                "SCHEDULED_OUTPUT_ROOT": str(self.output_root),
                "SCHEDULER_DB_PATH": "",
                "OBSERVABILITY_DB_PATH": str(self.root / "observability.sqlite3"),
                "RATELIMIT_STORAGE_URI": "memory://",
                "FLASK_SECRET_KEY": "x" * 64,
                "WEB_AUTH_USERNAME": "",
                "WEB_AUTH_PASSWORD": "",
                "WEB_AUTH_PASSWORD_FILE": "",
                "PROMETHEUS_USERNAME": "",
                "PROMETHEUS_PASSWORD": "",
                "PROMETHEUS_PASSWORD_FILE": "",
                "SENTRY_DSN": "",
            },
        )
        self.environment.start()
        self.addCleanup(self.environment.stop)
        self.upload_patch = patch(
            "social_media_agent.web.UPLOAD_FOLDER",
            self.upload_root,
        )
        self.upload_patch.start()
        self.addCleanup(self.upload_patch.stop)
        self.generator_patch = patch(
            "social_media_agent.web.SocialMediaPostGenerator",
            return_value=Mock(),
        )
        self.generator_patch.start()
        self.addCleanup(self.generator_patch.stop)
        self.app = create_app()
        self.app.config["TESTING"] = True
        self.store = AccountStore(str(self.database_path))

    def _create_admin(self, username="admin", password="admin-password-long"):
        self.store.create_initial_admin(username, password)

    def _login(self, client, username, password):
        response = client.get("/login")
        return client.post(
            "/login",
            data={
                "csrf_token": _token_from(response),
                "username": username,
                "password": password,
            },
            follow_redirects=False,
        )

    def test_invite_signup_role_enforcement_and_account_disable(self) -> None:
        self._create_admin()
        admin_client = self.app.test_client()
        self._login(admin_client, "admin", "admin-password-long")

        page = admin_client.get("/admin/users")
        invitation = admin_client.post(
            "/admin/invitations",
            data={
                "csrf_token": _token_from(page),
                "role": "user",
            },
        )
        token_match = re.search(
            r'<textarea id="new-invitation" rows="3" readonly>([^<]+)</textarea>',
            invitation.get_data(as_text=True),
        )
        self.assertIsNotNone(token_match)
        token = token_match.group(1)

        invitee_client = self.app.test_client()
        invitation_page = invitee_client.get("/accept-invitation")
        accepted = invitee_client.post(
            "/accept-invitation",
            data={
                "csrf_token": _token_from(invitation_page),
                "invitation": token,
                "username": "writer",
                "password": "writer-password-long",
                "confirm_password": "writer-password-long",
            },
        )
        self.assertEqual(accepted.status_code, 302)
        self.assertEqual(
            invitee_client.post(
                "/accept-invitation",
                data={
                    "csrf_token": _token_from(invitee_client.get("/accept-invitation")),
                    "invitation": token,
                    "username": "second",
                    "password": "second-password-long",
                    "confirm_password": "second-password-long",
                },
            ).status_code,
            400,
        )

        self._login(invitee_client, "writer", "writer-password-long")
        self.assertEqual(invitee_client.get("/admin/users").status_code, 403)
        self.assertEqual(
            invitee_client.get("/").status_code,
            200,
        )

        users_page = admin_client.get("/admin/users")
        writer_id = next(
            int(user["id"])
            for user in self.store.list_users()
            if user["username"] == "writer"
        )
        disabled = admin_client.post(
            f"/admin/users/{writer_id}/status",
            data={
                "csrf_token": _token_from(users_page),
                "active": "false",
            },
        )
        self.assertEqual(disabled.status_code, 200)
        self.assertEqual(invitee_client.get("/").headers["Location"], "/login")

        with self.assertRaisesRegex(ValueError, "last active administrator"):
            self.store.set_user_status(1, False)

    def test_scheduler_records_owner_and_uses_per_user_output_root(self) -> None:
        self._create_admin()
        client = self.app.test_client()
        self._login(client, "admin", "admin-password-long")

        page = client.get("/")
        with patch("social_media_agent.web.Thread") as thread_class:
            response = client.post(
                "/",
                data={
                    "csrf_token": _token_from(page),
                    "topic": "First user's topic",
                    "interval": "1h",
                    "count": "1",
                },
            )
        self.assertEqual(response.status_code, 200)
        self.assertTrue((self.output_root / "users" / "1").is_dir())
        self.assertEqual(thread_class.call_count, 1)

        connection = sqlite3.connect(str(self.output_root / "scheduler.sqlite3"))
        try:
            row = connection.execute(
                "SELECT owner_id, output_dir FROM scheduled_jobs"
            ).fetchone()
        finally:
            connection.close()
        self.assertEqual(row[0], 1)
        self.assertEqual(
            Path(row[1]).resolve(),
            (self.output_root / "users" / "1").resolve(),
        )

    def test_user_cannot_choose_another_users_output_directory(self) -> None:
        self._create_admin()
        client = self.app.test_client()
        self._login(client, "admin", "admin-password-long")
        page = client.get("/")

        response = client.post(
            "/",
            data={
                "csrf_token": _token_from(page),
                "topic": "Path traversal attempt",
                "interval": "1h",
                "scheduled_output": "../2",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn(
            "within the configured output root",
            response.get_data(as_text=True),
        )
        self.assertFalse((self.output_root / "users" / "2").exists())

    def test_wsgi_accepts_multi_user_auth_without_legacy_shared_password(self) -> None:
        with patch.dict(
            os.environ,
            {
                "RATELIMIT_STORAGE_URI": "redis://localhost:6379/0",
                "PROMETHEUS_USERNAME": "prometheus",
                "PROMETHEUS_PASSWORD": "metrics-password-long",
            },
        ), patch("social_media_agent.web.Limiter") as limiter_factory:
            limiter = Mock()
            limiter.exempt.side_effect = lambda function: function
            limiter.limit.return_value = lambda function: function
            limiter_factory.return_value = limiter
            app = create_wsgi_app()
        self.assertTrue(app.config["MULTI_USER_AUTH_ENABLED"])
        self.assertTrue(app.config["AUTHENTICATION_CONFIGURED"])
        self.assertEqual(app.config["WEB_AUTH_PASSWORD"], "")


if __name__ == "__main__":
    unittest.main()
