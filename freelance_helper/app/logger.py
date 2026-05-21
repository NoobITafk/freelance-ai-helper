import logging
import re
from pathlib import Path


class TelegramTokenFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        record.msg = re.sub(r"/bot[^/\s\"]+", "/bot<token>", message)
        record.args = ()
        return True


def setup_logger():
    Path("logs").mkdir(exist_ok=True)
    token_filter = TelegramTokenFilter()
    handlers = [
        logging.FileHandler("logs/bot.log", encoding="utf-8"),
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
