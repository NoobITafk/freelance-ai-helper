import logging
from logging.handlers import RotatingFileHandler
import re
from pathlib import Path

from .config import PROJECT_ROOT


class TelegramTokenFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        record.msg = re.sub(r"/bot[^/\s\"]+", "/bot<token>", message)
        record.args = ()
        return True


def setup_logger():
    log_dir = PROJECT_ROOT / "logs"
    log_dir.mkdir(exist_ok=True)
    token_filter = TelegramTokenFilter()
    handlers = [
        RotatingFileHandler(
            log_dir / "bot.log",
            maxBytes=5 * 1024 * 1024,
            backupCount=3,
            encoding="utf-8",
        ),
        logging.StreamHandler(),
    ]

    for handler in handlers:
        handler.addFilter(token_filter)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        handlers=handlers,
    )
    logging.getLogger().addFilter(token_filter)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)


logger = logging.getLogger("freelance_helper")
