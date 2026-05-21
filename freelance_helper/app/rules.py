import re
from dataclasses import dataclass


GOOD_KEYWORDS = [
    "python", "api", "backend", "fastapi", "django", "flask",
    "sqlite", "postgresql", "mysql", "sql", "база даних",
    "docker", "linux", "bash", "сервер", "деплой",
    "telegram", "bot", "бот", "ai", "штучний інтелект",
    "c#", ".net", "asp.net", "java", "spring", "c++", "архітектура",
    "javascript", "typescript", "node", "react", "vue",
    "html", "css", "bootstrap",
    "парсинг", "scraping", "скрипт", "automation", "автоматизація",
    "інтеграція",
]

HARD_BAD_KEYWORDS = [
    "crypto", "крипта", "casino", "казино", "nft", "trading", "трейдинг",
    "1с", "bas", "бухгалтерія",
]

SOFT_BAD_KEYWORDS = [
    "figma", "photoshop", "illustrator", "дизайн", "design", "logo",
    "banner", "банер",
    "копірайт", "копірайтинг", "рерайт", "переклад", "перекладач",
    "translation", "translator", "seo", "smm",
    "просування", "таргет",
    "реферат", "курсова", "дипломна",
    "instagram", "tiktok",
    "wordpress", "tilda", "wix", "shopify",
    "excel", "word", "презентація"
]


GOOD_PATTERN = re.compile(
    "|".join(re.escape(word) for word in GOOD_KEYWORDS),
    re.IGNORECASE,
)

HARD_BAD_PATTERN = re.compile(
    "|".join(re.escape(word) for word in HARD_BAD_KEYWORDS),
    re.IGNORECASE,
)

SOFT_BAD_PATTERN = re.compile(
    "|".join(re.escape(word) for word in SOFT_BAD_KEYWORDS),
    re.IGNORECASE,
)


@dataclass(frozen=True)
class FilterResult:
    category: str
    reason: str


def keyword_in_text(word: str, text_lower: str) -> bool:
    keyword = word.lower()

    if len(keyword) <= 3:
        return re.search(rf"\b{re.escape(keyword)}\b", text_lower) is not None

    return keyword in text_lower


def classify_project(title: str, description: str) -> FilterResult:
    text = f"{title or ''} {description or ''}"
    text_lower = text.lower()

    hard_bad = HARD_BAD_PATTERN.search(text)

    if hard_bad:
        return FilterResult(
            category="bad",
            reason=f"Стоп-слово: {hard_bad.group(0)}",
        )

    good_matches = [
        word
        for word in GOOD_KEYWORDS
        if keyword_in_text(word, text_lower)
    ]

    if good_matches:
        return FilterResult(
            category="good",
            reason=f"знайдено GOOD_KEYWORDS: {', '.join(good_matches[:5])}",
        )

    bad_matches = [
        word
        for word in SOFT_BAD_KEYWORDS
        if keyword_in_text(word, text_lower)
    ]

    if bad_matches:
        return FilterResult(
            category="bad",
            reason=f"знайдено BAD_KEYWORDS: {', '.join(bad_matches[:5])}",
        )

    return FilterResult(
        category="maybe",
        reason="Немає явного збігу, але й немає жорстких стоп-слів.",
    )


def basic_filter(title: str, description: str) -> bool:
    return classify_project(title, description).category != "bad"


def count_good_keyword_matches(title: str, description: str) -> list[str]:
    text_lower = f"{title or ''} {description or ''}".lower()
    return [word for word in GOOD_KEYWORDS if keyword_in_text(word, text_lower)]


def estimate_competition(numeric_bids_count: int | None) -> str:
    if numeric_bids_count is None:
        return "unknown"

    if numeric_bids_count >= 25:
        return "high"

    if numeric_bids_count >= 10:
        return "medium"

    return "low"


def calculate_rules_score(
    filter_result: FilterResult,
    good_matches: list[str],
    numeric_bids_count: int | None,
) -> int:
    if filter_result.category == "good":
        score = 48 + min(27, len(good_matches) * 4)
    else:
        score = 36

    competition = estimate_competition(numeric_bids_count)

    if competition == "high":
        score -= 18
    elif competition == "medium":
        score -= 8
    elif competition == "low":
        score += 6

    return max(0, min(100, score))


def build_rules_fallback_analysis(
    filter_result: FilterResult,
    title: str,
    description: str,
    numeric_bids_count: int | None,
) -> dict:
    good_matches = count_good_keyword_matches(title, description)
    competition = estimate_competition(numeric_bids_count)
    score = calculate_rules_score(filter_result, good_matches, numeric_bids_count)

    if filter_result.category == "good":
        fit = "yes"
        should_apply = score >= 40
        summary = f"Rules: IT-ключові слова ({', '.join(good_matches[:5])})"
        risk = 4
        difficulty = 5
    else:
        fit = "partial"
        should_apply = score >= 40
        summary = "Rules: немає явних IT-слів, але немає стоп-слів"
        risk = 6
        difficulty = 6

    return {
        "fit": fit,
        "summary": summary,
        "difficulty": difficulty,
        "risk": risk,
        "success_chance": score,
        "competition": competition,
        "budget_ok": "unknown",
        "should_apply": should_apply,
        "reason": filter_result.reason,
        "questions": [
            "Який точний обсяг роботи?",
            "Який формат результату очікується?",
            "Які терміни виконання?",
        ],
    }


def learning_bonus(title: str, description: str, good_bad_keywords) -> int:
    text = f"{title or ''} {description or ''}".lower()
    good_rows, bad_rows = good_bad_keywords

    matched_keywords = {
        word
        for word in GOOD_KEYWORDS
        if keyword_in_text(word, text)
    }

    if not matched_keywords:
        return 0

    bonus = 0

    for good_title, good_description in good_rows:
        good_text = f"{good_title or ''} {good_description or ''}".lower()

        if any(word in good_text for word in matched_keywords):
            bonus += 3

    for bad_title, bad_description in bad_rows:
        bad_text = f"{bad_title or ''} {bad_description or ''}".lower()

        if any(word in bad_text for word in matched_keywords):
            bonus -= 3

    return max(-15, min(15, bonus))
