import ipaddress
import logging
import os
import secrets
import sqlite3
import tempfile
import time
import uuid
from datetime import timedelta
from pathlib import Path
from threading import Thread
from typing import Callable, Union

from flask import Flask, Response, g, jsonify, redirect, render_template, request, session, url_for
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_wtf.csrf import CSRFError, CSRFProtect
from werkzeug.exceptions import Forbidden, NotFound
from werkzeug.datastructures import FileStorage
from werkzeug.exceptions import HTTPException, RequestEntityTooLarge
from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.utils import secure_filename

from .generator import SocialMediaPostGenerator
from .accounts import AccountStore
from .media_analysis import MediaAnalysisError, analyze_media, scan_for_malware
from .observability import (
    RequestMetrics,
    SchedulerMetrics,
    capture_sentry_exception,
    configure_logging,
    configure_sentry,
    log_event,
    log_exception_event,
    log_warning_event,
)
from .scheduler import PeriodicPostScheduler, parse_count, parse_interval

logger = logging.getLogger(__name__)

WEB_SESSION_MAX_AGE_SECONDS = 12 * 60 * 60
PLATFORMS = ["instagram", "linkedin", "twitter", "facebook", "youtube", "youtube_shorts"]
MEDIA_TYPES = ["text", "image", "video"]
TONES = ["friendly", "professional", "motivational", "funny", "educational"]
LENGTHS = ["short", "medium", "long"]
LANGUAGES = ["English", "Spanish", "French", "Turkish"]
UPLOAD_FOLDER = Path(__file__).resolve().parent.parent / "uploads"
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "mp4", "mov", "avi", "webm", "m4v"}
IMAGE_EXTENSIONS = {"png", "jpg", "jpeg", "gif"}
VIDEO_EXTENSIONS = {"mp4", "mov", "avi", "webm", "m4v"}
MAX_UPLOAD_BYTES = 5 * 1024 * 1024
MAX_REQUEST_BYTES = MAX_UPLOAD_BYTES + 256 * 1024


def allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def _has_matching_signature(extension: str, header: bytes) -> bool:
    image_signatures = {
        ".png": header.startswith(b"\x89PNG\r\n\x1a\n"),
        ".jpg": header.startswith(b"\xff\xd8\xff"),
        ".jpeg": header.startswith(b"\xff\xd8\xff"),
        ".gif": header.startswith((b"GIF87a", b"GIF89a")),
    }
    if extension in image_signatures:
        return image_signatures[extension]
    if extension == ".avi":
        return len(header) >= 12 and header.startswith(b"RIFF") and header[8:12] == b"AVI "
    if extension == ".webm":
        return header.startswith(b"\x1a\x45\xdf\xa3") and b"\x42\x82\x84webm" in header
    if extension in {".mp4", ".mov", ".m4v"}:
        if len(header) < 12 or header[4:8] != b"ftyp":
            return False
        brand = header[8:12]
        if extension == ".mov":
            return brand == b"qt  "
        if extension == ".m4v":
            return brand == b"M4V "
        return brand in {b"isom", b"iso2", b"mp41", b"mp42", b"avc1"}
    return False


def _save_uploaded_media(
    media_file: FileStorage,
    upload_folder: Path,
    media_type: str,
) -> str:
    safe_name = secure_filename(media_file.filename or "")
    extension = Path(safe_name).suffix.lower()
    extension_without_dot = extension.lstrip(".")
    if not safe_name or not allowed_file(safe_name):
        raise ValueError("Unsupported media file type. Allowed types: images and common video files.")

    if extension_without_dot in IMAGE_EXTENSIONS:
        expected_type = "image"
    elif extension_without_dot in VIDEO_EXTENSIONS:
        expected_type = "video"
    else:
        expected_type = None
    if media_type != expected_type:
        raise ValueError("Uploaded file extension must match the selected image or video media type.")

    size = 0
    while True:
        chunk = media_file.stream.read(64 * 1024)
        if not chunk:
            break
        size += len(chunk)
        if size > MAX_UPLOAD_BYTES:
            media_file.stream.seek(0)
            raise RequestEntityTooLarge()
    media_file.stream.seek(0)

    header = media_file.stream.read(4096)
    media_file.stream.seek(0)
    if not _has_matching_signature(extension, header):
        raise ValueError("Uploaded file contents do not match the selected file extension.")

    upload_folder.mkdir(parents=True, exist_ok=True)
    stored_name = f"{uuid.uuid4().hex}{extension}"
    stored_path = upload_folder / stored_name
    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=upload_folder,
            prefix=".upload-",
            suffix=".tmp",
            delete=False,
        ) as temporary_file:
            temporary_path = Path(temporary_file.name)
            media_file.save(temporary_file)
        os.replace(temporary_path, stored_path)
        temporary_path = None
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
    return stored_name


