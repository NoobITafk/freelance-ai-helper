import asyncio
import html
import re
import time
from datetime import datetime

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update, WebAppInfo
from telegram.error import BadRequest, Forbidden, TelegramError
from telegram.ext import ContextTypes

from ..ai_analyzer import (
    BID_VARIANTS,
    analyze_project_json,
    check_ollama_available,
    format_analysis,
    calculate_score,
    extract_project_insights,
    fallback_bid,
    fallback_questions,
    generate_bid,
    generate_chat_pitch,
    generate_questions,
    is_technical_project,
    normalize_analysis,
    project_type,
    unsuitable_project_text,
)
from ..rules import parse_budget_info
from .keyboards import (
    MINI_APP_URL,
    bid_keyboard,
    confirm_publish_keyboard,
    project_keyboard,
    questions_keyboard,
    unsuitable_project_keyboard,
)
from ..config import (
    AI_ANALYSIS_ENABLED,
    AI_TIMEOUT_SECONDS,
    AUTO_CHECK_FIRST_RUN_SECONDS,
    AUTO_CHECK_INTERVAL_SECONDS,
    FREELANCEHUNT_TOKEN,
    MIN_SCORE,
    OLLAMA_MODEL,
    OLLAMA_URL,
    TELEGRAM_BOT_TOKEN,
    TELEGRAM_CHAT_ID,
    USER_PROFILE,
)
from ..freelancehunt_api import FreelancehuntAPIError, get_projects, submit_project_bid
from ..database import (
    add_portfolio_case,
    check_database,
    cleanup_old_projects,
    create_database_backup,
    delete_portfolio_case,
    export_crm_data_csv,
    get_crm_stats,
    get_night_projects,
    get_portfolio_cases,
    get_portfolio_links,
    get_project,
    get_recent_projects,
    get_setting,
    get_stats,
    is_quiet_hours_now,
    set_portfolio_link,
    set_project_rating,
    set_setting,
    update_project_pipeline,
)
from .keyboards import (
    bid_keyboard,
    confirm_publish_keyboard,
    crm_pipeline_keyboard,
    project_keyboard,
    questions_keyboard,
    unsuitable_project_keyboard,
)
from ..services.project_service import format_project_message, process_and_send_project
from ..logger import logger

LAST_PROJECTS_LIMIT = 10


async def reply_text(update: Update, text: str, **kwargs) -> bool:
    message = update.effective_message

    if not message:
        logger.warning("Cannot reply: update has no effective_message")
        return False

    await message.reply_text(text, **kwargs)
    return True


def is_auto_search_on(context: ContextTypes.DEFAULT_TYPE, chat_id: int) -> bool:
    job_queue = context.job_queue

    if not job_queue:
        return False

    return bool(
        job_queue.get_jobs_by_name("auto_search") or job_queue.get_jobs_by_name(str(chat_id))
    )


def set_last_check_stats(
    received_count: int,
    sent_count: int,
    error: str = "",
) -> None:
    set_setting("last_check_at", datetime.now().isoformat(timespec="seconds"))
    set_setting("last_projects_received", str(received_count))
    set_setting("last_projects_sent", str(sent_count))
    set_setting("last_check_error", error)


def make_check_debug_stats() -> dict:
    return {
        "basic_rejected": 0,
        "already_seen": 0,
        "ai_analyzed": 0,
        "fallback_used": 0,
        "sent": 0,
        "low_score_skipped": 0,
        "competition_skipped": 0,
        "api_errors": [],
        "ai_errors": [],
        "api_ok": True,
        "ai_ok": True,
    }


def format_check_debug_stats(
    stats: dict,
    received_count: int,
    processed_count: int,
) -> str:
    filter_rejected = stats["basic_rejected"]

    lines = [
        "🔍 Перевірка завершена",
        "",
        f"Отримано з Freelancehunt: {received_count}",
        f"Оброблено: {processed_count}",
        f"Вже були в базі: {stats['already_seen']}",
        f"Відкинуто фільтрами: {filter_rejected}",
        f"Передано в AI: {stats['ai_analyzed']}",
        f"Fallback без AI: {stats['fallback_used']}",
        f"Відкинуто через score: {stats['low_score_skipped']}",
        f"Відкинуто через конкуренцію: {stats['competition_skipped']}",
        f"Надіслано: {stats['sent']}",
        "",
        f"API: {'OK' if stats['api_ok'] and not stats['api_errors'] else 'ERROR'}",
    ]

    if stats["api_errors"]:
        lines.append(f"Остання помилка API: {stats['api_errors'][-1][:200]}")

    if stats["ai_ok"] and stats["fallback_used"] == 0 and stats["ai_analyzed"] > 0:
        lines.append("AI: OK")
    elif stats["fallback_used"] > 0:
        lines.append("AI: unavailable, used fallback rules")
    elif not stats["ai_ok"]:
        lines.append("AI: ERROR")
    else:
        lines.append("AI: OK")

    if stats["ai_errors"]:
        lines.append(f"Остання помилка AI: {stats['ai_errors'][-1][:200]}")

    return "\n".join(lines)


def env_status(value) -> str:
    return "OK" if value else "missing"


def project_short_description(project: dict, limit: int = 200) -> str:
    description = project.get("description") or ""
    description = " ".join(description.split())

    if len(description) <= limit:
        return description or "Опис відсутній"

    return f"{description[:limit].rstrip()}..."


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_chat:
        logger.warning("Cannot start: update has no effective_chat")
        return

    chat_id = update.effective_chat.id
    await reply_text(update, f"Бот працює ✅\nТвій chat_id: {chat_id}")


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = """
🤖 Команди бота

/start — запуск бота
/help — список команд
/check — перевірити проєкти зараз
/auto_on — увімкнути автопошук
/auto_off — вимкнути автопошук
/stats — статистика
/health — діагностика бота, API, бази та налаштувань
/last — те саме, що /recent
/recent — останні проєкти з бази
/settings — показати мінімальний score
/settings 35 — змінити мінімальний score
/threshold 35 — те саме, коротше
/profile — показати профіль виконавця
/profile_set текст — змінити профіль
/portfolio — посилання на портфоліо
/portfolio_set кат посилання — задати посилання (bot, parsing, backend, web, mobile, devops, excel, general)
/cases — список реальних кейсів для ставок
/case_add кат назва | url | опис — додати кейс у базу
/case_del ID — видалити кейс із бази
/income (або /crm) — воронка заявок, конверсія та заробіток
/quiet — налаштування тихих нічних годин
/digest — ранковий дайджест проєктів за ніч
/backup — надіслати бекап бази даних у чат
/webapp — Telegram Mini App інтерфейс
/copilot (або /extension) — завантажити скрипт авто-ставок у чат
/test_ai — тест роботи аналізатора
/why project_id — показати збережений аналіз

📌 Кнопки під проєктом:
✅ Добрий | ❌ Поганий
📝 Ставка | 💬 Відгук у чат
❓ Уточнення | 💼 Я подав ставку
🔁 Нова ставка | ⏭ Пропустити
"""
    await reply_text(update, text)


