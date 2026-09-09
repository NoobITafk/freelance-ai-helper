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
_lock_fd = None


def acquire_single_instance_lock() -> None:
    """
    Acquires an atomic OS-level exclusive non-blocking lock (fcntl.flock).
    Guarantees that only ONE bot process can run at any given moment.
    Automatically released by Linux kernel if process terminates or crashes.
    """
    global _lock_fd

    LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(LOCK_PATH, os.O_RDWR | os.O_CREAT, 0o666)

    try:
        import fcntl
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except (ImportError, AttributeError):
        # Non-Unix fallback
        pass
    except (BlockingIOError, OSError) as error:
        other_pid = "?"
        try:
            with open(LOCK_PATH, "r", encoding="utf-8") as f:
                content = f.read().strip()
                if content:
                    other_pid = content
        except Exception:
            pass
        os.close(fd)
        logger.error("Another bot instance is already running (PID: %s)", other_pid)
        raise RuntimeError(
            f"Бот уже запущений (PID: {other_pid}) або файл {LOCK_PATH} заблокований іншим процесом. "
            "Зупиніть старий процес перед запуском нового."
        ) from error

    # Truncate and write current PID for convenience
    try:
        os.ftruncate(fd, 0)
        os.lseek(fd, 0, os.SEEK_SET)
        os.write(fd, f"{os.getpid()}\n".encode("utf-8"))
    except OSError:
        pass

    _lock_fd = fd
    atexit.register(release_single_instance_lock)


def release_single_instance_lock() -> None:
    global _lock_fd

    if _lock_fd is None:
        return

    try:
        import fcntl
        fcntl.flock(_lock_fd, fcntl.LOCK_UN)
    except Exception:
        pass

    try:
        os.close(_lock_fd)
    except Exception:
        pass
    finally:
        _lock_fd = None


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
