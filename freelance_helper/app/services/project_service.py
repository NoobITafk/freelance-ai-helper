import asyncio

from app.ai_analyzer import analyze_project_json, format_analysis, calculate_score
from app.database import (
    is_seen,
    save_project,
    get_setting,
    get_good_bad_keywords,
)
from app.rules import basic_filter, learning_bonus
from app.bot.keyboards import project_keyboard
from app.logger import logger


AI_TIMEOUT_SECONDS = 40
MAX_BIDS_COUNT = 40


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

    if not basic_filter(title, description):
        logger.info("Filtered by keywords: %s", title)
        return False

    numeric_bids_count = parse_bids_count(bids_count)
    if numeric_bids_count is not None and numeric_bids_count > MAX_BIDS_COUNT:
        return False

    useful = """
- Python / Telegram Bot API
- робота з API
- бази даних / SQLite / PostgreSQL
- парсинг даних
- HTML / CSS / JavaScript
- GitHub для показу коду
""".strip()

    save_project(
        project_id=project_id,
        title=title,
        description=description,
        budget=budget,
        bids_count=bids_count,
        url=url,
        analysis="AI ще не запускався",
    )

    message = f"""
🆕 Новий IT-проєкт

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

🔗 Посилання:
{url}
""".strip()

    await send_func(
        message[:4000],
        reply_markup=project_keyboard(project_id),
    )

    logger.info("Sent project without AI: %s", title)
    return True