async def test_ai(update: Update, context: ContextTypes.DEFAULT_TYPE):
    test_project = {
        "title": "Python-скрипт для парсингу товарів із сайту",
        "description": "Потрібен Python-скрипт для парсингу товарів із сайту. Результат зберегти в Excel.",
        "budget": "1500 грн",
        "bids_count": 4,
        "url": "https://example.com/test",
    }

    started_at = time.monotonic()
    from ..rules import classify_project, count_good_keyword_matches, build_rules_fallback_analysis
    f_res = classify_project(test_project["title"], test_project["description"])
    g_matches = count_good_keyword_matches(test_project["title"], test_project["description"])
    analysis_data = build_rules_fallback_analysis(f_res, test_project["title"], test_project["description"], 4, "1500 грн")
    score = int(analysis_data.get("success_chance", 0))
    elapsed = time.monotonic() - started_at

    sample_msg = format_project_message(
        title=test_project["title"],
        budget=test_project["budget"],
        bids_count=test_project["bids_count"],
        url=test_project["url"],
        score=score,
        analysis_data=analysis_data,
        filter_result=f_res,
        numeric_bids_count=4,
        good_matches=g_matches,
        project_dict=test_project,
    )

    await reply_text(
        update,
        f"✅ Тест евристичного аналізатора ({elapsed:.4f} сек):\n\n{sample_msg}",
    )


