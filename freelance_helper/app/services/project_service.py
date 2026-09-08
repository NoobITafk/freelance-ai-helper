import asyncio

from ..ai_analyzer import (
    analyze_project_json,
    check_ollama_available,
    format_analysis,
    calculate_score,
    normalize_analysis,
    project_type,
)
from ..config import (
    AI_ANALYSIS_ENABLED,
    AI_TIMEOUT_SECONDS,
    ANALYZE_MAYBE_PROJECTS,
    HIGH_COMPETITION_BIDS,
    MAX_BIDS_COUNT,
    MIN_SCORE,
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
    count_good_keyword_matches,
    format_budget_display,
    learning_bonus,
    should_skip_high_competition,
)
from ..bot.keyboards import project_keyboard
from ..logger import logger

BORDERLINE_SCORE_MARGIN = 10
STRONG_TECH_KEYWORDS = {
    "python",
    "django",
    "fastapi",
    "flask",
    "react",
    "vue",
    "next.js",
    "nextjs",
    "typescript",
    "javascript",
    "api",
    "openai",
    "ai",
    "backend",
    "frontend",
    "crm",
    "supabase",
    "postgresql",
    "mysql",
    "sqlite",
}


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


def values_text(value) -> str:
    if value is None:
        return ""

    if isinstance(value, str):
        return value.strip()

    if isinstance(value, dict):
        parts = []
        for key in ("name", "title", "slug", "id"):
            item = value.get(key)
            if item:
                parts.append(str(item).strip())
        return " ".join(parts)

    if isinstance(value, list):
        return ", ".join(part for item in value if (part := values_text(item)))

    return str(value).strip()


def extract_project_tags(attributes: dict) -> str:
    fields = (
        "skills",
        "skill",
        "categories",
        "category",
        "tags",
        "specializations",
        "service",
    )
    parts = [values_text(attributes.get(field)) for field in fields]
    return ", ".join(part for part in parts if part)


def description_with_tags(description: str, tags_text: str) -> str:
    description = str(description or "").strip()

    if not tags_text:
        return description

    return f"{description}\n\nТеги/категорії: {tags_text}".strip()


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
    tags_text: str = "",
) -> str:
    return f"""
Назва: {title}
Бюджет: {budget}
Кількість ставок: {bids_count}
Теги/категорії: {tags_text or "Не вказано"}

Опис:
{description}
""".strip()


FALLBACK_AI_UNAVAILABLE = "AI unavailable, used fallback rules"
FALLBACK_AI_DISABLED = "AI disabled, used fallback rules"


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
    budget,
) -> tuple[dict, bool, str, str]:
    ai_setting = get_setting("AI_ANALYSIS_ENABLED")
    if ai_setting is None:
        ai_setting = get_setting("ai_enabled")
    ai_enabled = setting_bool(ai_setting, AI_ANALYSIS_ENABLED)

    def rules_fallback() -> dict:
        return build_rules_fallback_analysis(
            filter_result,
            title,
            description,
            numeric_bids_count,
            budget,
        )

    if not ai_enabled:
        logger.info("AI disabled in settings, using fallback rules")
        return rules_fallback(), False, "", "disabled"

    ollama_ok, ollama_reason = await asyncio.to_thread(check_ollama_available)

    if not ollama_ok:
        logger.warning("Ollama unavailable, using fallback rules: %s", ollama_reason)
        return rules_fallback(), False, ollama_reason, "unavailable"

    user_profile = get_setting("user_profile", USER_PROFILE)

    try:
        raw_analysis = await asyncio.wait_for(
            asyncio.to_thread(analyze_project_json, project_text, user_profile),
            timeout=AI_TIMEOUT_SECONDS,
        )
        return normalize_analysis(raw_analysis), True, "", ""

    except Exception as error:
        logger.exception("AI analysis failed, using fallback rules")
        return rules_fallback(), False, str(error), "unavailable"


def should_send_project(analysis_data: dict, score: int, min_score: int, ai_used: bool) -> bool:
    if score >= min_score:
        return True

    if not ai_used:
        return False

    fit = analysis_data.get("fit")
    should_apply = analysis_data.get("should_apply")
    is_borderline = score >= min_score - BORDERLINE_SCORE_MARGIN

    return fit in {"yes", "partial"} and should_apply and is_borderline


