from telegram.ext import Application, CallbackQueryHandler, CommandHandler

from app.bot.handlers import (
    auto_check,
    auto_off,
    auto_on,
    check_projects,
    handle_button,
    help_command,
    settings_command,
    start,
    stats_command,
    test_ai,
)
from app.config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
from app.database import init_db
from app.logger import logger, setup_logger


AUTO_CHECK_INTERVAL_SECONDS = 180
AUTO_CHECK_FIRST_RUN_SECONDS = 10


def run_bot() -> None:
    setup_logger()
    init_db()

    if not TELEGRAM_BOT_TOKEN:
        raise ValueError("TELEGRAM_BOT_TOKEN не знайдено в .env")

    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    if TELEGRAM_CHAT_ID:
        app.job_queue.run_repeating(
            auto_check,
            interval=AUTO_CHECK_INTERVAL_SECONDS,
            first=AUTO_CHECK_FIRST_RUN_SECONDS,
            chat_id=int(TELEGRAM_CHAT_ID),
            name="auto_search",
        )

        logger.info(
            "Auto search scheduled on startup | interval=%s seconds",
            AUTO_CHECK_INTERVAL_SECONDS,
        )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("test_ai", test_ai))
    app.add_handler(CommandHandler("check", check_projects))
    app.add_handler(CommandHandler("auto_on", auto_on))
    app.add_handler(CommandHandler("auto_off", auto_off))
    app.add_handler(CommandHandler("stats", stats_command))
    app.add_handler(CommandHandler("settings", settings_command))
    app.add_handler(CallbackQueryHandler(handle_button))

    logger.info("Bot started")
    app.run_polling()