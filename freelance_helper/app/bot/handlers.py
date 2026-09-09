import asyncio
import time
from datetime import datetime

from telegram import Update
from telegram.error import BadRequest, Forbidden, TelegramError
from telegram.ext import ContextTypes

from ..ai_analyzer import (
    BID_VARIANTS,
    analyze_project_json,
    check_ollama_available,
    format_analysis,
    calculate_score,
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
from .keyboards import bid_keyboard, confirm_publish_keyboard, questions_keyboard, unsuitable_project_keyboard
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
    check_database,
    cleanup_old_projects,
    get_portfolio_links,
    get_project,
    get_recent_projects,
    get_setting,
    get_stats,
    set_portfolio_link,
    set_project_rating,
    set_setting,
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
/portfolio — налаштовані посилання на портфоліо/кейси
/portfolio_set категорія посилання — задати кейс (bot, parsing, backend, web, excel, general)
/test_ai — тест роботи аналізатора
/why project_id — показати збережений аналіз

📌 Кнопки під проєктом:
✅ Добрий | ❌ Поганий
📝 Ставка | 💬 Відгук у чат
❓ Уточнення | 🚀 Опублікувати
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


async def handle_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query

    if not query or not query.data:
        return

    try:
        await query.answer()
    except Exception:
        pass

    if ":" not in query.data:
        logger.warning("Invalid callback data: %s", query.data)
        return

    action, project_id = query.data.split(":", 1)
    project = get_project(project_id)
    message = query.message

    if not message:
        logger.warning("Cannot handle callback: query has no message")
        return

    if not project:
        await message.reply_text("Проєкт не знайдено в базі.")
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
        await message.reply_text(labels[action])

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

        await message.reply_text(
            response_text,
            parse_mode="Markdown",
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

        await message.reply_text(
            response_text,
            parse_mode="Markdown",
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
        days = 3 if kind in {"telegram_bot", "backend"} else 2

        active_bids = context.user_data.setdefault("active_bids", {})
        bid_text = active_bids.get(project_id)
        if not bid_text:
            bid_text = generate_bid(project, variant="short")
            active_bids[project_id] = bid_text

        pending = context.user_data.setdefault("pending_publish", {})
        pending[project_id] = {
            "days": days,
            "amount": amount,
            "currency": currency,
            "comment": bid_text,
            "title": project.get("title", "Без назви"),
        }

        preview = bid_text[:280] + ("..." if len(bid_text) > 280 else "")
        prompt = (
            f"🚀 <b>Підтвердження публікації ставки</b>\n\n"
            f"📌 <b>Проєкт:</b> {project.get('title')}\n"
            f"💰 <b>Сума ставки:</b> {amount:,} {currency}\n"
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
            await message.reply_text(
                f"✅ <b>Ставку успішно опубліковано на Freelancehunt!</b>\n\n"
                f"📌 {project.get('title')}\n"
                f"💰 {publish_data['amount']:,} {publish_data['currency']}  •  ⏱ {publish_data['days']} дн.\n"
                f"🔗 <a href=\"{project.get('url')}\">Переглянути проєкт на біржі</a>",
                parse_mode="HTML",
                disable_web_page_preview=True,
            )
        except FreelancehuntAPIError as err:
            logger.error("Freelancehunt API error submitting bid: %s", err)
            err_text = str(err)
            if "410" in err_text or "deprecation" in err_text.lower():
                await message.reply_text(
                    f"⚠️ <b>Freelancehunt вимкнув публічне створення ставок через API (HTTP 410).</b>\n\n"
                    f"Біржа вимагає публікації через сайт для захисту від автоспаму.\n\n"
                    f"👉 Скопіюйте текст ставки вище (1 клік по тексту) та відправте на сторінці проєкту:\n"
                    f"🔗 <a href=\"{project.get('url')}\">Відкрити замовлення на Freelancehunt</a>",
                    parse_mode="HTML",
                    disable_web_page_preview=True,
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