def protect_strong_technical_match(
    analysis_data: dict,
    filter_result,
    good_matches: list[str],
) -> dict:
    if filter_result.category != "good":
        return analysis_data

    strong_matches = {
        match.lower()
        for match in good_matches
        if match.lower() in STRONG_TECH_KEYWORDS
    }

    if len(strong_matches) < 2:
        return analysis_data

    if analysis_data.get("fit") != "no":
        return analysis_data

    success_chance = int(analysis_data.get("success_chance", 0))
    difficulty = int(analysis_data.get("difficulty", 10))
    budget_ok = analysis_data.get("budget_ok")

    if len(strong_matches) >= 4:
        fixed_analysis = dict(analysis_data)
        fixed_analysis["fit"] = "partial"
        fixed_analysis["should_apply"] = True
        fixed_analysis["manual_review"] = True
        fixed_analysis["success_chance"] = max(55, success_chance)
        fixed_analysis["reason"] = (
            "Явний full-stack/AI технічний проєкт для ручного перегляду: "
            f"{', '.join(sorted(strong_matches)[:7])}. "
            "AI вважає ризик високим, але проєкт не треба ховати автоматично."
        )
        return fixed_analysis

    if success_chance < 50 or difficulty > 6 or budget_ok == "no":
        return analysis_data

    fixed_analysis = dict(analysis_data)
    fixed_analysis["fit"] = "partial"
    fixed_analysis["should_apply"] = True
    fixed_analysis["manual_review"] = True
    fixed_analysis["risk"] = max(5, int(fixed_analysis.get("risk", 5)))
    fixed_analysis["reason"] = (
        "Сильний технічний збіг зі стеком проєкту: "
        f"{', '.join(sorted(strong_matches)[:5])}. "
        "AI-песимізм знижено до partial, бо задача виглядає короткою і технічно релевантною."
    )
    return fixed_analysis


def human_why_fit(kind: str, good_matches: list[str] | None, raw_reason: str) -> str:
    raw = str(raw_reason or "").strip()
    if raw and not raw.startswith("IT keywords:") and not raw.startswith("Fallback rules:"):
        return raw

    descriptions = {
        "telegram_bot": "розробка Telegram-бота (кнопки, меню, збереження заявок)",
        "parsing": "збір даних із сайту в таблицю (парсинг без дублікатів)",
        "backend": "розробка бекенду та API (робота з базою даних)",
        "api": "підключення та налаштування зовнішнього API",
        "frontend": "розробка веб-інтерфейсу (адаптивність, форми)",
        "html_css": "акуратна верстка сторінки під смартфони та комп'ютери",
        "wordpress": "правки та доопрацювання сайту на WordPress",
        "excel": "автоматизація обробки таблиць та звітів",
        "ai_integration": "підключення штучного інтелекту (ChatGPT / AI)",
    }
    desc = descriptions.get(kind, "проєкт за вашим технічним профілем")
    if good_matches:
        top = [m.capitalize() if len(m) > 3 else m.upper() for m in good_matches[:3]]
        return f"{desc} ({', '.join(top)})"
    return desc


def format_risks(analysis_data: dict, numeric_bids_count: int | None) -> str:
    risk_val = int(analysis_data.get("risk", 4))
    factors = []

    competition = str(analysis_data.get("competition", "unknown")).lower()
    if competition in {"high", "very_high"} or (numeric_bids_count is not None and numeric_bids_count >= 20):
        factors.append(f"багато ставок: {numeric_bids_count}")
    elif numeric_bids_count is not None and numeric_bids_count > 10:
        factors.append(f"ставок: {numeric_bids_count}")

    if analysis_data.get("budget_ok") == "no":
        factors.append("неясний бюджет")

    difficulty = int(analysis_data.get("difficulty", 5))
    if difficulty >= 8:
        factors.append("висока складність")

    if not factors:
        if risk_val <= 3:
            return f"🟢 низький ({risk_val}/10)"
        if risk_val <= 6:
            return f"🟡 помірний ({risk_val}/10)"
        return f"🔴 підвищений ({risk_val}/10)"

    joined = ", ".join(factors)
    if risk_val <= 3:
        return f"🟢 низький ({risk_val}/10) • {joined}"
    if risk_val <= 6:
        return f"🟡 помірний ({risk_val}/10) • {joined}"
    return f"🔴 підвищений ({risk_val}/10) • {joined}"


def format_project_message(
    title: str,
    budget,
    bids_count,
    url: str,
    score: int,
    analysis_data: dict,
    filter_result,
    numeric_bids_count: int | None = None,
    good_matches: list[str] | None = None,
    project_dict: dict | None = None,
    **_kwargs,
) -> str:
    kind = project_type(project_dict) if project_dict else "it_general"
    stack_names = {
        "telegram_bot": "Telegram-бот",
        "backend": "Backend / API",
        "frontend": "Frontend / Веб",
        "ai_integration": "AI / Інтеграція",
        "wordpress": "WordPress",
        "parsing": "Парсинг даних",
        "sheets_excel": "Google Sheets / Excel",
        "html_css": "HTML / CSS верстка",
        "python_script": "Python скрипт",
    }
    stack_label = stack_names.get(kind, "IT-розробка")
    if good_matches:
        unique_matches = []
        for match in good_matches:
            cap = match.capitalize() if len(match) > 3 else match.upper()
            if cap not in unique_matches:
                unique_matches.append(cap)
        top_tech = ", ".join(unique_matches[:4])
        stack_line = f"{stack_label} ({top_tech})"
    else:
        stack_line = stack_label

    raw_why = analysis_data.get("reason") or filter_result.reason
    why_fit = human_why_fit(kind, good_matches, raw_why)
    risk_info = format_risks(analysis_data, numeric_bids_count)

    lines = [
        f"🚀 {title}",
        "",
        f"💰 Бюджет: {budget}  •  👥 Ставок: {bids_count}  •  🎯 Score: {score}/100",
        f"🛠 Стек: {stack_line}",
        f"💡 Чому підходить: {why_fit}",
        f"⚠️ Ризик: {risk_info}",
        "",
        f"🔗 {url}",
    ]

    return "\n".join(lines)