async def check_projects(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.effective_message

    if not message:
        logger.warning("Cannot run /check: update has no effective_message")
        return

    await message.reply_text("Шукаю нові проєкти...")
    logger.info("Manual check started")
    debug_stats = make_check_debug_stats()

    try:
        projects = await get_projects()
        logger.info("Fetched projects: %s", len(projects))
    except Exception as error:
        logger.exception("Freelancehunt API error")
        debug_stats["api_ok"] = False
        debug_stats["api_errors"].append(str(error))
        set_last_check_stats(0, 0, str(error))
        await message.reply_text(f"Помилка Freelancehunt API:\n{error}")
        await message.reply_text(format_check_debug_stats(debug_stats, 0, 0))
        return

    if not projects:
        await message.reply_text("Отримано 0 проєктів з Freelancehunt.")
        set_last_check_stats(0, 0)
        await message.reply_text(format_check_debug_stats(debug_stats, 0, 0))
        return

    sent_count = 0
    processed_count = 0

    for project in projects:
        if processed_count >= 20:
            break

        try:
            was_sent = await process_and_send_project(
                message.reply_text,
                project,
                debug_stats=debug_stats,
            )
            processed_count += 1

        except Exception as error:
            logger.exception("Project processing error")
            debug_stats["ai_ok"] = False
            debug_stats["ai_errors"].append(str(error)[:200])
            await message.reply_text(f"Помилка обробки проєкту:\n{error}")
            continue

        if was_sent:
            sent_count += 1
            await asyncio.sleep(0.35)

        if sent_count >= 3:
            break

    if sent_count == 0:
        await message.reply_text("Нових відповідних проєктів поки немає.")

    set_last_check_stats(len(projects), sent_count)
    await message.reply_text(
        format_check_debug_stats(debug_stats, len(projects), processed_count)[:4000]
    )

    logger.info(
        "Manual check finished | sent=%s | processed=%s",
        sent_count,
        processed_count,
    )


async def auto_check(context: ContextTypes.DEFAULT_TYPE):
    chat_id = context.job.chat_id
    logger.info("Auto check started")

    try:
        projects = await get_projects()
        logger.info("Fetched projects: %s", len(projects))
    except Exception as error:
        logger.exception("Auto API error")
        set_last_check_stats(0, 0, str(error))
        try:
            await context.bot.send_message(chat_id=chat_id, text=f"Помилка API:\n{error}")
        except TelegramError:
            pass
        return

    async def send_func(text, reply_markup=None, **kwargs):
        try:
            await context.bot.send_message(
                chat_id=chat_id,
                text=text,
                reply_markup=reply_markup,
                **kwargs,
            )
        except BadRequest as b_err:
            if "chat not found" in str(b_err).lower():
                logger.warning(
                    "Chat not found (chat_id=%s). Відкрийте нового бота в Telegram та надішліть йому /start!",
                    chat_id,
                )
                return
            raise
        except Forbidden as f_err:
            logger.warning("Бот заблокований користувачем або немає прав (chat_id=%s): %s", chat_id, f_err)
            return

    sent_count = 0
    processed_count = 0

    for project in projects:
        if processed_count >= 20:
            break

        try:
            was_sent = await process_and_send_project(
                send_func,
                project,
            )
            processed_count += 1

        except Exception:
            logger.exception("Auto project processing error")
            continue

        if was_sent:
            sent_count += 1
            await asyncio.sleep(0.35)

        if sent_count >= 3:
            break

    logger.info(
        "Auto check finished | sent=%s | processed=%s",
        sent_count,
        processed_count,
    )
    set_last_check_stats(len(projects), sent_count)

    try:
        cleaned = cleanup_old_projects(days=30)
        if cleaned > 0:
            logger.info("DB cleanup: removed %s old skipped projects", cleaned)
    except Exception as cleanup_err:
        logger.warning("DB cleanup error: %s", cleanup_err)


async def auto_on(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_chat:
        logger.warning("Cannot enable auto check: update has no effective_chat")
        return

    if not context.job_queue:
        await reply_text(update, "Job queue недоступний. Перевстанови python-telegram-bot[job-queue].")
        return

    chat_id = update.effective_chat.id
    current_jobs = context.job_queue.get_jobs_by_name(str(chat_id))

    if current_jobs:
        await reply_text(update, "Автоперевірка вже увімкнена ✅")
        return

    context.job_queue.run_repeating(
        auto_check,
        interval=AUTO_CHECK_INTERVAL_SECONDS,
        first=AUTO_CHECK_FIRST_RUN_SECONDS,
        chat_id=chat_id,
        name=str(chat_id),
    )

    logger.info("Auto check enabled for chat_id=%s", chat_id)
    await reply_text(
        update,
        f"Автоперевірку увімкнено ✅\nІнтервал: {AUTO_CHECK_INTERVAL_SECONDS} сек."
    )


async def auto_off(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_chat:
        logger.warning("Cannot disable auto check: update has no effective_chat")
        return

    if not context.job_queue:
        await reply_text(update, "Job queue недоступний.")
        return

    chat_id = update.effective_chat.id
    current_jobs = context.job_queue.get_jobs_by_name(str(chat_id))

    for job in current_jobs:
        job.schedule_removal()

    logger.info("Auto check disabled for chat_id=%s", chat_id)
    await reply_text(update, "Автоперевірку вимкнено ⏹")


async def health_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    database_ok, database_reason = check_database()
    min_score = get_setting("min_score", str(MIN_SCORE))

    api_status = "OK"
    api_reason = "not checked"

    try:
        projects = await get_projects()
        api_reason = f"{len(projects)} projects"
    except Exception as error:
        logger.warning("Health Freelancehunt API check failed: %s", error)
        api_status = "error"
        api_reason = str(error)[:120]

    text = f"""
🩺 Health

Bot: OK
TELEGRAM_BOT_TOKEN: {env_status(TELEGRAM_BOT_TOKEN)}
TELEGRAM_CHAT_ID: {env_status(TELEGRAM_CHAT_ID)}
FREELANCEHUNT_TOKEN: {env_status(FREELANCEHUNT_TOKEN)}
Database: {"OK" if database_ok else "error"} ({database_reason})
Freelancehunt API: {api_status} ({api_reason})
Аналізатор: Швидкий евристичний (без Ollama)
AUTO_CHECK_INTERVAL_SECONDS: {AUTO_CHECK_INTERVAL_SECONDS}
MIN_SCORE: {min_score}
""".strip()

    await reply_text(update, text[:4000])


def setting_bool_from_env(value, default: bool) -> bool:
    if value is None:
        return default

    return str(value).lower() in {"1", "true", "yes", "on", "так"}


async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    stats = get_stats()
    min_score = get_setting("min_score", str(MIN_SCORE))
    ai_enabled = get_setting("AI_ANALYSIS_ENABLED", str(AI_ANALYSIS_ENABLED)).lower()
    interval_min = AUTO_CHECK_INTERVAL_SECONDS // 60 if AUTO_CHECK_INTERVAL_SECONDS >= 60 else AUTO_CHECK_INTERVAL_SECONDS

    text = f"""📊 Статистика роботи бота

⏱ За останні 24 години:
• Оброблено проєктів: {stats.get("recent_24h", 0)}
• Надіслано у Telegram: {stats.get("recent_sent_24h", 0)}

📦 За весь час:
• Усього в базі: {stats["total"]}
• Надіслано користувачу: {stats.get("sent", 0)}

👍 Оцінки та якість:
• 🔥 Дуже підходять: {stats["great"]}
• ✅ Добрі: {stats["good"]}
• 🤔 Можливо: {stats["maybe"]}
• ❌ Погані: {stats["bad"]}
• 🚫 Не моє: {stats["not_mine"]}
• ⏭ Пропущені: {stats["skip"]}
• ⚪ Без оцінки: {stats["unrated"]}

⚙️ Поточні параметри:
• 🎯 Поріг score: {min_score}
• 🤖 AI-аналіз: {ai_enabled}
• 🔄 Інтервал автопошуку: {interval_min} хв"""

    await reply_text(update, text)


async def settings_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        min_score = get_setting("min_score", str(MIN_SCORE))
        await reply_text(
            update,
            f"Поточний мінімальний score: {min_score}\n\n" f"Щоб змінити:\n/settings 35"
        )
        return

    value = context.args[0]

    if not value.isdigit():
        await reply_text(update, "Score має бути числом. Наприклад: /settings 35")
        return

    score = int(value)

    if score < 0 or score > 100:
        await reply_text(update, "Score має бути від 0 до 100.")
        return

    set_setting("min_score", str(score))
    logger.info("Min score changed to %s", score)

    await reply_text(update, f"✅ Мінімальний score змінено на {score}")


async def threshold_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await settings_command(update, context)


async def profile_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    profile = get_setting("user_profile", USER_PROFILE)
    await reply_text(update, f"👤 Поточний профіль:\n\n{profile}")


async def profile_set_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    profile = " ".join(context.args).strip()

    if len(profile) < 20:
        await reply_text(
            update,
            "Профіль занадто короткий. Напиши хоча б 20 символів після /profile_set."
        )
        return

    set_setting("user_profile", profile)
    logger.info("User profile changed")
    await reply_text(update, "✅ Профіль оновлено.")


async def portfolio_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    links = get_portfolio_links()
    if not links:
        await reply_text(
            update,
            "📁 Посилання на портфоліо ще не налаштовані.\n\n"
            "Щоб додати посилання під категорію, використовуйте:\n"
            "<code>/portfolio_set bot https://github.com/...</code>\n"
            "<code>/portfolio_set parsing https://github.com/...</code>\n"
            "<code>/portfolio_set backend https://github.com/...</code>\n"
            "<code>/portfolio_set web https://site.com/...</code>\n"
            "<code>/portfolio_set excel https://docs.google.com/...</code>\n"
            "<code>/portfolio_set general https://github.com/my-profile</code>",
            parse_mode="HTML",
        )
        return

    lines = ["📁 <b>Налаштовані посилання на портфоліо:</b>\n"]
    for cat, url in sorted(links.items()):
        lines.append(f"• <b>{cat}</b>: {url}")

    lines.append("\nЩоб змінити: <code>/portfolio_set &lt;категорія&gt; &lt;посилання&gt;</code>")
    await reply_text(update, "\n".join(lines), parse_mode="HTML")


async def portfolio_set_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args or []
    if len(args) < 2:
        await reply_text(
            update,
            "ℹ️ Формат: /portfolio_set <категорія> <посилання>\n\n"
            "Доступні категорії:\n"
            "• <code>bot</code> — Telegram-боти\n"
            "• <code>parsing</code> — парсинг та скрейпінг\n"
            "• <code>backend</code> — бекенд та API\n"
            "• <code>web</code> — сайти, верстка, WordPress\n"
            "• <code>excel</code> — Excel / Google Таблиці\n"
            "• <code>general</code> — універсальне посилання (за замовчуванням)",
            parse_mode="HTML",
        )
        return

    category = args[0].lower().strip()
    url = args[1].strip()

    valid_categories = {
        "bot",
        "telegram_bot",
        "parsing",
        "backend",
        "api",
        "web",
        "frontend",
        "wordpress",
        "excel",
        "general",
    }
    if category not in valid_categories:
        await reply_text(
            update,
            f"❌ Невідома категорія: <code>{category}</code>.\n"
            "Використовуйте одну з: bot, parsing, backend, web, excel, general.",
            parse_mode="HTML",
        )
        return

    if category == "telegram_bot":
        category = "bot"
    elif category == "api":
        category = "backend"
    elif category in {"frontend", "wordpress"}:
        category = "web"

    set_portfolio_link(category, url)
    logger.info("Portfolio link updated for %s: %s", category, url)
    await reply_text(
        update,
        f"✅ Збережено посилання для категорії <b>{category}</b>:\n{url}",
        parse_mode="HTML",
    )


async def ai_on(update: Update, context: ContextTypes.DEFAULT_TYPE):
    set_setting("AI_ANALYSIS_ENABLED", "true")
    await reply_text(
        update,
        "⚡ Швидкий евристичний аналіз увімкнено (миттєва оцінка без затримок)."
    )


async def ai_off(update: Update, context: ContextTypes.DEFAULT_TYPE):
    set_setting("AI_ANALYSIS_ENABLED", "false")
    await reply_text(
        update,
        "ℹ️ Базовий евристичний фільтр активний за замовчуванням."
    )


async def recent_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    projects = get_recent_projects(limit=LAST_PROJECTS_LIMIT)

    if not projects:
        await reply_text(update, "Поки немає збережених проєктів.")
        return

    lines = ["🕘 Останні знайдені проєкти:"]

    for project in projects:
        status = project.get("status") or "unknown"
        score = project.get("score")
        score_text = "?" if score is None else str(score)
        reason = project.get("reason") or "reason не збережено"
        lines.append(
            f"\nID: {project['project_id']}\n"
            f"Назва: {project['title']}\n"
            f"Опис: {project_short_description(project)}\n"
            f"Budget: {project.get('budget')}\n"
            f"Bids: {project.get('bids_count')}\n"
            f"Score: {score_text}\n"
            f"Status: {status}\n"
            f"Reason: {reason}\n"
            f"{project.get('url') or ''}"
        )

    await reply_text(update, "\n".join(lines)[:4000])


async def last_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await recent_command(update, context)


async def why_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await reply_text(update, "Вкажи ID проєкту. Наприклад: /why 123456")
        return

    project_id = context.args[0]
    project = get_project(project_id)

    if not project:
        await reply_text(update, "Проєкт не знайдено в базі.")
        return

    text = f"""
📌 {project.get("title")}

{project.get("analysis") or "Аналіз не збережено."}

🔗 {project.get("url") or ""}
""".strip()

    await reply_text(update, text[:4000])


async def cases_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cases = get_portfolio_cases()
    if not cases:
        await reply_text(
            update,
            "📂 <b>База кейсів порожня.</b>\n\n"
            "Додайте ваші реальні роботи для автоматичної підстановки у ставки:\n"
            "<code>/case_add bot Назва кейсу | https://посилання | Короткий опис</code>\n\n"
            "Категорії: <code>bot</code>, <code>parser</code>, <code>backend</code>, <code>web</code>, <code>mobile</code>, <code>devops</code>, <code>general</code>",
            parse_mode="HTML",
        )
        return

    lines = ["📁 <b>Ваші реальні кейси в портфоліо:</b>\n"]
    for c in cases:
        lines.append(
            f"🔹 <b>[ID {c['id']}]</b> [{c['category'].upper()}] {c['title']}\n"
            f"   🔗 {c['url'] or 'Без посилання'}\n"
            f"   📝 {c['description'] or 'Без опису'}\n"
        )
    lines.append("Видалити: <code>/case_del ID</code>\nДодати: <code>/case_add кат Назва | URL | Опис</code>")
    await reply_text(update, "\n".join(lines)[:4000], parse_mode="HTML", disable_web_page_preview=True)


async def case_add_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await reply_text(
            update,
            "ℹ️ <b>Формат додавання кейсу:</b>\n"
            "<code>/case_add <категорія> <назва> | <посилання> | <опис></code>\n\n"
            "Приклад:\n"
            "<code>/case_add bot Telegram Shop Bot | https://t.me/example_bot | Бот інтернет-магазину з оплатою LiqPay</code>",
            parse_mode="HTML",
        )
        return

    full_arg = " ".join(context.args)
    first_space = full_arg.find(" ")
    if first_space == -1:
        category = full_arg.lower()
        rest = ""
    else:
        category = full_arg[:first_space].lower()
        rest = full_arg[first_space:].strip()

    parts = [p.strip() for p in rest.split("|")]
    title = parts[0] if parts and parts[0] else f"Кейс {category}"
    url = parts[1] if len(parts) > 1 else ""
    desc = parts[2] if len(parts) > 2 else ""

    case_id = add_portfolio_case(category=category, title=title, description=desc, url=url)
    await reply_text(
        update,
        f"✅ <b>Кейс успішно додано! [ID {case_id}]</b>\n\n"
        f"🏷 <b>Категорія:</b> {category}\n"
        f"📌 <b>Назва:</b> {title}\n"
        f"🔗 <b>URL:</b> {url or 'не вказано'}\n"
        f"📝 <b>Опис:</b> {desc or 'не вказано'}\n\n"
        "Тепер цей кейс буде автоматично підставлятися у відповідні ставки!",
        parse_mode="HTML",
        disable_web_page_preview=True,
    )


async def case_del_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args or not context.args[0].isdigit():
        await reply_text(update, "Вкажіть числовий ID кейсу для видалення. Наприклад: <code>/case_del 2</code>", parse_mode="HTML")
        return

    case_id = int(context.args[0])
    ok = delete_portfolio_case(case_id)
    if ok:
        await reply_text(update, f"✅ Кейс [ID {case_id}] видалено з бази.")
    else:
        await reply_text(update, f"❌ Кейс [ID {case_id}] не знайдено.")


async def crm_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await income_command(update, context)


async def income_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    stats = get_crm_stats()
    text = (
        f"💼 <b>Freelance CRM & Воронка замовлень</b>\n\n"
        f"📊 <b>Конверсія відгуків:</b>\n"
        f"• Подано заявок: <b>{stats['bids_placed']}</b>\n"
        f"• Замовники відповіли: <b>{stats['replied']}</b> ({stats['reply_rate']:.1f}% відгук)\n"
        f"• В активній роботі: <b>{stats['in_progress']}</b>\n"
        f"• Успішно завершено: <b>{stats['completed']}</b> (Win Rate: <b>{stats['win_rate']:.1f}%</b>)\n\n"
        f"💰 <b>Фінансові результати:</b>\n"
        f"• Дохід за поточний місяць: <b>{stats['income_month']:,.0f} грн</b>\n"
        f"• Загальний заробіток: <b>{stats['income_total']:,.0f} грн</b>\n\n"
        f"💡 <i>Позначайте статус проєктів кнопкою «💼 Я подав ставку» під кожною згенерованою пропозицією.</i>"
    )
    await reply_text(update, text, parse_mode="HTML")


async def quiet_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        current = get_setting("quiet_hours") or "23:00 - 08:00"
        is_active = is_quiet_hours_now()
        status_text = "🟢 Зараз діє (без звуку)" if is_active else "⚪ Зараз день (повідомлення зі звуком)"
        await reply_text(
            update,
            f"🌙 <b>Режим «Тихі години»</b>\n\n"
            f"⏱ Поточний інтервал: <b>{current}</b>\n"
            f"Статус: {status_text}\n\n"
            f"Корисні команди:\n"
            f"• <code>/quiet 23:00-08:00</code> — встановити нічний час\n"
            f"• <code>/quiet off</code> — вимкнути тихий режим\n\n"
            f"<i>Під час тихих годин усі нові проєкти надсилаються тихо (без звукового сигналу), щоб не турбувати сон.</i>",
            parse_mode="HTML",
        )
        return

    arg = context.args[0].lower().strip()
    if arg in {"off", "false", "0", "вимк", "вимкнути"}:
        set_setting("quiet_hours", "off")
        await reply_text(update, "☀️ Тихі години вимкнено. Усі сповіщення надходитимуть зі звуком.")
        return

    if "-" in arg:
        parts = arg.split("-")
        try:
            datetime.strptime(parts[0].strip(), "%H:%M")
            datetime.strptime(parts[1].strip(), "%H:%M")
            formatted = f"{parts[0].strip()} - {parts[1].strip()}"
            set_setting("quiet_hours", formatted)
            await reply_text(
                update,
                f"🌙 <b>Тихі години встановлено: {formatted}</b>\n"
                "У цей період бот надсилатиме нові проєкти без звуку.",
                parse_mode="HTML",
            )
            return
        except ValueError:
            pass

    await reply_text(
        update,
        "❌ Невірний формат. Вкажіть години як <code>HH:MM-HH:MM</code>, наприклад: <code>/quiet 23:00-08:00</code> або <code>/quiet off</code>",
        parse_mode="HTML",
    )


async def digest_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    min_score = safe_setting_int(get_setting("min_score", str(MIN_SCORE)), MIN_SCORE)
    projects = get_night_projects(hours=12, min_score=min_score)

    if not projects:
        await reply_text(
            update,
            "🌅 <b>Ранковий дайджест:</b>\n\n"
            "За останні 12 годин нових високих за score проєктів не надходило.\n"
            "Бот продовжує моніторинг у звичайному режимі!",
            parse_mode="HTML",
        )
        return

    lines = [
        f"🌅 <b>Ранковий дайджест ({len(projects)} найкращих проєктів за ніч):</b>\n"
    ]
    for i, p in enumerate(projects, 1):
        budget_str = p.get("budget") or "За домовленістю"
        score_val = p.get("score") or 0
        lines.append(
            f"{i}. <b>{p.get('title')}</b>\n"
            f"   💰 {budget_str}  •  🎯 Score: {score_val}/100\n"
            f"   🔗 <a href=\"{p.get('url')}\">Відкрити на біржі</a>\n"
        )
    lines.append("<i>Щоб згенерувати ставку, використовуйте кнопку під карткою проєкту в стрічці або /recent.</i>")

    await reply_text(update, "\n".join(lines)[:4000], parse_mode="HTML", disable_web_page_preview=True)


async def auto_morning_digest(context: ContextTypes.DEFAULT_TYPE):
    chat_id = context.job.chat_id if context.job else TELEGRAM_CHAT_ID
    if not chat_id:
        return
    min_score = safe_setting_int(get_setting("min_score", str(MIN_SCORE)), MIN_SCORE)
    projects = get_night_projects(hours=10, min_score=min_score)
    if not projects:
        return
    lines = [
        f"🌅 <b>Ранковий дайджест ({len(projects)} найкращих проєктів за ніч):</b>\n"
    ]
    for i, p in enumerate(projects, 1):
        budget_str = p.get("budget") or "За домовленістю"
        score_val = p.get("score") or 0
        lines.append(
            f"{i}. <b>{p.get('title')}</b>\n"
            f"   💰 {budget_str}  •  🎯 Score: {score_val}/100\n"
            f"   🔗 <a href=\"{p.get('url')}\">Відкрити на біржі</a>\n"
        )
    lines.append("<i>Щоб згенерувати ставку, використовуйте кнопку під карткою проєкту в стрічці або /recent.</i>")
    try:
        await context.bot.send_message(
            chat_id=int(chat_id),
            text="\n".join(lines)[:4000],
            parse_mode="HTML",
            disable_web_page_preview=True,
        )
    except Exception as e:
        logger.warning("Auto morning digest failed: %s", e)


async def backup_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_chat:
        return

    await reply_text(update, "⏳ Створюю резервну копію бази даних...")
    try:
        backup_path = create_database_backup()
        with open(backup_path, "rb") as doc:
            await context.bot.send_document(
                chat_id=update.effective_chat.id,
                document=doc,
                filename=backup_path.name,
                caption=f"📦 <b>Резервна копія бази даних</b>\n\nДата: {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}\nФайл: <code>{backup_path.name}</code>",
                parse_mode="HTML",
            )
    except Exception as exc:
        logger.exception("Backup failed: %s", exc)
        await reply_text(update, f"❌ Помилка створення бекапу: {exc}")


async def webapp_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "📱 <b>Telegram Mini App для Freelance AI Helper</b>\n\n"
        "Інтерактивний мобільний інтерфейс дозволяє:\n"
        "• 📊 Переглядати CRM воронку та заробіток\n"
        "• ⚡️ Копіювати згенеровані ставки в 1 дотик\n"
        "• ⚙️ Перемикати фільтри, тихі години та score прямо з телефону\n\n"
        "Файл інтерфейсу: <code>freelance_helper/web_app/index.html</code>\n"
        "Ви можете відкрити його локально або підключити як WebApp меню в @BotFather через команду <code>/setmenubutton</code>."
    )
    await reply_text(update, text, parse_mode="HTML")


async def copilot_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        return

    from ..web_server import WEB_APP_DIR
    script_path = WEB_APP_DIR / "freelancehunt_helper.user.js"

    caption = (
        "🧩 <b>Freelancehunt AI Co-Pilot v1.3.0</b>\n\n"
        "Скрипт для автозаповнення ставок на Freelancehunt.\n\n"
        "💻 <b>На комп'ютері (ПК / Ноутбук):</b>\n"
        "1. Встановіть Tampermonkey (посилання нижче).\n"
        "2. Завантажте прикріплений файл та відкрийте його в Tampermonkey.\n\n"
        "📱 <b>На телефоні (смартфоні):</b>\n"
        "• У мобільному Chrome розширення не підтримуються Google.\n"
        "• <b>Але на телефоні розширення не потрібне:</b> просто торкніться тексту згенерованої ставки у повідомленні (вона скопіюється в 1 дотик) та вставте у замовлення."
    )

    markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("💾 Завантажити файл .user.js", url=f"{MINI_APP_URL}/freelancehunt_helper.user.js?download=1")],
        [
            InlineKeyboardButton("🌐 Chrome (ПК)", url="https://chromewebstore.google.com/detail/tampermonkey/dhdgffkkebhmkfjojejmpbldmpobfkfo"),
            InlineKeyboardButton("🦊 Firefox (ПК / Android)", url="https://addons.mozilla.org/firefox/addon/tampermonkey/"),
        ],
        [
            InlineKeyboardButton("📱 Відкрити Mini App", web_app=WebAppInfo(url=MINI_APP_URL)),
        ],
    ])

    if script_path.is_file():
        try:
            with open(script_path, "rb") as f:
                await context.bot.send_document(
                    chat_id=update.effective_chat.id,
                    document=f,
                    filename="freelancehunt_helper.user.js",
                    caption=caption,
                    parse_mode="HTML",
                    reply_markup=markup,
                )
            return
        except Exception as exc:
            logger.warning("Could not send document: %s", exc)

    await reply_text(update, caption, parse_mode="HTML", reply_markup=markup)


