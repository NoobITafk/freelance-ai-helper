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
        logger.info("Skipped project without ID")
        return False

    if is_seen(project_id):
        logger.info("Skipped seen project: %s", title)
        return False

    if not basic_filter(title, description):
        logger.info("Filtered by keywords: %s", title)
        return False

    numeric_bids_count = parse_bids_count(bids_count)

    if numeric_bids_count is not None and numeric_bids_count > MAX_BIDS_COUNT:
        logger.info(
            "Filtered by bids count: %s | bids=%s | max=%s",
            title,
            numeric_bids_count,
            MAX_BIDS_COUNT,
        )
        return False

    project_text = f"""
Назва: {title}
Бюджет: {budget}
Кількість ставок: {bids_count}
Посилання: {url}

Опис:
{description}
"""

    loop = asyncio.get_running_loop()

    try:
        analysis_data = await asyncio.wait_for(
            loop.run_in_executor(
                None,
                analyze_project_json,
                project_text,
            ),
            timeout=AI_TIMEOUT_SECONDS,
        )

    except asyncio.TimeoutError:
        logger.warning("Ollama timeout: %s", title)
        return False

    except Exception:
        logger.exception("AI analysis error: %s", title)
        return False

    score = calculate_score(analysis_data)

    bonus = learning_bonus(
        title,
        description,
        get_good_bad_keywords(),
    )

    final_score = score + bonus
    min_score = int(get_setting("min_score", "45"))

    if final_score < min_score:
        logger.info(
            "Filtered by score: %s | score=%s | bonus=%s | final=%s | min=%s",
            title,
            score,
            bonus,
            final_score,
            min_score,
        )
        return False

    analysis = format_analysis(analysis_data)

    save_project(
        project_id=project_id,
        title=title,
        description=description,
        budget=budget,
        bids_count=bids_count,
        url=url,
        analysis=analysis,
    )

    message = f"""
🆕 Новий проєкт

📌 {title}
💰 Бюджет: {budget}
👥 Ставок: {bids_count}
🎯 Score: {final_score}/100
🔗 {url}

{analysis}
"""

    await send_func(
        message[:4000],
        reply_markup=project_keyboard(project_id),
    )

    logger.info("Sent project: %s | score=%s", title, final_score)
    return True