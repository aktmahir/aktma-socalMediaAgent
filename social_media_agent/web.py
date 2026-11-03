import threading
from pathlib import Path
from flask import Flask, render_template, request
from werkzeug.utils import secure_filename
from .generator import SocialMediaPostGenerator
from .scheduler import PeriodicPostScheduler, parse_count, parse_interval

PLATFORMS = ["instagram", "linkedin", "twitter", "facebook", "youtube", "youtube_shorts"]
MEDIA_TYPES = ["text", "image", "video"]
TONES = ["friendly", "professional", "motivational", "funny", "educational"]
LENGTHS = ["short", "medium", "long"]
LANGUAGES = ["English", "Spanish", "French", "Turkish"]
UPLOAD_FOLDER = Path(__file__).resolve().parent.parent / "uploads"
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "mp4", "mov", "avi", "webm", "m4v"}


def allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def create_app() -> Flask:
    app = Flask(__name__, template_folder="templates")
    app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
    UPLOAD_FOLDER.mkdir(parents=True, exist_ok=True)
    generator = SocialMediaPostGenerator()

    @app.route("/", methods=["GET", "POST"])
    def index():
        post = None
        values = {
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
        status_message = None

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

            media_file = request.files.get("media_file")
            if media_file and media_file.filename:
                filename = secure_filename(media_file.filename)
                if allowed_file(filename):
                    file_path = app.config["UPLOAD_FOLDER"] / filename
                    media_file.save(file_path)
                    values["media_filename"] = filename
                else:
                    if status_message is None:
                        status_message = "Unsupported media file type. Allowed types: images and common video files."

            post_config = {
                "topic": values["topic"],
                "platform": values["platform"],
                "tone": values["tone"],
                "length": values["length"],
                "language": values["language"],
                "media_type": values["media_type"],
                "media_filename": values["media_filename"] or None,
            }

            if values["topic"] and values["interval"] and not status_message:
                try:
                    interval_seconds = parse_interval(values["interval"])
                except ValueError as exc:
                    status_message = str(exc)
                else:
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
            elif values["topic"] and not values["interval"] and not status_message:
                post = generator.generate_post(**post_config)

        return render_template(
            "index.html",
            post=post,
            status_message=status_message,
            values=values,
            platforms=PLATFORMS,
            media_types=MEDIA_TYPES,
            tones=TONES,
            lengths=LENGTHS,
            languages=LANGUAGES,
        )

    return app


def main() -> None:
    app = create_app()
    app.run(debug=False, host="127.0.0.1", port=5000)
