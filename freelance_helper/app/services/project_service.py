import asyncio

from ..ai_analyzer import (
    analyze_project_json,
    format_analysis,
    calculate_score,
    normalize_analysis,
)
from ..config import (
    AI_ANALYSIS_ENABLED,
    AI_TIMEOUT_SECONDS,
    ANALYZE_MAYBE_PROJECTS,
    MAX_BIDS_COUNT,
    USER_PROFILE,
)
from ..database import (
    is_seen,
    save_project,
    get_setting,
    get_good_bad_keywords,
)
from ..rules import classify_project, learning_bonus
from ..bot.keyboards import project_keyboard
from ..logger import logger


BORDERLINE_SCORE_MARGIN = 10


def get_project_url(project: dict, attributes: dict) -> str:
    links = project.get("links", {})

    return (
        attributes.get("url")
        or attributes.get("link")
        or links.get("self", {}).get("web")
        or links.get("self", {}).get("href")
        or "Посилання не знайдено"
    )


def parse_bids_count(bids_count) -> int | None:
    if isinstance(bids_count, int):
        return bids_count

    if isinstance(bids_count, str) and bids_count.isdigit():
        return int(bids_count)

    return None


def safe_setting_int(value, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def build_project_text(
    title: str,
    description: str,
    budget,
    bids_count,
) -> str:
    return f"""
Назва: {title}
Бюджет: {budget}
Кількість ставок: {bids_count}

Опис:
{description}
""".strip()


def fallback_analysis(reason: str) -> dict:
    return {
        "fit": "partial",
        "summary": "Проєкт пройшов базовий keyword-фільтр, але AI-аналіз не виконався.",
        "difficulty": 4,
        "risk": 5,
        "success_chance": 65,
        "competition": "unknown",
        "budget_ok": "unknown",
        "should_apply": True,
        "reason": reason,
        "questions": [
            "Який точний обсяг роботи?",
            "Який формат результату очікується?",
            "Які терміни виконання?",
        ],
    }


def setting_bool(value, default: bool) -> bool:
    if value is None:
        return default

    return str(value).lower() in {"1", "true", "yes", "on", "так"}


async def analyze_project_with_timeout(project_text: str) -> tuple[dict, bool]:
    ai_enabled = setting_bool(get_setting("ai_enabled"), AI_ANALYSIS_ENABLED)

    if not ai_enabled:
        return fallback_analysis("AI-аналіз вимкнено в налаштуваннях."), False

    user_profile = get_setting("user_profile", USER_PROFILE)

    try:
        raw_analysis = await asyncio.wait_for(
            asyncio.to_thread(analyze_project_json, project_text, user_profile),
            timeout=AI_TIMEOUT_SECONDS,
        )
        return normalize_analysis(raw_analysis), True

    except Exception as error:
        logger.exception("AI analysis failed")
        return fallback_analysis(f"AI-аналіз не спрацював: {error}"), False


def should_send_project(analysis_data: dict, score: int, min_score: int, ai_used: bool) -> bool:
    if not ai_used:
        return True

    if score >= min_score:
        return True

    fit = analysis_data.get("fit")
    should_apply = analysis_data.get("should_apply")
    is_borderline = score >= min_score - BORDERLINE_SCORE_MARGIN

    return fit in {"yes", "partial"} and should_apply and is_borderline


def format_score_reason(filter_category: str, filter_reason: str, score: int, min_score: int) -> str:
    return f"""
🔎 Чому показано:
- Фільтр: {filter_category} ({filter_reason})
- Score: {score}/100
- Мінімум: {min_score}/100
""".strip()


async def process_and_send_project(send_func, project: dict) -> bool:
    project_id = str(project.get("id"))
    attributes = project.get("attributes", {})

    title = attributes.get("name", "Без назви")
    description = attributes.get("description", "")
    budget = attributes.get("budget", "Не вказано")
    bids_count = (
        attributes.get("bid_count")
        or attributes.get("bids_count")
        or attributes.get("bids")
        or "Невідомо"
    )
    url = get_project_url(project, attributes)

    if not project_id:
        return False

    if is_seen(project_id):
        return False

    filter_result = classify_project(title, description)

    if filter_result.category == "bad":
        logger.info("Filtered by keywords: %s | %s", title, filter_result.reason)
        return False

    if filter_result.category == "maybe" and not ANALYZE_MAYBE_PROJECTS:
        logger.info("Filtered maybe project: %s | %s", title, filter_result.reason)
        return False

    numeric_bids_count = parse_bids_count(bids_count)
    if numeric_bids_count is not None and numeric_bids_count > MAX_BIDS_COUNT:
        return False

    project_text = build_project_text(
        title=title,
        description=description,
        budget=budget,
        bids_count=bids_count,
    )
    analysis_data, ai_used = await analyze_project_with_timeout(project_text)
    score = calculate_score(analysis_data)
    score += learning_bonus(title, description, get_good_bad_keywords())
    score = max(0, min(100, score))
    min_score = safe_setting_int(get_setting("min_score", "45"), 45)
    analysis = format_analysis(analysis_data)
    score_reason = format_score_reason(
        filter_result.category,
        filter_result.reason,
        score,
        min_score,
    )
    analysis_for_db = (
        f"Score: {score}/100\n"
        f"AI: {'так' if ai_used else 'ні'}\n\n"
        f"{score_reason}\n\n"
        f"{analysis}"
    )

    save_project(
        project_id=project_id,
        title=title,
        description=description,
        budget=budget,
        bids_count=bids_count,
        url=url,
        analysis=analysis_for_db,
    )

    if not should_send_project(analysis_data, score, min_score, ai_used):
        logger.info(
            "Filtered by score: %s | score=%s | min_score=%s",
            title,
            score,
            min_score,
        )
        return False

    useful = """
- Python / Telegram Bot API
- робота з API
- бази даних / SQLite / PostgreSQL
- парсинг даних
- HTML / CSS / JavaScript
- GitHub для показу коду
""".strip()

    message = f"""
🆕 Новий IT-проєкт

🎯 Score:
{score}/100

📌 Назва:
{title}

💰 Бюджет:
{budget}

👥 Ставок:
{bids_count}

📝 Опис:
{description[:1200]}

🛠 Що може знадобитись:
{useful}

🤖 AI-аналіз:
{analysis}

{score_reason}

🔗 Посилання:
{url}
""".strip()

    await send_func(
        message[:4000],
        reply_markup=project_keyboard(project_id),
    )

    logger.info("Sent project: %s | score=%s | ai=%s", title, score, ai_used)
    return True
