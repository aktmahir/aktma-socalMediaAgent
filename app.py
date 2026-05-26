import argparse
from social_media_agent.generator import SocialMediaPostGenerator
from social_media_agent.scheduler import PeriodicPostScheduler


def parse_interval(interval: str) -> int:
    if not interval:
        return 0
    unit = interval[-1].lower()
    amount = int(interval[:-1])
    if unit == "s":
        return amount
    if unit == "m":
        return amount * 60
    if unit == "h":
        return amount * 3600
    if unit == "d":
        return amount * 86400
    raise ValueError("Interval must end with s, m, h, or d.")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate social media posts automatically using AI or a smart local fallback."
    )
    parser.add_argument("--topic", required=True, help="The topic or theme for the social media post.")
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
    args = parser.parse_args()

    generator = SocialMediaPostGenerator(api_key=None, openai_model=args.openai_model)
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
        interval_seconds = parse_interval(args.interval)
        scheduler = PeriodicPostScheduler(generator, output_dir=args.scheduled_output)
        scheduler.schedule(post_config, interval_seconds=interval_seconds, count=args.count)
        return

    result = generator.generate_post(**post_config)

    print("\n=== Generated Social Media Post ===\n")
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