def format_score_reason(
    filter_category: str, filter_reason: str, score: int, min_score: int
) -> str:
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


async def process_and_send_project(
    send_func, project: dict, debug_stats: dict | None = None
) -> bool:
    raw_project_id = project.get("id")
    project_id = str(raw_project_id) if raw_project_id is not None else ""
    attributes = project.get("attributes", {})

    title = attributes.get("name", "Без назви")
    description = attributes.get("description", "")
    tags_text = extract_project_tags(attributes)
    stored_description = description_with_tags(description, tags_text)
    budget = format_budget_display(attributes.get("budget"))
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

    filter_result = classify_project(title, description, tags_text)

    if filter_result.category == "bad":
        if debug_stats is not None:
            debug_stats["basic_rejected"] += 1
        reason = f"skipped: {filter_result.reason}"
        save_project_status(
            project_id,
            title,
            stored_description,
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
            stored_description,
            budget,
            bids_count,
            url,
            status="skipped",
            reason=reason,
        )
        logger.info("Filtered maybe project: %s | %s", title, reason)
        return False

    numeric_bids_count = parse_bids_count(bids_count)
    good_matches = count_good_keyword_matches(title, description, tags_text)

    is_strong_tech = (
        any(k in STRONG_TECH_KEYWORDS for k in good_matches)
        or len(good_matches) >= 2
    )
    bids_limit = HIGH_COMPETITION_BIDS if is_strong_tech else MAX_BIDS_COUNT

    if numeric_bids_count is not None and numeric_bids_count > bids_limit:
        if debug_stats is not None:
            debug_stats["competition_skipped"] += 1
        reason = f"skipped: {numeric_bids_count} ставок > ліміту {bids_limit}"
        save_project_status(
            project_id,
            title,
            stored_description,
            budget,
            bids_count,
            url,
            status="skipped",
            reason=reason,
        )
        logger.info("Filtered by max bids: %s | %s", title, reason)
        return False

    if should_skip_high_competition(numeric_bids_count, good_matches):
        if debug_stats is not None:
            debug_stats["competition_skipped"] += 1
        reason = f"skipped: {numeric_bids_count} ставок, слабка IT-релевантність"
        save_project_status(
            project_id,
            title,
            stored_description,
            budget,
            bids_count,
            url,
            status="skipped",
            reason=reason,
        )
        logger.info("Filtered by high competition: %s | %s", title, reason)
        return False

    analysis_data = build_rules_fallback_analysis(
        filter_result,
        title,
        stored_description,
        numeric_bids_count,
        budget,
    )
    analysis_data = protect_strong_technical_match(
        analysis_data,
        filter_result,
        good_matches,
    )

    if debug_stats is not None:
        debug_stats["fallback_used"] += 1

    score = int(analysis_data.get("success_chance", 0))
    score += learning_bonus(title, stored_description, get_good_bad_keywords())
    score = max(0, min(100, score))
    min_score = safe_setting_int(get_setting("min_score", str(MIN_SCORE)), MIN_SCORE)
    if analysis_data.get("manual_review"):
        score = max(score, min_score)

    project_dict = {
        "title": title,
        "description": stored_description,
        "budget": budget,
        "bids_count": bids_count,
        "url": url,
    }
    p_type = project_type(project_dict)

    analysis_for_db = (
        f"Score: {score}/100\n"
        f"Тип: {p_type}\n"
        f"Суть: {analysis_data.get('summary', '')}\n"
        f"Причина: {filter_result.reason}"
    )

    if score < min_score:
        if debug_stats is not None:
            debug_stats["low_score_skipped"] += 1
        reason = f"skipped: score {score}/100 нижче MIN_SCORE {min_score}/100"
        save_project_status(
            project_id,
            title,
            stored_description,
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

    send_reason = f"sent: {filter_result.reason}; score {score}/100"
    save_project_status(
        project_id,
        title,
        stored_description,
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
        numeric_bids_count=numeric_bids_count,
        good_matches=good_matches,
        project_dict=project_dict,
    )

    await send_func(
        message[:4000],
        reply_markup=project_keyboard(project_id),
    )

    if debug_stats is not None:
        debug_stats["sent"] += 1

    logger.info("Sent project: %s | score=%s", title, score)
    return True
