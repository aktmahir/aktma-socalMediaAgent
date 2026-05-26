import json
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional

from .generator import SocialMediaPostGenerator


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
