import json
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional

from .generator import SocialMediaPostGenerator


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
    def __init__(self, generator: SocialMediaPostGenerator, output_dir: Optional[str] = None) -> None:
        self.generator = generator
        self.output_dir = Path(output_dir or Path.cwd() / "scheduled_posts")
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def schedule(
        self,
        post_config: Dict[str, object],
        interval_seconds: int,
        count: int = 0,
    ) -> None:
        if interval_seconds <= 0:
            raise ValueError("Interval must be a positive number of seconds.")
        if count < 0:
            raise ValueError("Scheduled post count must be non-negative.")

        iteration = 0
        print(f"Starting periodic posting every {interval_seconds} seconds.")
        print("Press Ctrl+C to stop if running indefinitely.")

        try:
            while count == 0 or iteration < count:
                iteration += 1
                post = self.generator.generate_post(**post_config)
                timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
                filename = self.output_dir / f"scheduled_post_{timestamp}_{iteration}.json"
                with filename.open("w", encoding="utf-8") as out_file:
                    json.dump(post, out_file, ensure_ascii=False, indent=2)

                print(f"[{datetime.now().isoformat()}] Generated scheduled post #{iteration}: {filename}")
                if count != 0 and iteration >= count:
                    break
                time.sleep(interval_seconds)
        except KeyboardInterrupt:
            print("Periodic posting interrupted by user.")
