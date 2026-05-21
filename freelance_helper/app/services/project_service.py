import asyncio

from ..ai_analyzer import (
    analyze_project_json,
    check_ollama_available,
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
from ..rules import (
    build_rules_fallback_analysis,
    classify_project,
    learning_bonus,
)
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


FALLBACK_NOTICE = "AI unavailable, used fallback rules"


def setting_bool(value, default: bool) -> bool:
    if value is None:
        return default

    return str(value).lower() in {"1", "true", "yes", "on", "так"}


async def analyze_project_with_timeout(
    project_text: str,
    filter_result,
    title: str,
    description: str,
    numeric_bids_count: int | None,
) -> tuple[dict, bool, str]:
    ai_setting = get_setting("AI_ANALYSIS_ENABLED")
    if ai_setting is None:
        ai_setting = get_setting("ai_enabled")
    ai_enabled = setting_bool(ai_setting, AI_ANALYSIS_ENABLED)

    if not ai_enabled:
        return (
            build_rules_fallback_analysis(filter_result, title, description, numeric_bids_count),
            False,
            "",
        )

    ollama_ok, ollama_reason = await asyncio.to_thread(check_ollama_available)

    if not ollama_ok:
        logger.warning("Ollama unavailable: %s", ollama_reason)
        return (
            build_rules_fallback_analysis(filter_result, title, description, numeric_bids_count),
            False,
            f"Ollama недоступна: {ollama_reason}",
        )

    user_profile = get_setting("user_profile", USER_PROFILE)

    try:
        raw_analysis = await asyncio.wait_for(
            asyncio.to_thread(analyze_project_json, project_text, user_profile),
            timeout=AI_TIMEOUT_SECONDS,
        )
        return normalize_analysis(raw_analysis), True, ""

    except Exception as error:
        logger.exception("AI analysis failed")
        return (
            build_rules_fallback_analysis(filter_result, title, description, numeric_bids_count),
            False,
            str(error),
        )


def should_send_project(analysis_data: dict, score: int, min_score: int, ai_used: bool) -> bool:
    if score >= min_score:
        return True

    if not ai_used:
        return False

    fit = analysis_data.get("fit")
    should_apply = analysis_data.get("should_apply")
    is_borderline = score >= min_score - BORDERLINE_SCORE_MARGIN

    return fit in {"yes", "partial"} and should_apply and is_borderline


def format_competition_note(analysis_data: dict, numeric_bids_count: int | None) -> str:
    competition = str(analysis_data.get("competition", "unknown")).lower()

    if competition == "high":
        return "⚠️ Висока конкуренція"

    if numeric_bids_count is not None and numeric_bids_count >= 25:
        return "⚠️ Висока конкуренція (багато ставок)"

    return ""


def format_project_message(
    title: str,
    budget,
    bids_count,
    url: str,
    score: int,
    analysis_data: dict,
    filter_result,
    ai_used: bool,
    numeric_bids_count: int | None,
    description: str,
) -> str:
    competition_note = format_competition_note(analysis_data, numeric_bids_count)
    why_fit = analysis_data.get("reason") or filter_result.reason
    risk = analysis_data.get("risk", "?")
    summary = analysis_data.get("summary", "")

    lines = [
        "🆕 Новий IT-проєкт",
        "",
        f"📌 Назва: {title}",
        f"💰 Бюджет: {budget}",
        f"👥 Ставок: {bids_count}",
        f"🔗 {url}",
        "",
        f"🎯 Score: {score}/100",
    ]

    if not ai_used:
        lines.append(FALLBACK_NOTICE)

    if competition_note:
        lines.append(competition_note)

    lines.extend([
        "",
        f"✅ Чому підходить: {why_fit}",
        f"⚠️ Ризики: {risk}/10 — {summary[:300]}",
    ])

    short_description = " ".join((description or "").split())
    if short_description:
        lines.extend(["", f"📝 Опис: {short_description[:800]}"])

    return "\n".join(lines)


def format_score_reason(filter_category: str, filter_reason: str, score: int, min_score: int) -> str:
    return f"""
🔎 Чому показано:
- Фільтр: {filter_category} ({filter_reason})
- Score: {score}/100
- Мінімум: {min_score}/100
""".strip()


def save_project_status(
    project_id: str,
    title: str,
    description: str,
    budget,
    bids_count,
    url: str,
    status: str,
    reason: str,
    score: int | None = None,
    analysis: str = "",
) -> None:
    save_project(
        project_id=project_id,
        title=title,
        description=description,
        budget=budget,
        bids_count=bids_count,
        url=url,
        analysis=analysis,
        status=status,
        score=score,
        reason=reason,
    )


async def process_and_send_project(send_func, project: dict, debug_stats: dict | None = None) -> bool:
    raw_project_id = project.get("id")
    project_id = str(raw_project_id) if raw_project_id is not None else ""
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
        if debug_stats is not None:
            debug_stats["basic_rejected"] += 1
        return False

    if is_seen(project_id):
        if debug_stats is not None:
            debug_stats["already_seen"] += 1
        return False

    filter_result = classify_project(title, description)

    if filter_result.category == "bad":
        if debug_stats is not None:
            debug_stats["basic_rejected"] += 1
        reason = f"skipped: {filter_result.reason}"
        save_project_status(
            project_id,
            title,
            description,
            budget,
            bids_count,
            url,
            status="skipped",
            reason=reason,
        )
        logger.info("Filtered by keywords: %s | %s", title, reason)
        return False

    if filter_result.category == "maybe" and not ANALYZE_MAYBE_PROJECTS:
        if debug_stats is not None:
            debug_stats["basic_rejected"] += 1
        reason = f"skipped: maybe-проєкти вимкнені ({filter_result.reason})"
        save_project_status(
            project_id,
            title,
            description,
            budget,
            bids_count,
            url,
            status="skipped",
            reason=reason,
        )
        logger.info("Filtered maybe project: %s | %s", title, reason)
        return False

    numeric_bids_count = parse_bids_count(bids_count)
    if numeric_bids_count is not None and numeric_bids_count > MAX_BIDS_COUNT:
        if debug_stats is not None:
            debug_stats["basic_rejected"] += 1
        reason = f"skipped: bids_count {numeric_bids_count} більше MAX_BIDS_COUNT {MAX_BIDS_COUNT}"
        save_project_status(
            project_id,
            title,
            description,
            budget,
            bids_count,
            url,
            status="skipped",
            reason=reason,
        )
        logger.info("Filtered by bids_count: %s | %s", title, reason)
        return False

    project_text = build_project_text(
        title=title,
        description=description,
        budget=budget,
        bids_count=bids_count,
    )
    analysis_data, ai_used, ai_error = await analyze_project_with_timeout(
        project_text,
        filter_result,
        title,
        description,
        numeric_bids_count,
    )

    if debug_stats is not None:
        if ai_used:
            debug_stats["ai_analyzed"] += 1
        else:
            debug_stats["fallback_used"] += 1

    if ai_error and debug_stats is not None:
        debug_stats["ai_errors"].append(ai_error)

    if ai_used:
        score = calculate_score(analysis_data)
    else:
        score = int(analysis_data.get("success_chance", 0))

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
    if not ai_used:
        analysis_for_db = f"{FALLBACK_NOTICE}\n\n{analysis_for_db}"

    if not should_send_project(analysis_data, score, min_score, ai_used):
        if debug_stats is not None:
            debug_stats["low_score_skipped"] += 1
        reason = f"skipped: score {score}/100 нижче MIN_SCORE {min_score}/100"

        if analysis_data.get("fit") == "no":
            reason = f"skipped: AI вирішив, що проєкт не підходить; score {score}/100"

        save_project_status(
            project_id,
            title,
            description,
            budget,
            bids_count,
            url,
            status="skipped",
            reason=reason,
            score=score,
            analysis=analysis_for_db,
        )
        logger.info(
            "Filtered by score: %s | score=%s | min_score=%s | reason=%s",
            title,
            score,
            min_score,
            reason,
        )
        return False

    send_reason = (
        f"sent: {filter_result.reason}; score {score}/100; "
        f"AI: {'OK' if ai_used else 'fallback'}"
    )

    save_project_status(
        project_id,
        title,
        description,
        budget,
        bids_count,
        url,
        status="sent",
        reason=send_reason,
        score=score,
        analysis=analysis_for_db,
    )

    message = format_project_message(
        title=title,
        budget=budget,
        bids_count=bids_count,
        url=url,
        score=score,
        analysis_data=analysis_data,
        filter_result=filter_result,
        ai_used=ai_used,
        numeric_bids_count=numeric_bids_count,
        description=description,
    )

    if ai_used:
        message = f"{message}\n\n🤖 AI-аналіз:\n{analysis}\n\n{score_reason}"

    await send_func(
        message[:4000],
        reply_markup=project_keyboard(project_id),
    )

    if debug_stats is not None:
        debug_stats["sent"] += 1

    logger.info("Sent project: %s | score=%s | ai=%s", title, score, ai_used)
    return True
