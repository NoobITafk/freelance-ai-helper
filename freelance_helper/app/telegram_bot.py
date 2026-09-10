import atexit
import errno
import os
from pathlib import Path

from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    MessageHandler,
    PreCheckoutQueryHandler,
    filters,
)

from .bot.handlers import (
    ai_off,
    ai_on,
    auto_check,
    auto_morning_digest,
    auto_off,
    auto_on,
    backup_command,
    case_add_command,
    case_del_command,
    cases_command,
    channel_off_command,
    check_projects,
    crm_command,
    digest_command,
    export_command,
    grant_sub_command,
    group_added_handler,
    handle_button,
    handle_text_message,
    health_command,
    help_command,
    hot_command,
    income_command,
    last_command,
    portfolio_command,
    portfolio_set_command,
    pre_checkout_handler,
    profile_command,
    profile_set_command,
    quiet_command,
    recent_command,
    ref_command,
    set_channel_command,
    set_price_command,
    settings_command,
    start,
    stats_command,
    subscribers_command,
    subscribe_command,
    subscription_command,
    successful_payment_handler,
    test_ai,
    threshold_command,
    webapp_command,
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


_web_runner = None


async def _on_startup(app: Application) -> None:
    global _web_runner
    from .web_server import start_background_web_server
    port = int(os.getenv("WEB_APP_PORT", "8088"))
    _web_runner = await start_background_web_server(host="0.0.0.0", port=port, bot=app.bot)


async def _on_shutdown(app: Application) -> None:
    global _web_runner
    if _web_runner:
        try:
            await _web_runner.cleanup()
            logger.info("Mini App web server stopped cleanly on bot shutdown")
        except Exception as e:
            logger.warning("Error stopping web server: %s", e)

    from .freelancehunt_api import close_http_client
    try:
        await close_http_client()
        logger.info("HTTP client closed cleanly on bot shutdown")
    except Exception as e:
        logger.warning("Error closing HTTP client on shutdown: %s", e)


def run_bot() -> None:
    setup_logger()
    init_db()

    if not TELEGRAM_BOT_TOKEN:
        raise ValueError("TELEGRAM_BOT_TOKEN не знайдено в .env")

    acquire_single_instance_lock()

    app = (
        Application.builder()
        .token(TELEGRAM_BOT_TOKEN)
        .post_init(_on_startup)
        .post_shutdown(_on_shutdown)
        .build()
    )

    if TELEGRAM_CHAT_ID:
        try:
            chat_id_int = int(TELEGRAM_CHAT_ID)
            app.job_queue.run_repeating(
                auto_check,
                interval=AUTO_CHECK_INTERVAL_SECONDS,
                first=AUTO_CHECK_FIRST_RUN_SECONDS,
                chat_id=chat_id_int,
                name="auto_search",
            )
            # Schedule morning digest at 08:30
            from datetime import time as dt_time
            app.job_queue.run_daily(
                auto_morning_digest,
                time=dt_time(hour=8, minute=30),
                chat_id=chat_id_int,
                name="morning_digest",
            )
        except ValueError:
            logger.warning("TELEGRAM_CHAT_ID must be an integer: %s", TELEGRAM_CHAT_ID)
        else:
            logger.info(
                "Auto search and morning digest scheduled on startup | interval=%s seconds",
                AUTO_CHECK_INTERVAL_SECONDS,
            )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("ref", ref_command))
    app.add_handler(CommandHandler("referral", ref_command))
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
    app.add_handler(CommandHandler("cases", cases_command))
    app.add_handler(CommandHandler("case_add", case_add_command))
    app.add_handler(CommandHandler("case_del", case_del_command))
    app.add_handler(CommandHandler("income", income_command))
    app.add_handler(CommandHandler("crm", crm_command))
    app.add_handler(CommandHandler("quiet", quiet_command))
    app.add_handler(CommandHandler("digest", digest_command))
    app.add_handler(CommandHandler("backup", backup_command))
    app.add_handler(CommandHandler("webapp", webapp_command))
    app.add_handler(CommandHandler("export", export_command))
    app.add_handler(CommandHandler("ai_on", ai_on))
    app.add_handler(CommandHandler("ai_off", ai_off))
    app.add_handler(CommandHandler("last", last_command))
    app.add_handler(CommandHandler("recent", recent_command))
    app.add_handler(CommandHandler("why", why_command))
    app.add_handler(CommandHandler("subscribe", subscribe_command))
    app.add_handler(CommandHandler("subscription", subscription_command))
    app.add_handler(CommandHandler("sub", subscription_command))
    app.add_handler(CommandHandler("grant_sub", grant_sub_command))
    app.add_handler(CommandHandler("hot", hot_command))
    app.add_handler(CommandHandler("set_channel", set_channel_command))
    app.add_handler(CommandHandler("channel_off", channel_off_command))
    app.add_handler(CommandHandler("subscribers", subscribers_command))
    app.add_handler(CommandHandler("set_price", set_price_command))
    app.add_handler(PreCheckoutQueryHandler(pre_checkout_handler))
    app.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment_handler))
    app.add_handler(CallbackQueryHandler(handle_button))
    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, group_added_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_message))

    logger.info("Bot started | run: python -m freelance_helper.app.main")
    if TELEGRAM_CHAT_ID:
        logger.info("Auto search scheduled for TELEGRAM_CHAT_ID=%s", TELEGRAM_CHAT_ID)
    else:
        logger.info("TELEGRAM_CHAT_ID not set; use /auto_on in chat")
    app.run_polling(bootstrap_retries=5)
