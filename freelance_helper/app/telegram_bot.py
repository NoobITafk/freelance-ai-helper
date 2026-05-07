from telegram.ext import Application, CommandHandler, CallbackQueryHandler

from app.config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
from app.database import init_db
from app.logger import setup_logger, logger
from app.bot.handlers import (
    start,
    test_ai,
    check_projects,
    auto_check,
    auto_on,
    auto_off,
    stats_command,
    settings_command,
    handle_button,
)


def run_bot():
    setup_logger()
    init_db()

    if not TELEGRAM_BOT_TOKEN:
        raise ValueError("TELEGRAM_BOT_TOKEN не знайдено в .env")

    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    if TELEGRAM_CHAT_ID:
        app.job_queue.run_repeating(
            auto_check,
            interval=180,
            first=10,
            chat_id=int(TELEGRAM_CHAT_ID),
            name="auto_search",
        )
        logger.info("Auto search scheduled on startup")

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("test_ai", test_ai))
    app.add_handler(CommandHandler("check", check_projects))
    app.add_handler(CommandHandler("auto_on", auto_on))
    app.add_handler(CommandHandler("auto_off", auto_off))
    app.add_handler(CommandHandler("stats", stats_command))
    app.add_handler(CommandHandler("settings", settings_command))
    app.add_handler(CallbackQueryHandler(handle_button))

    logger.info("Bot started")
    app.run_polling()