def _resolve_scheduled_output(value: str, output_root: Path) -> Path:
    root = output_root.expanduser().resolve()
    requested_path = Path(value).expanduser() if value else Path(".")
    candidate = requested_path if requested_path.is_absolute() else root / requested_path
    try:
        resolved = candidate.resolve()
        resolved.relative_to(root)
    except (OSError, RuntimeError, ValueError) as error:
        raise ValueError(
            "Scheduled output folder must be within the configured output root."
        ) from error
    return resolved


def _request_route() -> str:
    return request.url_rule.rule if request.url_rule is not None else "<unmatched>"


def _configured_secret(name: str) -> str:
    value = os.environ.get(name, "")
    file_path = os.environ.get(f"{name}_FILE", "").strip()
    if value and file_path:
        raise RuntimeError(f"Configure only one of {name} and {name}_FILE.")
    if not file_path:
        return value
    try:
        secret = Path(file_path).expanduser().read_text(encoding="utf-8").rstrip("\r\n")
    except OSError as error:
        raise RuntimeError(f"Unable to read configured {name}_FILE.") from error
    if not secret:
        raise RuntimeError(f"Configured {name}_FILE is empty.")
    return secret


class _TrustedProxyMiddleware:
    def __init__(
        self,
        app: Callable,
        trusted_proxy_ip: Union[ipaddress.IPv4Address, ipaddress.IPv6Address],
    ) -> None:
        self.app = app
        self.trusted_proxy_ip = trusted_proxy_ip

    def __call__(self, environ, start_response):
        try:
            peer_ip = ipaddress.ip_address(environ.get("REMOTE_ADDR", ""))
        except ValueError:
            peer_ip = None
        if peer_ip != self.trusted_proxy_ip:
            for name in (
                "HTTP_X_FORWARDED_FOR",
                "HTTP_X_FORWARDED_HOST",
                "HTTP_X_FORWARDED_PROTO",
            ):
                environ.pop(name, None)
        return self.app(environ, start_response)