async def reply_safe_markdown(message, text: str, reply_markup=None):
    """
    Sends message with Markdown parse_mode, automatically falling back to plain text
    if Telegram raises a Markdown entity parsing error.
    """
    try:
        return await message.reply_text(
            text,
            parse_mode="Markdown",
            reply_markup=reply_markup,
        )
    except BadRequest as error:
        err_lower = str(error).lower()
        if "entity" in err_lower or "can't find end" in err_lower or "parse" in err_lower:
            logger.warning("Markdown parsing failed, falling back to plain text: %s", error)
            return await message.reply_text(
                text,
                parse_mode=None,
                reply_markup=reply_markup,
            )
        raise


async def handle_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query

    if not query or not query.data:
        return

    if ":" not in query.data:
        logger.warning("Invalid callback data: %s", query.data)
        try:
            await query.answer()
        except Exception:
            pass
        return

    action, project_id = query.data.split(":", 1)
    project = get_project(project_id)
    message = query.message

    if not message:
        logger.warning("Cannot handle callback: query has no message")
        return

    if not project:
        try:
            await query.answer("Проєкт не знайдено в базі.", show_alert=True)
        except Exception:
            pass
        await message.reply_text("Проєкт не знайдено в базі.")
        return

    if not action.startswith("crm_") and action not in {"great", "good", "maybe", "bad", "not_mine", "skip"}:
        try:
            await query.answer()
        except Exception:
            pass

    if action in {"great", "good", "maybe", "bad", "not_mine", "skip"}:
        set_project_rating(project_id, action)
        logger.info("Project rated %s: %s", action, project_id)

        labels = {
            "great": "🔥 Збережено: дуже підходить.",
            "good": "✅ Збережено: добрий проєкт.",
            "maybe": "🤔 Збережено: можливо.",
            "bad": "❌ Збережено: поганий проєкт.",
            "not_mine": "🚫 Збережено: не твоє.",
            "skip": "⏭ Проєкт пропущено.",
        }
        try:
            await query.answer(labels[action], show_alert=False)
        except Exception:
            pass

        try:
            await query.edit_message_reply_markup(
                reply_markup=project_keyboard(project_id, current_rating=action)
            )
        except Exception:
            pass

    elif action == "crm_bid":
        update_project_pipeline(project_id, "bid_placed")
        try:
            await query.answer("💼 Заявку додано у воронку CRM!", show_alert=False)
        except Exception:
            pass
        try:
            await query.edit_message_reply_markup(
                reply_markup=crm_pipeline_keyboard(project_id, current_status="bid_placed")
            )
        except Exception:
            await message.reply_text(
                f"💼 <b>Статус: Заявку подано!</b>\n\n"
                f"📌 {project.get('title')}\n"
                f"Замовлення додано до воронки активних заявок.\n"
                f"Коли замовник відповість, оновіть статус нижче:",
                parse_mode="HTML",
                reply_markup=crm_pipeline_keyboard(project_id, current_status="bid_placed"),
            )

    elif action == "crm_reply":
        update_project_pipeline(project_id, "replied")
        try:
            await query.answer("💬 Статус: Замовник відповів!", show_alert=False)
        except Exception:
            pass
        try:
            await query.edit_message_reply_markup(
                reply_markup=crm_pipeline_keyboard(project_id, current_status="replied")
            )
        except Exception:
            pass

    elif action == "crm_work":
        update_project_pipeline(project_id, "in_progress")
        try:
            await query.answer("🤝 Статус: Проєкт у роботі!", show_alert=False)
        except Exception:
            pass
        try:
            await query.edit_message_reply_markup(
                reply_markup=crm_pipeline_keyboard(project_id, current_status="in_progress")
            )
        except Exception:
            pass

    elif action == "crm_done":
        try:
            await query.answer("💰 Вкажіть суму угоди", show_alert=False)
        except Exception:
            pass
        amount, currency, _ = parse_budget_info(project.get("budget"))
        val = float(amount or 0)
        curr = currency or "UAH"
        context.user_data["pending_crm_done"] = {
            "project_id": project_id,
            "default_amount": val,
            "currency": curr,
        }
        confirm_markup = InlineKeyboardMarkup([
            [InlineKeyboardButton(f"💰 Зарахувати бюджет ({val:,.0f} {curr})", callback_data=f"crm_done_def:{project_id}")],
            [InlineKeyboardButton("❌ Скасувати", callback_data=f"crm_cancel:{project_id}")],
        ])
        await message.reply_text(
            f"💰 <b>Фіксація завершення проєкту:</b>\n"
            f"📌 <b>{project.get('title')}</b>\n\n"
            f"Бюджет біржі: <b>{val:,.0f} {curr}</b>\n\n"
            f"👉 <b>Надішліть фактичну суму угоди</b> повідомленням у чат (наприклад: <code>4500</code> або <code>150$</code>),\n"
            f"або натисніть кнопку нижче для зарахування бюджету біржі:",
            parse_mode="HTML",
            reply_markup=confirm_markup,
        )

    elif action == "crm_done_def":
        amount, currency, _ = parse_budget_info(project.get("budget"))
        val = float(amount or 0)
        curr = currency or "UAH"
        update_project_pipeline(project_id, "completed", deal_amount=val, currency=curr)
        context.user_data.pop("pending_crm_done", None)
        try:
            await query.answer(f"💰 Зараховано {val:,.0f} {curr}!", show_alert=False)
        except Exception:
            pass
        await message.reply_text(
            f"🏆 <b>Проєкт успішно завершено!</b>\n\n"
            f"📌 {project.get('title')}\n"
            f"💰 Зараховано в дохід: <b>{val:,.0f} {curr}</b>\n"
            f"Статистика оновлена у /income та /crm!",
            parse_mode="HTML",
        )

    elif action == "crm_cancel":
        context.user_data.pop("pending_crm_done", None)
        try:
            await query.answer("Скасовано", show_alert=False)
        except Exception:
            pass
        await message.reply_text("❌ Фіксацію завершення проєкту скасовано.")

    elif action == "crm_declined":
        update_project_pipeline(project_id, "declined")
        try:
            await query.answer("❌ Проєкт відхилено", show_alert=False)
        except Exception:
            pass
        await message.reply_text(
            f"❌ <b>Статус: Проєкт відхилено/архівовано.</b>\n📌 {project.get('title')}",
            parse_mode="HTML",
        )

    elif action in ["bid", "rebid"]:
        if not is_technical_project(project):
            await message.reply_text(
                unsuitable_project_text(project),
                reply_markup=unsuitable_project_keyboard(project_id),
            )
            return

        variant = "short"
        if action == "rebid":
            bid_variants = context.user_data.setdefault("bid_variants", {})
            current_index = bid_variants.get(project_id, 0)
            variant = BID_VARIANTS[(current_index + 1) % len(BID_VARIANTS)]
            bid_variants[project_id] = current_index + 1
        else:
            context.user_data.setdefault("bid_variants", {})[project_id] = 0

        variant_labels = {
            "short": "основна",
            "technical": "розгорнута",
            "cautious": "з питаннями",
        }
        variant_name = variant_labels.get(variant, variant)
        bid_text = generate_bid(project, variant=variant)
        context.user_data.setdefault("active_bids", {})[project_id] = bid_text

        # Preformatted code block enables 1-tap/1-click instant copying in Telegram
        escaped_bid = bid_text.replace("```", "'''")
        response_text = (
            f"📝 Пропозиція до проєкту ({variant_name})\n"
            f"👇 Натисніть на текст нижче, щоб скопіювати:\n\n"
            f"```\n{escaped_bid}\n```"
        )

        await reply_safe_markdown(
            message,
            response_text,
            reply_markup=bid_keyboard(project_id, url=project.get("url")),
        )

    elif action == "pitch":
        if not is_technical_project(project):
            await message.reply_text(
                unsuitable_project_text(project),
                reply_markup=unsuitable_project_keyboard(project_id),
            )
            return

        pitch_text = generate_chat_pitch(project)
        escaped_pitch = pitch_text.replace("```", "'''")
        response_text = (
            f"💬 Короткий відгук у чат (для першого контакту)\n"
            f"👇 Натисніть на текст нижче, щоб скопіювати:\n\n"
            f"```\n{escaped_pitch}\n```"
        )

        await reply_safe_markdown(
            message,
            response_text,
            reply_markup=bid_keyboard(project_id, url=project.get("url")),
        )

    elif action == "questions":
        questions = generate_questions(project)
        reply_markup = (
            questions_keyboard(project_id)
            if is_technical_project(project)
            else unsuitable_project_keyboard(project_id)
        )
        await message.reply_text(
            f"❓ Що уточнити:\n\n{questions}",
            reply_markup=reply_markup,
        )

    elif action == "publish_bid":
        if not FREELANCEHUNT_TOKEN:
            await message.reply_text(
                "❌ FREELANCEHUNT_TOKEN не знайдено в налаштуваннях бота.\n"
                "Додайте токен у файл .env для можливості прямої публікації ставок на біржі."
            )
            return

        amount, currency, _ = parse_budget_info(project.get("budget"))
        if not amount or amount <= 0:
            amount = 3000
        currency = currency or "UAH"

        kind = project_type(project)
        days = 2
        try:
            insights = extract_project_insights(project)
            time_est = insights.get("time_estimate", "1-2 дні")
            days_match = re.findall(r"\d+", time_est)
            if days_match:
                days = int(days_match[-1])
        except Exception:
            days = 3 if kind in {"telegram_bot", "backend"} else 2

        # Sweet spot pricing
        bids_cnt = int(project.get("bids_count") or 0)
        rec_amount = amount
        if amount and bids_cnt > 10:
            rec_amount = int(amount * 0.95 / 50) * 50

        active_bids = context.user_data.setdefault("active_bids", {})
        bid_text = active_bids.get(project_id)
        if not bid_text:
            bid_text = generate_bid(project, variant="short")
            active_bids[project_id] = bid_text

        pending = context.user_data.setdefault("pending_publish", {})
        pending[project_id] = {
            "days": days,
            "amount": rec_amount,
            "currency": currency,
            "comment": bid_text,
            "title": project.get("title", "Без назви"),
        }

        preview = bid_text[:280] + ("..." if len(bid_text) > 280 else "")
        prompt = (
            f"🚀 <b>Підтвердження публікації ставки</b>\n\n"
            f"📌 <b>Проєкт:</b> {project.get('title')}\n"
            f"💰 <b>Сума ставки:</b> {rec_amount:,} {currency}\n"
            f"⏱ <b>Термін виконання:</b> {days} дн.\n"
            f"🛡 <b>Тип безпечної угоди:</b> Робота з резервуванням (employer)\n\n"
            f"📝 <b>Текст пропозиції:</b>\n"
            f"<i>{preview}</i>\n\n"
            f"⚠️ <b>Увага:</b> Після підтвердження ставку буде миттєво відправлено на біржу Freelancehunt від вашого облікового запису.\n\n"
            f"Опублікувати ставку зараз?"
        )

        await message.reply_text(
            prompt,
            parse_mode="HTML",
            reply_markup=confirm_publish_keyboard(project_id),
        )

    elif action == "cancel_publish":
        pending = context.user_data.setdefault("pending_publish", {})
        pending.pop(project_id, None)
        await message.reply_text("❌ Публікацію ставки скасовано.")

    elif action == "confirm_publish":
        pending = context.user_data.setdefault("pending_publish", {})
        publish_data = pending.pop(project_id, None)

        if not publish_data:
            amount, currency, _ = parse_budget_info(project.get("budget"))
            if not amount or amount <= 0:
                amount = 3000
            currency = currency or "UAH"
            bid_text = generate_bid(project, variant="short")
            publish_data = {
                "days": 2,
                "amount": amount,
                "currency": currency,
                "comment": bid_text,
            }

        await message.reply_text("⏳ Відправляю ставку на Freelancehunt API...")
        try:
            res = await submit_project_bid(
                project_id=project_id,
                days=publish_data["days"],
                amount=publish_data["amount"],
                currency=publish_data["currency"],
                comment=publish_data["comment"],
            )
            logger.info("Bid posted for project %s: %s", project_id, res)
            update_project_pipeline(project_id, "bid_placed", deal_amount=float(publish_data["amount"]), currency=publish_data["currency"])
            await message.reply_text(
                f"✅ <b>Ставку успішно опубліковано на Freelancehunt!</b>\n\n"
                f"📌 {project.get('title')}\n"
                f"💰 {publish_data['amount']:,} {publish_data['currency']}  •  ⏱ {publish_data['days']} дн.\n"
                f"💼 Проєкт автоматично додано до вашої воронки CRM.\n\n"
                f"🔗 <a href=\"{project.get('url')}\">Переглянути проєкт на біржі</a>",
                parse_mode="HTML",
                disable_web_page_preview=True,
                reply_markup=crm_pipeline_keyboard(project_id, current_status="bid_placed"),
            )
        except FreelancehuntAPIError as err:
            logger.error("Freelancehunt API error submitting bid: %s", err)
            err_text = str(err)
            if "410" in err_text or "deprecation" in err_text.lower():
                escaped_comment = html.escape(publish_data["comment"])
                import urllib.parse
                p_url = project.get("url") or f"https://freelancehunt.com/project/{project_id}.html"
                comment_encoded = urllib.parse.quote(publish_data["comment"])
                autobid_url = f"{p_url}#autobid&amount={publish_data['amount']}&days={publish_data['days']}&bid={comment_encoded}"
                text_410 = (
                    f"⚠️ <b>Freelancehunt вимкнув подачу ставок через прямий API (HTTP 410).</b>\n"
                    f"Біржа вимагає відправки через веб-сайт, але <b>ми повністю автоматизували цей процес в 1 клік:</b>\n\n"
                    f"💰 <b>Сума:</b> {publish_data['amount']:,} {publish_data['currency']}  •  ⏱ <b>Термін:</b> {publish_data['days']} дн.\n\n"
                    f"📋 <b>Ваша згенерована ставка:</b>\n\n"
                    f"<code>{escaped_comment}</code>\n\n"
                    f"👉 <b>Натисніть кнопку нижче:</b> відкриється замовлення у Firefox, скрипт миттєво підставить цю ставку, відкриє форму та запустить авто-відправку:"
                )
                markup_410 = InlineKeyboardMarkup([
                    [InlineKeyboardButton("🚀 Запустити авто-подачу (1 клік)", url=autobid_url)],
                    [
                        InlineKeyboardButton("💼 Я відправив ставку (в CRM)", callback_data=f"crm_bid:{project_id}"),
                        InlineKeyboardButton("📱 Mini App", web_app=WebAppInfo(url=MINI_APP_URL)),
                    ],
                ])
                await message.reply_text(
                    text_410,
                    parse_mode="HTML",
                    disable_web_page_preview=True,
                    reply_markup=markup_410,
                )
            else:
                await message.reply_text(
                    f"❌ <b>Помилка Freelancehunt API:</b>\n{err}",
                    parse_mode="HTML",
                )
        except Exception as exc:
            logger.exception("Unexpected error submitting bid: %s", exc)
            await message.reply_text(
                f"❌ <b>Непередбачена помилка:</b> {exc}",
                parse_mode="HTML",
            )


