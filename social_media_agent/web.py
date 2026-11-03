import logging
import os
import tempfile
import threading
import time
import uuid
from pathlib import Path

from flask import Flask, Response, g, jsonify, render_template, request
from werkzeug.datastructures import FileStorage
from werkzeug.exceptions import RequestEntityTooLarge
from werkzeug.utils import secure_filename

from .generator import SocialMediaPostGenerator
from .observability import RequestMetrics, configure_logging, log_event
from .scheduler import PeriodicPostScheduler, parse_count, parse_interval

logger = logging.getLogger(__name__)

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


def create_app() -> Flask:
    app = Flask(__name__, template_folder="templates")
    app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
    app.config["MAX_CONTENT_LENGTH"] = MAX_REQUEST_BYTES
    UPLOAD_FOLDER.mkdir(parents=True, exist_ok=True)
    generator = SocialMediaPostGenerator()
    request_metrics = RequestMetrics()

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
            "scheduled_output": "scheduled_posts",
        }

    @app.before_request
    def start_request_logging() -> None:
        g.request_id = uuid.uuid4().hex
        g.request_started_at = time.perf_counter()

    @app.after_request
    def log_request(response):
        request_id = getattr(g, "request_id", None)
        if request_id is not None:
            response.headers["X-Request-ID"] = request_id
            duration_ms = round((time.perf_counter() - g.request_started_at) * 1000, 2)
            if request.path != "/metrics":
                request_metrics.observe_request(
                    request.method,
                    response.status_code,
                    duration_ms / 1000,
                )
                log_event(
                    logger,
                    "http.request",
                    request_id=request_id,
                    method=request.method,
                    path=request.path,
                    status_code=response.status_code,
                    duration_ms=duration_ms,
                )
        return response

    @app.get("/metrics")
    def metrics() -> Response:
        return Response(
            request_metrics.render_prometheus(),
            content_type="text/plain; version=0.0.4; charset=utf-8",
        )

    @app.get("/health")
    def health() -> Response:
        return jsonify(status="ok")

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

    @app.route("/", methods=["GET", "POST"])
    def index():
        post = None
        values = default_form_values()
        status_message = None
        status_type = None

        if request.method == "POST":
            values["topic"] = request.form.get("topic", "").strip()
            values["platform"] = request.form.get("platform", "instagram")
            values["media_type"] = request.form.get("media_type", "text")
            values["tone"] = request.form.get("tone", "friendly")
            values["length"] = request.form.get("length", "medium")
            values["language"] = request.form.get("language", "English")
            values["interval"] = request.form.get("interval", "").strip()
            values["scheduled_output"] = request.form.get("scheduled_output", "scheduled_posts").strip() or "scheduled_posts"

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

            media_files = request.files.getlist("media_file")
            if len(media_files) > 1 and status_message is None:
                status_message = "Upload only one image or video file at a time."
            elif media_files and media_files[0].filename and status_message is None:
                try:
                    values["media_filename"] = _save_uploaded_media(
                        media_files[0],
                        Path(app.config["UPLOAD_FOLDER"]),
                        values["media_type"],
                    )
                except ValueError as exc:
                    status_message = str(exc)

            post_config = {
                "topic": values["topic"],
                "platform": values["platform"],
                "tone": values["tone"],
                "length": values["length"],
                "language": values["language"],
                "media_type": values["media_type"],
                "media_filename": values["media_filename"] or None,
            }

            if values["topic"] and interval_seconds is not None and not status_message:
                scheduler = PeriodicPostScheduler(generator, output_dir=values["scheduled_output"])
                job_id = scheduler.create_job(
                    post_config,
                    interval_seconds=interval_seconds,
                    count=values["count"],
                )
                thread = threading.Thread(
                    target=scheduler.run_scheduled_job,
                    kwargs={"job_id": job_id},
                    daemon=True,
                )
                thread.start()
                status_message = (
                    f"Scheduled job {job_id} started every {values['interval']}. "
                    f"Saved output to {values['scheduled_output']}/"
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
    app.run(debug=False, host="127.0.0.1", port=5000)