def create_app() -> Flask:
    app = Flask(__name__, template_folder="templates")
    multi_user_auth_enabled = os.environ.get(
        "MULTI_USER_AUTH_ENABLED", ""
    ).lower() in {"1", "true", "yes"}
    configured_secret = _configured_secret("FLASK_SECRET_KEY")
    auth_username = "" if multi_user_auth_enabled else os.environ.get("WEB_AUTH_USERNAME", "")
    auth_password = "" if multi_user_auth_enabled else _configured_secret("WEB_AUTH_PASSWORD")
    prometheus_username = os.environ.get("PROMETHEUS_USERNAME", "")
    prometheus_password = _configured_secret("PROMETHEUS_PASSWORD")
    if (
        not multi_user_auth_enabled
        and bool(auth_username) != bool(auth_password)
    ):
        raise RuntimeError(
            "WEB_AUTH_USERNAME and WEB_AUTH_PASSWORD must be configured together."
        )
    if not multi_user_auth_enabled and auth_password and len(auth_password) < 16:
        raise RuntimeError("WEB_AUTH_PASSWORD must be at least 16 characters long.")
    if bool(prometheus_username) != bool(prometheus_password):
        raise RuntimeError(
            "PROMETHEUS_USERNAME and PROMETHEUS_PASSWORD must be configured together."
        )
    if prometheus_password and len(prometheus_password) < 16:
        raise RuntimeError("PROMETHEUS_PASSWORD must be at least 16 characters long.")
    try:
        trusted_proxy_hops = int(os.environ.get("TRUSTED_PROXY_HOPS", "0"))
    except ValueError as error:
        raise RuntimeError("TRUSTED_PROXY_HOPS must be a non-negative integer.") from error
    if trusted_proxy_hops < 0:
        raise RuntimeError("TRUSTED_PROXY_HOPS must be a non-negative integer.")
    trusted_proxy_value = os.environ.get("TRUSTED_PROXY_IP", "").strip()
    if trusted_proxy_hops and not trusted_proxy_value:
        raise RuntimeError(
            "TRUSTED_PROXY_IP must identify the proxy when TRUSTED_PROXY_HOPS is set."
        )
    if trusted_proxy_value and not trusted_proxy_hops:
        raise RuntimeError("TRUSTED_PROXY_HOPS must be set when TRUSTED_PROXY_IP is configured.")
    try:
        trusted_proxy_ip = (
            ipaddress.ip_address(trusted_proxy_value) if trusted_proxy_value else None
        )
    except ValueError as error:
        raise RuntimeError("TRUSTED_PROXY_IP must be a valid IP address.") from error
    limiter_storage_uri = os.environ.get("RATELIMIT_STORAGE_URI", "memory://")
    secure_session_cookie = os.environ.get("SESSION_COOKIE_SECURE", "").lower() in {
        "1",
        "true",
        "yes",
    }
    app.config.update(
        SECRET_KEY=configured_secret or secrets.token_hex(32),
        PRODUCTION_SECRET_CONFIGURED=len(configured_secret.encode("utf-8")) >= 32,
        WEB_AUTH_USERNAME=auth_username,
        WEB_AUTH_PASSWORD=auth_password,
        MULTI_USER_AUTH_ENABLED=multi_user_auth_enabled,
        AUTHENTICATION_CONFIGURED=(
            multi_user_auth_enabled or bool(auth_username and auth_password)
        ),
        PROMETHEUS_USERNAME=prometheus_username,
        PROMETHEUS_PASSWORD=prometheus_password,
        PROMETHEUS_AUTH_CONFIGURED=bool(prometheus_username and prometheus_password),
        TRUSTED_PROXY_HOPS=trusted_proxy_hops,
        TRUSTED_PROXY_IP=str(trusted_proxy_ip) if trusted_proxy_ip else "",
        RATELIMIT_STORAGE_URI=limiter_storage_uri,
        RATELIMIT_SHARED_STORAGE=not limiter_storage_uri.startswith("memory://"),
        SESSION_COOKIE_NAME="__Host-session" if secure_session_cookie else "session",
        SESSION_COOKIE_SECURE=secure_session_cookie,
        SESSION_COOKIE_PATH="/",
        SESSION_COOKIE_DOMAIN=None,
        OBSERVABILITY_DB_PATH=os.environ.get(
            "OBSERVABILITY_DB_PATH",
            str(Path.cwd() / "scheduled_posts" / "observability.sqlite3"),
        ),
        SCHEDULED_OUTPUT_ROOT=str(
            Path(
                os.environ.get(
                    "SCHEDULED_OUTPUT_ROOT",
                    str(Path.cwd() / "scheduled_posts"),
                )
            ).expanduser().resolve()
        ),
        SCHEDULER_DB_PATH=os.environ.get("SCHEDULER_DB_PATH", "").strip(),
        AUTH_DATABASE_PATH=os.environ.get(
            "AUTH_DATABASE_PATH",
            str(
                Path(
                    os.environ.get(
                        "SCHEDULED_OUTPUT_ROOT",
                        str(Path.cwd() / "scheduled_posts"),
                    )
                ).expanduser().resolve()
                / "accounts.sqlite3"
            ),
        ),
        SENTRY_DSN=os.environ.get("SENTRY_DSN", ""),
        SENTRY_ENVIRONMENT=os.environ.get("SENTRY_ENVIRONMENT", "development"),
        RATELIMIT_HEADERS_ENABLED=True,
        PERMANENT_SESSION_LIFETIME=timedelta(seconds=WEB_SESSION_MAX_AGE_SECONDS),
        SESSION_REFRESH_EACH_REQUEST=False,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
    )
    if trusted_proxy_ip:
        app.wsgi_app = _TrustedProxyMiddleware(
            ProxyFix(
                app.wsgi_app,
                x_for=trusted_proxy_hops,
                x_proto=trusted_proxy_hops,
                x_host=trusted_proxy_hops,
            ),
            trusted_proxy_ip,
        )
    app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
    app.config["MAX_CONTENT_LENGTH"] = MAX_REQUEST_BYTES
    limiter = Limiter(
        key_func=get_remote_address,
        app=app,
        default_limits=["120 per hour"],
        storage_uri=app.config["RATELIMIT_STORAGE_URI"],
    )
    csrf = CSRFProtect()
    csrf.init_app(app)
    app.config["SENTRY_ENABLED"] = configure_sentry(
        app.config["SENTRY_DSN"],
        app.config["SENTRY_ENVIRONMENT"],
    )
    UPLOAD_FOLDER.mkdir(parents=True, exist_ok=True)
    account_store = (
        AccountStore(app.config["AUTH_DATABASE_PATH"])
        if multi_user_auth_enabled
        else None
    )
    generator = SocialMediaPostGenerator()
    request_metrics = RequestMetrics(Path(app.config["OBSERVABILITY_DB_PATH"]))
    scheduler_database_path = app.config["SCHEDULER_DB_PATH"] or str(
        Path(app.config["SCHEDULED_OUTPUT_ROOT"]) / "scheduler.sqlite3"
    )
    scheduler_metrics = SchedulerMetrics(Path(scheduler_database_path))

    def default_form_values():
        return {
            "topic": "",
            "platform": "instagram",
            "media_type": "text",
            "media_filename": "",
            "tone": "friendly",
            "length": "medium",
            "language": "English",
            "interval": "",
            "count": 0,
            "scheduled_output": "." if multi_user_auth_enabled else "",
            "provider_vision": False,
        }

    @app.before_request
    def start_request_logging() -> None:
        g.request_id = uuid.uuid4().hex
        g.request_started_at = time.perf_counter()

    def authenticated_session_is_valid() -> bool:
        if session.get("authenticated") is not True:
            return False
        authenticated_at = session.get("authenticated_at")
        if not isinstance(authenticated_at, (int, float)):
            session.clear()
            return False
        session_age = time.time() - authenticated_at
        if session_age < 0 or session_age >= WEB_SESSION_MAX_AGE_SECONDS:
            session.clear()
            return False
        if multi_user_auth_enabled:
            user_id = session.get("user_id")
            if not isinstance(user_id, int) or account_store is None:
                session.clear()
                return False
            user = account_store.get_user(user_id)
            if user is None:
                session.clear()
                return False
            g.current_user = user
        return True

    @app.before_request
    def require_authentication():
        if request.endpoint == "metrics" and app.config["PROMETHEUS_AUTH_CONFIGURED"]:
            authorization = request.authorization
            if authorization is not None:
                username_matches = secrets.compare_digest(
                    (authorization.username or "").encode("utf-8"),
                    app.config["PROMETHEUS_USERNAME"].encode("utf-8"),
                )
                password_matches = secrets.compare_digest(
                    (authorization.password or "").encode("utf-8"),
                    app.config["PROMETHEUS_PASSWORD"].encode("utf-8"),
                )
                if username_matches and password_matches:
                    return None
            if (
                not app.config["AUTHENTICATION_CONFIGURED"]
                or not authenticated_session_is_valid()
            ):
                response = Response(status=401)
                response.headers["WWW-Authenticate"] = 'Basic realm="metrics"'
                return response
        if not app.config["AUTHENTICATION_CONFIGURED"]:
            return None
        if request.endpoint in {
            "login",
            "accept_invitation",
            "health",
            "readiness",
            "static",
        }:
            return None
        if authenticated_session_is_valid():
            if request.endpoint in {
                "admin_users",
                "create_invitation",
                "set_user_role",
                "set_user_status",
            } and getattr(g, "current_user", {}).get("role") != "admin":
                raise Forbidden()
            return None
        return redirect(url_for("login"))

    @app.after_request
    def add_security_headers(response: Response) -> Response:
        if response.mimetype == "text/html":
            response.headers["Cache-Control"] = "no-store"
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; base-uri 'self'; object-src 'none'; "
            "frame-ancestors 'none'; form-action 'self'; img-src 'self' data:; "
            "style-src 'self'; script-src 'self'",
        )
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault(
            "Referrer-Policy",
            "strict-origin-when-cross-origin",
        )
        response.headers.setdefault(
            "Permissions-Policy",
            "camera=(), microphone=(), geolocation=()",
        )
        if request.is_secure:
            response.headers.setdefault(
                "Strict-Transport-Security",
                "max-age=31536000",
            )
        return response

    @app.after_request
    def log_request(response):
        request_id = getattr(g, "request_id", None)
        if request_id is not None:
            response.headers["X-Request-ID"] = request_id
            duration_ms = round((time.perf_counter() - g.request_started_at) * 1000, 2)
            if request.endpoint != "metrics":
                try:
                    request_metrics.observe_request(
                        request.method,
                        response.status_code,
                        duration_ms / 1000,
                    )
                except sqlite3.Error as error:
                    log_event(
                        logger,
                        "http.metrics_persist_failed",
                        request_id=request_id,
                        error_type=type(error).__name__,
                    )
                log_event(
                    logger,
                    "http.request",
                    request_id=request_id,
                    method=request.method,
                    route=_request_route(),
                    status_code=response.status_code,
                    duration_ms=duration_ms,
                )
        return response

    @app.get("/metrics")
    @limiter.exempt
    def metrics() -> Response:
        return Response(
            request_metrics.render_prometheus() + scheduler_metrics.render_prometheus(),
            content_type="text/plain; version=0.0.4; charset=utf-8",
        )

    @app.get("/health")
    @limiter.exempt
    def health() -> Response:
        return jsonify(status="ok")

    @app.get("/ready")
    @limiter.exempt
    def readiness() -> Response:
        def check(name: str, operation: Callable[[], bool]) -> bool:
            try:
                return bool(operation())
            except Exception as error:
                log_event(
                    logger,
                    "readiness.check_failed",
                    check=name,
                    error_type=type(error).__name__,
                )
                return False

        def upload_storage_is_writable() -> bool:
            with tempfile.TemporaryFile(dir=app.config["UPLOAD_FOLDER"]):
                return True

        def scheduled_output_storage_is_writable() -> bool:
            output_root = Path(app.config["SCHEDULED_OUTPUT_ROOT"])
            output_root.mkdir(parents=True, exist_ok=True)
            with tempfile.TemporaryFile(dir=output_root):
                return True

        checks = {
            "metrics_storage": check("metrics_storage", request_metrics.check_storage),
            "upload_storage": check("upload_storage", upload_storage_is_writable),
            "scheduled_output_storage": check(
                "scheduled_output_storage",
                scheduled_output_storage_is_writable,
            ),
            "authentication_configured": bool(app.config["AUTHENTICATION_CONFIGURED"]),
            "prometheus_auth_configured": bool(
                app.config["PROMETHEUS_AUTH_CONFIGURED"]
            ),
            "session_secret": bool(app.config["PRODUCTION_SECRET_CONFIGURED"]),
            "secure_session_cookie": bool(app.config["SESSION_COOKIE_SECURE"]),
            "debug_mode_disabled": not app.debug,
            "shared_rate_limit_storage": bool(
                app.config["RATELIMIT_SHARED_STORAGE"]
                and check("shared_rate_limit_storage", limiter.storage.check)
            ),
        }
        if multi_user_auth_enabled and account_store is not None:
            checks["accounts_storage"] = check(
                "accounts_storage",
                account_store.check_storage,
            )
        ready = all(checks.values())
        response_data: dict[str, object] = {
            "status": "ready" if ready else "not_ready"
        }
        if (
            not app.config["AUTHENTICATION_CONFIGURED"]
            or authenticated_session_is_valid()
        ):
            response_data["checks"] = checks
        return jsonify(response_data), 200 if ready else 503

    @app.errorhandler(RequestEntityTooLarge)
    def handle_request_too_large(_error: RequestEntityTooLarge):
        return render_template(
            "index.html",
            post=None,
            status_message="The request is too large. Uploaded files must be 5 MB or smaller.",
            status_type="error",
            values=default_form_values(),
            platforms=PLATFORMS,
            media_types=MEDIA_TYPES,
            tones=TONES,
            lengths=LENGTHS,
            languages=LANGUAGES,
        ), _error.code or 413

    @app.errorhandler(CSRFError)
    def handle_csrf_error(_error: CSRFError):
        return "The form security token is missing or invalid. Reload the page and try again.", 400

    @app.errorhandler(Exception)
    def handle_unexpected_error(error: Exception):
        if isinstance(error, HTTPException):
            return error.get_response()

        request_id = getattr(g, "request_id", uuid.uuid4().hex)
        error_fields = {
            "request_id": request_id,
            "method": request.method,
            "path": _request_route(),
            "error_type": type(error).__name__,
        }
        log_exception_event(logger, "http.unhandled_exception", **error_fields)
        if app.config["SENTRY_ENABLED"]:
            try:
                capture_sentry_exception(error, request_id)
            except Exception as reporting_error:
                log_event(
                    logger,
                    "http.sentry_capture_failed",
                    request_id=request_id,
                    error_type=type(reporting_error).__name__,
                )
        try:
            request_metrics.report_error(**error_fields)
        except sqlite3.Error as persistence_error:
            log_event(
                logger,
                "http.error_persist_failed",
                request_id=request_id,
                error_type=type(persistence_error).__name__,
            )
        return (
            f"An unexpected error occurred. Reference: {request_id}",
            500,
            {"Content-Type": "text/plain; charset=utf-8"},
        )

    @app.route("/login", methods=["GET", "POST"])
    @limiter.limit("5 per minute", methods=["POST"], override_defaults=False)
    def login():
        if not app.config["AUTHENTICATION_CONFIGURED"]:
            return redirect(url_for("index"))
        if authenticated_session_is_valid():
            return redirect(url_for("index"))

        error_message = None
        if request.method == "POST":
            username = request.form.get("username", "")
            password = request.form.get("password", "")
            if multi_user_auth_enabled:
                user = account_store.authenticate(username, password) if account_store else None
                authenticated = user is not None
            else:
                username_matches = secrets.compare_digest(
                    username.encode("utf-8"),
                    app.config["WEB_AUTH_USERNAME"].encode("utf-8"),
                )
                password_matches = secrets.compare_digest(
                    password.encode("utf-8"),
                    app.config["WEB_AUTH_PASSWORD"].encode("utf-8"),
                )
                authenticated = username_matches and password_matches
                user = None
            if authenticated:
                session.clear()
                session.permanent = True
                session["authenticated"] = True
                session["authenticated_at"] = time.time()
                if user is not None:
                    session["user_id"] = user["id"]
                log_event(
                    logger,
                    "auth.login_succeeded",
                    request_id=g.request_id,
                )
                return redirect(url_for("index"))
            log_warning_event(
                logger,
                "auth.login_failed",
                request_id=g.request_id,
            )
            error_message = "Invalid username or password."

        return render_template(
            "login.html",
            error_message=error_message,
            multi_user=multi_user_auth_enabled,
        ), (
            401 if error_message else 200
        )

    @app.route("/accept-invitation", methods=["GET", "POST"])
    @limiter.limit("5 per minute", methods=["POST"], override_defaults=False)
    def accept_invitation():
        if not multi_user_auth_enabled or account_store is None:
            raise NotFound()
        error_message = None
        if request.method == "POST":
            token = request.form.get("invitation", "").strip()
            password = request.form.get("password", "")
            confirmation = request.form.get("confirm_password", "")
            if password != confirmation:
                error_message = "Passwords do not match."
            else:
                try:
                    account_store.accept_invitation(
                        token,
                        request.form.get("username", ""),
                        password,
                    )
                    return redirect(url_for("login"))
                except ValueError as error:
                    error_message = str(error)
        return render_template(
            "accept_invitation.html",
            error_message=error_message,
        ), (400 if error_message else 200)

    @app.get("/admin/users")
    def admin_users():
        if not multi_user_auth_enabled or account_store is None:
            raise NotFound()
        return render_template(
            "admin_users.html",
            users=account_store.list_users(),
            current_user_id=int(g.current_user["id"]),
            invitation_token=None,
            status_message=None,
            status_type=None,
        )

    @app.post("/admin/invitations")
    def create_invitation():
        if not multi_user_auth_enabled or account_store is None:
            raise NotFound()
        try:
            token = account_store.create_invitation(
                request.form.get("role", ""),
                int(g.current_user["id"]),
            )
        except ValueError as error:
            return render_template(
                "admin_users.html",
                users=account_store.list_users(),
                current_user_id=int(g.current_user["id"]),
                invitation_token=None,
                status_message=str(error),
                status_type="error",
            ), 400
        return render_template(
            "admin_users.html",
            users=account_store.list_users(),
            current_user_id=int(g.current_user["id"]),
            invitation_token=token,
            status_message="Share this one-time invitation token with the new user. It expires in 24 hours.",
            status_type="success",
        )

    @app.post("/admin/users/<int:user_id>/role")
    def set_user_role(user_id: int):
        if not multi_user_auth_enabled or account_store is None:
            raise NotFound()
        try:
            account_store.set_user_role(user_id, request.form.get("role", ""))
            status_message = "User role updated."
            status_type = "success"
        except ValueError as error:
            status_message = str(error)
            status_type = "error"
        return render_template(
            "admin_users.html",
            users=account_store.list_users(),
            current_user_id=int(g.current_user["id"]),
            invitation_token=None,
            status_message=status_message,
            status_type=status_type,
        ), (400 if status_type == "error" else 200)

    @app.post("/admin/users/<int:user_id>/status")
    def set_user_status(user_id: int):
        if not multi_user_auth_enabled or account_store is None:
            raise NotFound()
        try:
            active = request.form.get("active") == "true"
            account_store.set_user_status(user_id, active)
            status_message = "User status updated."
            status_type = "success"
        except ValueError as error:
            status_message = str(error)
            status_type = "error"
        return render_template(
            "admin_users.html",
            users=account_store.list_users(),
            current_user_id=int(g.current_user["id"]),
            invitation_token=None,
            status_message=status_message,
            status_type=status_type,
        ), (400 if status_type == "error" else 200)

    @app.post("/logout")
    def logout():
        session.clear()
        return redirect(url_for("login" if app.config["AUTHENTICATION_CONFIGURED"] else "index"))

    @app.route("/", methods=["GET", "POST"])
    @limiter.limit("10 per minute", methods=["POST"], override_defaults=False)
    def index():
        post = None
        values = default_form_values()
        status_message = None
        status_type = None
        media_analysis = None

        if request.method == "POST":
            values["topic"] = request.form.get("topic", "").strip()
            values["platform"] = request.form.get("platform", "instagram")
            values["media_type"] = request.form.get("media_type", "text")
            values["tone"] = request.form.get("tone", "friendly")
            values["length"] = request.form.get("length", "medium")
            values["language"] = request.form.get("language", "English")
            values["interval"] = request.form.get("interval", "").strip()
            values["provider_vision"] = request.form.get("provider_vision") == "yes"
            default_output = "." if multi_user_auth_enabled else "scheduled_posts"
            values["scheduled_output"] = (
                request.form.get("scheduled_output", default_output).strip()
                or default_output
            )

            if not values["topic"] and status_message is None:
                status_message = "Topic is required."

            for field, choices in (
                ("platform", PLATFORMS),
                ("media_type", MEDIA_TYPES),
                ("tone", TONES),
                ("length", LENGTHS),
                ("language", LANGUAGES),
            ):
                if values[field] not in choices:
                    values[field] = choices[0]
                    if status_message is None:
                        status_message = f"Unsupported {field.replace('_', ' ')} selected."

            count_value = request.form.get("count", "0").strip()
            try:
                values["count"] = parse_count(count_value)
            except ValueError as exc:
                values["count"] = 0
                if status_message is None:
                    status_message = str(exc)

            interval_seconds = None
            if values["interval"] and status_message is None:
                try:
                    interval_seconds = parse_interval(values["interval"])
                except ValueError as exc:
                    status_message = str(exc)

            scheduled_output_path = None
            if interval_seconds is not None and status_message is None:
                try:
                    scheduled_root = Path(app.config["SCHEDULED_OUTPUT_ROOT"])
                    if multi_user_auth_enabled:
                        scheduled_root = scheduled_root / "users" / str(
                            int(g.current_user["id"])
                        )
                    scheduled_output_path = _resolve_scheduled_output(
                        values["scheduled_output"],
                        scheduled_root,
                    )
                except ValueError as exc:
                    status_message = str(exc)

            media_files = request.files.getlist("media_file")
            if len(media_files) > 1 and status_message is None:
                status_message = "Upload only one image or video file at a time."
            elif media_files and media_files[0].filename and status_message is None:
                try:
                    upload_folder = Path(app.config["UPLOAD_FOLDER"])
                    if multi_user_auth_enabled:
                        upload_folder = upload_folder / str(int(g.current_user["id"]))
                    stored_name = _save_uploaded_media(
                        media_files[0],
                        upload_folder,
                        values["media_type"],
                    )
                    stored_path = upload_folder / stored_name
                    analysis_complete = False
                    try:
                        malware_scan = scan_for_malware(stored_path)
                        if malware_scan["status"] == "infected":
                            raise MediaAnalysisError(
                                "The uploaded file was detected as malware and was rejected."
                            )
                        media_analysis = analyze_media(stored_path, values["media_type"])
                        media_analysis["malware_scan"] = malware_scan
                        analysis_complete = True
                    finally:
                        if not analysis_complete:
                            stored_path.unlink(missing_ok=True)
                    values["media_filename"] = stored_name
                    if values["provider_vision"]:
                        media_analysis["semantic_vision"] = generator.analyze_media_with_vision(
                            stored_path,
                            values["media_type"],
                        )
                except ValueError as exc:
                    status_message = str(exc)

            if (
                values["provider_vision"]
                and not values["media_filename"]
                and status_message is None
            ):
                status_message = "Upload an image or video to use provider vision analysis."

            post_config = {
                "topic": values["topic"],
                "platform": values["platform"],
                "tone": values["tone"],
                "length": values["length"],
                "language": values["language"],
                "media_type": values["media_type"],
                "media_filename": values["media_filename"] or None,
            }
            if media_analysis is not None:
                post_config["media_analysis"] = media_analysis

            if values["topic"] and interval_seconds is not None and not status_message:
                if scheduled_output_path is None:
                    raise RuntimeError("Scheduled output path was not resolved.")
                scheduler = PeriodicPostScheduler(
                    generator,
                    output_dir=str(scheduled_output_path),
                    database_path=(
                        app.config["SCHEDULER_DB_PATH"]
                        or (
                            str(
                                Path(app.config["SCHEDULED_OUTPUT_ROOT"])
                                / "scheduler.sqlite3"
                            )
                            if multi_user_auth_enabled
                            else None
                        )
                    ),
                )
                if multi_user_auth_enabled:
                    job_id = scheduler.create_job(
                        post_config,
                        interval_seconds=interval_seconds,
                        count=values["count"],
                        owner_id=int(g.current_user["id"]),
                    )
                else:
                    job_id = scheduler.create_job(
                        post_config,
                        interval_seconds=interval_seconds,
                        count=values["count"],
                    )
                thread = Thread(
                    target=scheduler.run_scheduled_job,
                    kwargs={"job_id": job_id},
                    daemon=True,
                )
                thread.start()
                status_message = (
                    f"Scheduled job {job_id} started every {values['interval']}. "
                    f"Saved output to {scheduled_output_path}/"
                )
                status_type = "success"
                log_event(
                    logger,
                    "web.scheduled_job_created",
                    request_id=g.request_id,
                    job_id=job_id,
                )
            elif values["topic"] and not values["interval"] and not status_message:
                post = generator.generate_post(**post_config)
                log_event(
                    logger,
                    "web.post_generated",
                    request_id=g.request_id,
                    provider=generator.provider,
                )

        if status_message and status_type is None:
            status_type = "error"

        return render_template(
            "index.html",
            post=post,
            status_message=status_message,
            status_type=status_type,
            values=values,
            auth_enabled=app.config["AUTHENTICATION_CONFIGURED"],
            multi_user=multi_user_auth_enabled,
            current_user=getattr(g, "current_user", None),
            platforms=PLATFORMS,
            media_types=MEDIA_TYPES,
            tones=TONES,
            lengths=LENGTHS,
            languages=LANGUAGES,
        )

    return app


def main() -> None:
    configure_logging()
    app = create_app()
    host = os.environ.get("WEB_HOST", "127.0.0.1")
    if host not in {"127.0.0.1", "localhost", "::1"} and not app.config[
        "AUTHENTICATION_CONFIGURED"
    ]:
        raise RuntimeError(
            "Configure browser authentication before binding beyond localhost."
        )
    app.run(debug=False, host=host, port=5000)