async def handle_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.effective_message
    if not message or not message.text:
        return

    pending = context.user_data.get("pending_crm_done")
    if not pending:
        return

    text = message.text.strip()
    if text.lower() in {"/cancel_deal", "відміна", "скасувати", "cancel"}:
        context.user_data.pop("pending_crm_done", None)
        await message.reply_text("❌ Фіксацію завершення проєкту скасовано.")
        return

    import re
    cleaned = text.replace(" ", "")
    match = re.search(r"(\d+(?:[.,]\d+)?)", cleaned)
    if not match:
        await message.reply_text(
            "⚠️ Не вдалося розпізнати суму. Введіть число (наприклад: <code>4500</code> або <code>150$</code>) "
            "або відправте <b>скасувати</b> для виходу.",
            parse_mode="HTML",
        )
        return

    amount_str = match.group(1).replace(",", ".")
    try:
        amount = float(amount_str)
    except ValueError:
        return

    currency = pending.get("currency", "UAH")
    lower_text = text.lower()
    if "$" in text or "usd" in lower_text:
        currency = "USD"
    elif "€" in text or "eur" in lower_text:
        currency = "EUR"
    elif "грн" in lower_text or "uah" in lower_text:
        currency = "UAH"

    project_id = pending["project_id"]
    project = get_project(project_id) or {}
    title = project.get("title", f"ID {project_id}")

    update_project_pipeline(project_id, "completed", deal_amount=amount, currency=currency)
    context.user_data.pop("pending_crm_done", None)

    await message.reply_text(
        f"🏆 <b>Проєкт успішно завершено!</b>\n\n"
        f"📌 <b>{title}</b>\n"
        f"💰 Фактичний дохід: <b>{amount:,.0f} {currency}</b>\n\n"
        f"Дані зафіксовані у воронці CRM та враховані в /income та /crm!",
        parse_mode="HTML",
    )


async def export_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.effective_message
    if not message:
        return

    try:
        csv_data = export_crm_data_csv()
        import io
        bio = io.BytesIO(csv_data.encode("utf-8"))
        filename = f"crm_export_{datetime.now().strftime('%Y%m%d_%H%M')}.csv"
        bio.name = filename

        stats = get_crm_stats()
        win_rate = stats.get("win_rate", 0.0)
        total_income = stats.get("total_income", {})
        income_str = "  •  ".join(f"{v:,.0f} {k}" for k, v in total_income.items()) or "0 UAH"

        caption = (
            f"📊 <b>Експорт CRM та фінансової звітності</b>\n\n"
            f"📈 Win Rate: <b>{win_rate:.1f}%</b>\n"
            f"💰 Загальний дохід: <b>{income_str}</b>\n\n"
            f"📁 Файл <code>{filename}</code> готовий для відкриття в Excel або Google Sheets."
        )

        await message.reply_document(
            document=bio,
            filename=filename,
            caption=caption,
            parse_mode="HTML",
        )
    except Exception as e:
        logger.exception("Export command error: %s", e)
        await message.reply_text(f"❌ Помилка експорту даних: {e}")

