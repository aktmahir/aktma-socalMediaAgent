import json
import logging
from typing import Any


def configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )


def log_event(logger: logging.Logger, event: str, **fields: Any) -> None:
    logger.info(
        "%s",
        json.dumps({"event": event, **fields}, sort_keys=True, separators=(",", ":")),
    )
