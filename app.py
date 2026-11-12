import argparse
import os
from datetime import datetime
from getpass import getpass
from pathlib import Path

from social_media_agent.accounts import AccountStore
from social_media_agent.generator import SocialMediaPostGenerator
from social_media_agent.observability import configure_logging
from social_media_agent.scheduler import PeriodicPostScheduler, parse_interval


def main() -> None:
    configure_logging()
    parser = argparse.ArgumentParser(
        description="Generate social media posts automatically using AI or a smart local fallback."
    )
    scheduler_actions = parser.add_mutually_exclusive_group()
    scheduler_actions.add_argument(
        "--list-scheduled",
        action="store_true",
        help="List persisted scheduled jobs.",
    )
    scheduler_actions.add_argument("--pause-job", metavar="JOB_ID", help="Pause a scheduled job.")
    scheduler_actions.add_argument("--resume-job", metavar="JOB_ID", help="Resume a paused job.")
    scheduler_actions.add_argument("--cancel-job", metavar="JOB_ID", help="Cancel a scheduled job.")
    scheduler_actions.add_argument(
        "--retry-job",
        metavar="JOB_ID",
        help="Reset and run a job that exhausted its generation attempts.",
    )
    scheduler_actions.add_argument(
        "--run-scheduled",
        metavar="JOB_ID",
        help="Run or recover a persisted scheduled job.",
    )
    scheduler_actions.add_argument(
        "--supervise-scheduled",
        action="store_true",
        help="Continuously recover and run persisted scheduled jobs.",
    )
    scheduler_actions.add_argument(
        "--create-admin",
        action="store_true",
        help="Create the first multi-user administrator interactively.",
    )
    parser.add_argument("--topic", help="The topic or theme for the social media post.")
    parser.add_argument(
        "--platform",
        default="instagram",
        choices=["instagram", "linkedin", "twitter", "facebook", "youtube", "youtube_shorts"],
        help="The social media platform style to target.",
    )
    parser.add_argument(
        "--media-type",
        default="text",
        choices=["text", "image", "video"],
        help="The type of media being shared.",
    )
    parser.add_argument(
        "--media-filename",
        default="",
        help="Optional media file name for image or video posts.",
    )
    parser.add_argument(
        "--tone",
        default="friendly",
        choices=["friendly", "professional", "motivational", "funny", "educational"],
        help="The tone of the generated post.",
    )
    parser.add_argument(
        "--length",
        default="medium",
        choices=["short", "medium", "long"],
        help="Rough length of the generated caption.",
    )
    parser.add_argument(
        "--language",
        default="English",
        help="Language for the generated post.",
    )
    parser.add_argument(
        "--ai-provider",
        default="openai",
        choices=["openai", "huggingface", "cohere"],
        help="The AI provider to use for generation.",
    )
    parser.add_argument(
        "--provider-model",
        default="",
        help="Optional provider-specific model name (OpenAI, Hugging Face, or Cohere).",
    )
    parser.add_argument(
        "--openai-model",
        default="gpt-3.5-turbo",
        help="OpenAI model to use when OPENAI_API_KEY is available.",
    )
    parser.add_argument(
        "--interval",
        default="",
        help="Optional schedule interval (e.g. 30m, 1h, 1d) for periodic posting.",
    )
    parser.add_argument(
        "--count",
        type=int,
        default=0,
        help="Optional number of scheduled posts to generate (0 for unlimited).",
    )
    parser.add_argument(
        "--scheduled-output",
        default="scheduled_posts",
        help="Directory where scheduled posts are written.",
    )
    parser.add_argument(
        "--scheduler-db",
        default="",
        help="Path to the SQLite scheduler database (defaults to scheduler.sqlite3 in the output directory).",
    )
    parser.add_argument(
        "--scheduler-poll-seconds",
        type=int,
        default=5,
        help="Seconds between scans when --supervise-scheduled is enabled.",
    )
    parser.add_argument(
        "--max-scheduled-workers",
        type=int,
        default=4,
        help="Maximum concurrent jobs when --supervise-scheduled is enabled.",
    )
    args = parser.parse_args()

    if args.create_admin:
        output_root = Path(os.environ.get("SCHEDULED_OUTPUT_ROOT", "scheduled_posts"))
        database_path = os.environ.get(
            "AUTH_DATABASE_PATH",
            str(output_root / "accounts.sqlite3"),
        )
        username = input("Administrator username: ").strip()
        password = getpass("Administrator password (minimum 16 characters): ")
        confirmation = getpass("Confirm administrator password: ")
        if password != confirmation:
            parser.error("Passwords do not match.")
        try:
            AccountStore(database_path).create_initial_admin(username, password)
        except ValueError as exc:
            parser.error(str(exc))
        print(f"Created initial administrator '{username}'.")
        return

    provider_model = args.provider_model or (
        args.openai_model if args.ai_provider == "openai" else None
    )
    generator = SocialMediaPostGenerator(
        api_key=None,
        openai_model=args.openai_model,
        provider=args.ai_provider,
        provider_model=provider_model,
    )

    def create_scheduler() -> PeriodicPostScheduler:
        return PeriodicPostScheduler(
            generator,
            output_dir=args.scheduled_output,
            database_path=args.scheduler_db or None,
        )

    try:
        if args.list_scheduled:
            scheduler = create_scheduler()
            jobs = scheduler.list_jobs()
            if not jobs:
                print("No scheduled jobs found.")
            for job in jobs:
                summary = (
                    f"{job['id']}  {job['status']}  "
                    f"{job['completed_count']}/{job['target_count'] or 'unlimited'}  "
                    f"next={datetime.fromtimestamp(float(job['next_run_at'])).isoformat()}"
                )
                if job["last_error"]:
                    summary += f"  error={job['last_error']}"
                print(summary)
            return
        if args.pause_job:
            scheduler = create_scheduler()
            scheduler.pause_job(args.pause_job)
            print(f"Paused scheduled job {args.pause_job}.")
            return
        if args.resume_job:
            scheduler = create_scheduler()
            scheduler.resume_job(args.resume_job)
            print(f"Resumed scheduled job {args.resume_job}.")
            return
        if args.cancel_job:
            scheduler = create_scheduler()
            scheduler.cancel_job(args.cancel_job)
            print(f"Cancelled scheduled job {args.cancel_job}.")
            return
        if args.retry_job:
            scheduler = create_scheduler()
            scheduler.retry_failed_job(args.retry_job)
            return
        if args.run_scheduled:
            scheduler = create_scheduler()
            scheduler.run_scheduled_job(args.run_scheduled)
            return
        if args.supervise_scheduled:
            scheduler = create_scheduler()
            scheduler.run_supervisor(
                poll_interval_seconds=args.scheduler_poll_seconds,
                max_workers=args.max_scheduled_workers,
            )
            return
    except ValueError as exc:
        parser.error(str(exc))

    if not args.topic or not args.topic.strip():
        parser.error("--topic is required and must not be empty.")
    if args.count < 0:
        parser.error("--count must be a non-negative integer.")

    post_config = {
        "topic": args.topic,
        "platform": args.platform,
        "tone": args.tone,
        "length": args.length,
        "language": args.language,
        "media_type": args.media_type,
        "media_filename": args.media_filename or None,
    }

    if args.interval:
        try:
            interval_seconds = parse_interval(args.interval)
        except ValueError as exc:
            parser.error(str(exc))
        if interval_seconds == 0:
            parser.error("--interval must be a positive duration.")
        scheduler = create_scheduler()
        scheduler.schedule(post_config, interval_seconds=interval_seconds, count=args.count)
        return

    result = generator.generate_post(**post_config)

    print("\n=== Generated Social Media Post ===\n")
    if result["generation_source"] == "provider":
        print(f"Provider: {args.ai_provider.title()}")
        print(f"Model: {generator.provider_model}")
    else:
        print("Generation source: Local template fallback")
    print(f"Platform: {result['platform'].title().replace('_', ' ')}")
    print(f"Tone: {result['tone'].title()}")
    print(f"Language: {result['language']}")
    print(f"Topic: {result['topic']}")
    if result.get("media_type") and result["media_type"] != "text":
        print(f"Media type: {result['media_type']}")
    if result.get("media_filename"):
        print(f"Media file: {result['media_filename']}")
    if result.get("title"):
        print("\nYouTube title:\n")
        print(result["title"])
    if result.get("description"):
        print("\nYouTube description:\n")
        print(result["description"])
    if result.get("tags"):
        print("\nYouTube tags:\n")
        print(", ".join(result["tags"]))
    print("\nCaption:\n")
    print(result["caption"])
    print("\nHashtags:\n")
    print(" ".join(result["hashtags"]))
    if result.get("call_to_action"):
        print("\nCall to action:\n")
        print(result["call_to_action"])


if __name__ == "__main__":
    main()
