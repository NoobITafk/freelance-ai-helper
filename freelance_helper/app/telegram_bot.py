from telegram.ext import Application, CallbackQueryHandler, CommandHandler

from .bot.handlers import (
    ai_off,
    ai_on,
    auto_check,
    auto_off,
    auto_on,
    check_projects,
    handle_button,
    health_command,
    help_command,
    last_command,
    profile_command,
    profile_set_command,
    recent_command,
    settings_command,
    start,
    stats_command,
    test_ai,
    threshold_command,
    why_command,
)
from .config import (
    AUTO_CHECK_FIRST_RUN_SECONDS,
    AUTO_CHECK_INTERVAL_SECONDS,
    TELEGRAM_BOT_TOKEN,
    TELEGRAM_CHAT_ID,
)
from .database import init_db
from .logger import logger, setup_logger


def run_bot() -> None:
    setup_logger()
    init_db()

    if not TELEGRAM_BOT_TOKEN:
        raise ValueError("TELEGRAM_BOT_TOKEN не знайдено в .env")

    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    if TELEGRAM_CHAT_ID:
        try:
            app.job_queue.run_repeating(
                auto_check,
                interval=AUTO_CHECK_INTERVAL_SECONDS,
                first=AUTO_CHECK_FIRST_RUN_SECONDS,
                chat_id=int(TELEGRAM_CHAT_ID),
                name="auto_search",
            )
        except ValueError:
            logger.warning("TELEGRAM_CHAT_ID must be an integer: %s", TELEGRAM_CHAT_ID)
        else:
            logger.info(
                "Auto search scheduled on startup | interval=%s seconds",
                AUTO_CHECK_INTERVAL_SECONDS,
            )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("health", health_command))
    app.add_handler(CommandHandler("test_ai", test_ai))
    app.add_handler(CommandHandler("check", check_projects))
    app.add_handler(CommandHandler("auto_on", auto_on))
    app.add_handler(CommandHandler("auto_off", auto_off))
    app.add_handler(CommandHandler("stats", stats_command))
    app.add_handler(CommandHandler("settings", settings_command))
    app.add_handler(CommandHandler("threshold", threshold_command))
    app.add_handler(CommandHandler("profile", profile_command))
    app.add_handler(CommandHandler("profile_set", profile_set_command))
    app.add_handler(CommandHandler("ai_on", ai_on))
    app.add_handler(CommandHandler("ai_off", ai_off))
    app.add_handler(CommandHandler("last", last_command))
    app.add_handler(CommandHandler("recent", recent_command))
    app.add_handler(CommandHandler("why", why_command))
    app.add_handler(CallbackQueryHandler(handle_button))

    logger.info("Bot started | run: python -m freelance_helper.app.main")
    if TELEGRAM_CHAT_ID:
        logger.info("Auto search scheduled for TELEGRAM_CHAT_ID=%s", TELEGRAM_CHAT_ID)
    else:
        logger.info("TELEGRAM_CHAT_ID not set; use /auto_on in chat")
    app.run_polling(bootstrap_retries=5)
