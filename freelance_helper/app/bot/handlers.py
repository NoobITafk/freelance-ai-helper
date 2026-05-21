import time
from datetime import datetime

from telegram import Update
from telegram.ext import ContextTypes

from ..ai_analyzer import (
    analyze_project_json,
    check_ollama_available,
    format_analysis,
    calculate_score,
    generate_bid,
    generate_questions,
    normalize_analysis,
)
from ..config import (
    AI_ANALYSIS_ENABLED,
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
from ..freelancehunt_api import get_projects
from ..database import (
    check_database,
    get_project,
    get_recent_projects,
    set_project_rating,
    get_stats,
    get_setting,
    set_setting,
)
from ..services.project_service import process_and_send_project
from ..logger import logger


LAST_PROJECTS_LIMIT = 10


def is_auto_search_on(context: ContextTypes.DEFAULT_TYPE, chat_id: int) -> bool:
    job_queue = context.job_queue

    if not job_queue:
        return False

    return bool(
        job_queue.get_jobs_by_name("auto_search")
        or job_queue.get_jobs_by_name(str(chat_id))
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
    filter_rejected = stats["basic_rejected"] + stats["already_seen"]

    lines = [
        "🔍 Перевірка завершена",
        "",
        f"Отримано з Freelancehunt: {received_count}",
        f"Оброблено: {processed_count}",
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
    chat_id = update.effective_chat.id
    await update.message.reply_text(f"Бот працює ✅\nТвій chat_id: {chat_id}")


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = """
🤖 Команди бота

/start — запуск бота
/help — список команд
/check — перевірити проєкти зараз
/auto_on — увімкнути автопошук
/auto_off — вимкнути автопошук
/stats — статистика
/health — діагностика бота, API, бази, AI
/last — те саме, що /recent
/recent — останні проєкти з бази
/settings — показати мінімальний score
/settings 35 — змінити мінімальний score
/threshold 35 — те саме, коротше
/profile — показати профіль виконавця
/profile_set текст — змінити профіль
/ai_on — увімкнути AI-аналіз
/ai_off — вимкнути AI-аналіз
/test_ai — перевірити Ollama/AI
/why project_id — показати збережений аналіз

📌 Кнопки під проєктом:
✅ Добрий | ❌ Поганий
📝 Ставка | ❓ Уточнення
🔁 Нова ставка | ⏭ Пропустити
"""
    await update.message.reply_text(text)


async def test_ai(update: Update, context: ContextTypes.DEFAULT_TYPE):
    test_project = """
Потрібен Python-скрипт для парсингу товарів із сайту.
Результат зберегти в Excel.
Бюджет: 1000 грн.
Термін: 1 день.
"""

    await update.message.reply_text(
        f"Тестую AI...\nМодель: {OLLAMA_MODEL}\nURL: {OLLAMA_URL}"
    )

    try:
        started_at = time.monotonic()
        user_profile = get_setting("user_profile", USER_PROFILE)
        analysis_data = normalize_analysis(analyze_project_json(test_project, user_profile))
        score = calculate_score(analysis_data)
        analysis = format_analysis(analysis_data)
        elapsed = time.monotonic() - started_at
    except Exception as error:
        logger.exception("AI test failed")
        await update.message.reply_text(f"AI-тест не пройшов:\n{error}")
        return

    await update.message.reply_text(f"Score: {score}/100\nЧас: {elapsed:.1f} сек\n\n{analysis}")


async def check_projects(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Шукаю нові проєкти...")
    logger.info("Manual check started")
    debug_stats = make_check_debug_stats()

    try:
        projects = get_projects()
        logger.info("Fetched projects: %s", len(projects))
    except Exception as error:
        logger.exception("Freelancehunt API error")
        debug_stats["api_ok"] = False
        debug_stats["api_errors"].append(str(error))
        set_last_check_stats(0, 0, str(error))
        await update.message.reply_text(f"Помилка Freelancehunt API:\n{error}")
        await update.message.reply_text(format_check_debug_stats(debug_stats, 0, 0))
        return

    if not projects:
        await update.message.reply_text("Отримано 0 проєктів з Freelancehunt.")
        set_last_check_stats(0, 0)
        await update.message.reply_text(format_check_debug_stats(debug_stats, 0, 0))
        return

    sent_count = 0
    processed_count = 0

    for project in projects:
        if processed_count >= 20:
            break

        try:
            was_sent = await process_and_send_project(
                update.message.reply_text,
                project,
                debug_stats=debug_stats,
            )
            processed_count += 1

        except Exception as error:
            logger.exception("Project processing error")
            debug_stats["ai_ok"] = False
            debug_stats["ai_errors"].append(str(error)[:200])
            await update.message.reply_text(f"Помилка обробки проєкту:\n{error}")
            continue

        if was_sent:
            sent_count += 1

        if sent_count >= 3:
            break

    if sent_count == 0:
        await update.message.reply_text("Нових відповідних проєктів поки немає.")

    set_last_check_stats(len(projects), sent_count)
    await update.message.reply_text(
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
        projects = get_projects()
        logger.info("Fetched projects: %s", len(projects))
    except Exception as error:
        logger.exception("Auto API error")
        set_last_check_stats(0, 0, str(error))
        await context.bot.send_message(chat_id=chat_id, text=f"Помилка API:\n{error}")
        return

    async def send_func(text, reply_markup=None):
        await context.bot.send_message(
            chat_id=chat_id,
            text=text,
            reply_markup=reply_markup,
        )

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

        if sent_count >= 3:
            break

    logger.info(
        "Auto check finished | sent=%s | processed=%s",
        sent_count,
        processed_count,
    )
    set_last_check_stats(len(projects), sent_count)


async def auto_on(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    current_jobs = context.job_queue.get_jobs_by_name(str(chat_id))

    if current_jobs:
        await update.message.reply_text("Автоперевірка вже увімкнена ✅")
        return

    context.job_queue.run_repeating(
        auto_check,
        interval=AUTO_CHECK_INTERVAL_SECONDS,
        first=AUTO_CHECK_FIRST_RUN_SECONDS,
        chat_id=chat_id,
        name=str(chat_id),
    )

    logger.info("Auto check enabled for chat_id=%s", chat_id)
    await update.message.reply_text(
        f"Автоперевірку увімкнено ✅\nІнтервал: {AUTO_CHECK_INTERVAL_SECONDS} сек."
    )


async def auto_off(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    current_jobs = context.job_queue.get_jobs_by_name(str(chat_id))

    for job in current_jobs:
        job.schedule_removal()

    logger.info("Auto check disabled for chat_id=%s", chat_id)
    await update.message.reply_text("Автоперевірку вимкнено ⏹")


async def health_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    database_ok, database_reason = check_database()
    ai_setting = get_setting("AI_ANALYSIS_ENABLED")
    if ai_setting is None:
        ai_setting = get_setting("ai_enabled")
    runtime_ai_enabled = setting_bool_from_env(ai_setting, AI_ANALYSIS_ENABLED)
    min_score = get_setting("min_score", str(MIN_SCORE))

    api_status = "OK"
    api_reason = "not checked"

    try:
        projects = get_projects()
        api_reason = f"{len(projects)} projects"
    except Exception as error:
        logger.warning("Health Freelancehunt API check failed: %s", error)
        api_status = "error"
        api_reason = str(error)[:120]

    try:
        ollama_ok, ollama_reason = check_ollama_available()
    except Exception as error:
        ollama_ok = False
        ollama_reason = str(error)[:120]

    text = f"""
🩺 Health

Bot: OK
TELEGRAM_BOT_TOKEN: {env_status(TELEGRAM_BOT_TOKEN)}
TELEGRAM_CHAT_ID: {env_status(TELEGRAM_CHAT_ID)}
FREELANCEHUNT_TOKEN: {env_status(FREELANCEHUNT_TOKEN)}
Database: {"OK" if database_ok else "error"} ({database_reason})
Freelancehunt API: {api_status} ({api_reason})
AI_ANALYSIS_ENABLED: {str(runtime_ai_enabled).lower()}
OLLAMA_URL: {OLLAMA_URL}
OLLAMA_MODEL: {OLLAMA_MODEL}
Ollama: {"OK" if ollama_ok else "unavailable"} ({ollama_reason})
AUTO_CHECK_INTERVAL_SECONDS: {AUTO_CHECK_INTERVAL_SECONDS}
MIN_SCORE: {min_score}
""".strip()

    await update.message.reply_text(text[:4000])


def setting_bool_from_env(value, default: bool) -> bool:
    if value is None:
        return default

    return str(value).lower() in {"1", "true", "yes", "on", "так"}


async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    stats = get_stats()
    min_score = get_setting("min_score", str(MIN_SCORE))
    ai_enabled = get_setting("AI_ANALYSIS_ENABLED", str(AI_ANALYSIS_ENABLED)).lower()

    text = f"""
📊 Статистика

Усього проєктів у базі: {stats["total"]}

🔥 Дуже підходять: {stats["great"]}
✅ Добрі: {stats["good"]}
🤔 Можливо: {stats["maybe"]}
❌ Погані: {stats["bad"]}
🚫 Не моє: {stats["not_mine"]}
⏭ Пропущені: {stats["skip"]}
⚪ Без оцінки: {stats["unrated"]}

🎯 Мінімальний score: {min_score}
🤖 AI-аналіз: {ai_enabled}
"""

    await update.message.reply_text(text)


async def settings_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        min_score = get_setting("min_score", str(MIN_SCORE))
        await update.message.reply_text(
            f"Поточний мінімальний score: {min_score}\n\n"
            f"Щоб змінити:\n/settings 35"
        )
        return

    value = context.args[0]

    if not value.isdigit():
        await update.message.reply_text("Score має бути числом. Наприклад: /settings 35")
        return

    score = int(value)

    if score < 0 or score > 100:
        await update.message.reply_text("Score має бути від 0 до 100.")
        return

    set_setting("min_score", str(score))
    logger.info("Min score changed to %s", score)

    await update.message.reply_text(f"✅ Мінімальний score змінено на {score}")


async def threshold_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await settings_command(update, context)


async def profile_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    profile = get_setting("user_profile", USER_PROFILE)
    await update.message.reply_text(f"👤 Поточний профіль:\n\n{profile}")


async def profile_set_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    profile = " ".join(context.args).strip()

    if len(profile) < 20:
        await update.message.reply_text(
            "Профіль занадто короткий. Напиши хоча б 20 символів після /profile_set."
        )
        return

    set_setting("user_profile", profile)
    logger.info("User profile changed")
    await update.message.reply_text("✅ Профіль оновлено.")


async def ai_on(update: Update, context: ContextTypes.DEFAULT_TYPE):
    set_setting("AI_ANALYSIS_ENABLED", "true")
    await update.message.reply_text("✅ AI-аналіз увімкнено (AI_ANALYSIS_ENABLED=true).")


async def ai_off(update: Update, context: ContextTypes.DEFAULT_TYPE):
    set_setting("AI_ANALYSIS_ENABLED", "false")
    await update.message.reply_text(
        "⏹ AI-аналіз вимкнено (AI_ANALYSIS_ENABLED=false). Використовується fallback rules."
    )


async def recent_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    projects = get_recent_projects(limit=LAST_PROJECTS_LIMIT)

    if not projects:
        await update.message.reply_text("Поки немає збережених проєктів.")
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

    await update.message.reply_text("\n".join(lines)[:4000])


async def last_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await recent_command(update, context)


async def why_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Вкажи ID проєкту. Наприклад: /why 123456")
        return

    project_id = context.args[0]
    project = get_project(project_id)

    if not project:
        await update.message.reply_text("Проєкт не знайдено в базі.")
        return

    text = f"""
📌 {project.get("title")}

{project.get("analysis") or "Аналіз не збережено."}

🔗 {project.get("url") or ""}
""".strip()

    await update.message.reply_text(text[:4000])


async def handle_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query

    if not query or not query.data:
        return

    try:
        await query.answer()
    except Exception:
        pass

    action, project_id = query.data.split(":", 1)
    project = get_project(project_id)

    if not project:
        await query.message.reply_text("Проєкт не знайдено в базі.")
        return

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
        await query.message.reply_text(labels[action])

    elif action in ["bid", "rebid"]:
        await query.message.reply_text("Генерую відповідь клієнту...")

        try:
            user_profile = get_setting("user_profile", USER_PROFILE)
            short_bid = generate_bid(project, user_profile=user_profile, variant="short")
            confident_bid = generate_bid(project, user_profile=user_profile, variant="confident")
        except Exception as error:
            logger.exception("Bid generation error")
            await query.message.reply_text(f"Помилка генерації ставки:\n{error}")
            return

        await query.message.reply_text(
            f"📝 Коротка відповідь клієнту:\n\n{short_bid}\n\n"
            f"💪 Впевненіший варіант:\n\n{confident_bid}\n\n"
            f"🔗 {project.get('url')}"
        )

    elif action == "questions":
        await query.message.reply_text("Генерую питання клієнту...")

        try:
            questions = generate_questions(project)
        except Exception as error:
            logger.exception("Questions generation error")
            await query.message.reply_text(f"Помилка генерації питань:\n{error}")
            return

        await query.message.reply_text(
            f"❓ Що уточнити:\n\n{questions}\n\n🔗 {project.get('url')}"
        )
