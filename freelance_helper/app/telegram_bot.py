import atexit
import errno
import os
from pathlib import Path

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
    portfolio_command,
    portfolio_set_command,
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


LOCK_PATH = Path(__file__).resolve().parents[2] / "data" / "bot.lock"
_lock_file = None


def is_process_running(pid: int) -> bool:
    if pid <= 0:
        return False

    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True

    return True


def remove_stale_lock() -> bool:
    try:
        pid_text = LOCK_PATH.read_text(encoding="utf-8").strip()
        pid = int(pid_text)
    except (OSError, ValueError):
        pid = 0

    if is_process_running(pid):
        return False

    LOCK_PATH.unlink(missing_ok=True)
    logger.warning("Removed stale bot lock: %s", LOCK_PATH)
    return True


def acquire_single_instance_lock() -> None:
    global _lock_file

    LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)

    try:
        fd = os.open(LOCK_PATH, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except OSError as error:
        if error.errno != errno.EEXIST:
            raise

        if remove_stale_lock():
            fd = os.open(LOCK_PATH, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        else:
            raise RuntimeError(
                f"Бот уже запущений або залишився lock-файл: {LOCK_PATH}. "
                "Якщо бот точно зупинений, видали цей файл і запусти ще раз."
            ) from error

    _lock_file = os.fdopen(fd, "w", encoding="utf-8")
    _lock_file.write(str(os.getpid()))
    _lock_file.flush()
    atexit.register(release_single_instance_lock)


def release_single_instance_lock() -> None:
    global _lock_file

    if _lock_file is None:
        return

    try:
        _lock_file.close()
        LOCK_PATH.unlink(missing_ok=True)
    finally:
        _lock_file = None


def run_bot() -> None:
    setup_logger()
    init_db()

    if not TELEGRAM_BOT_TOKEN:
        raise ValueError("TELEGRAM_BOT_TOKEN не знайдено в .env")

    acquire_single_instance_lock()

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
    app.add_handler(CommandHandler("portfolio", portfolio_command))
    app.add_handler(CommandHandler("portfolio_set", portfolio_set_command))
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
