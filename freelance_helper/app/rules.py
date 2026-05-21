import re
from dataclasses import dataclass


GOOD_KEYWORDS = [
    "python", "telegram", "bot", "бот", "api", "backend", "fastapi", "django", "flask",
    "parsing", "парсинг", "scraping", "parser", "html", "css", "javascript", "typescript",
    "wordpress", "sqlite", "postgresql", "mysql", "sql", "база даних",
    "excel", "google sheets", "google sheet", "automation", "автоматизація",
    "bug fix", "bugfix", "виправити помилку", "form", "форма", "landing", "лендінг",
    "docker", "linux", "bash", "інтеграція", "integration", "скрипт", "script",
    "node", "react", "vue", "bootstrap",
]

HARD_BAD_KEYWORDS = [
    "crypto", "крипта", "casino", "казино", "nft", "trading", "трейдинг", "forex",
    "blockchain", "блокчейн", "payment gateway", "платіжний шлюз", "meta app review",
    "facebook app review", "highload", "high load", "crm", "erp", "1с", "бухгалтерія",
]

SOFT_BAD_KEYWORDS = [
    "seo strategy", "seo стратег", "seo-стратег", "seo просування",
    "figma", "photoshop", "illustrator", "logo", "банер", "banner",
    "копірайт", "копірайтинг", "рерайт", "переклад", "перекладач",
    "translation", "translator", "smm", "таргет", "instagram", "tiktok",
    "реферат", "курсова", "дипломна", "tilda", "wix", "shopify",
    "дизайн", "design",
]


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

    hard_bad = [
        word
        for word in HARD_BAD_KEYWORDS
        if keyword_in_text(word, text_lower)
    ]

    if hard_bad:
        return FilterResult(
            category="bad",
            reason=f"Стоп-слово: {', '.join(hard_bad[:3])}",
        )

    good_matches = [
        word
        for word in GOOD_KEYWORDS
        if keyword_in_text(word, text_lower)
    ]

    if good_matches:
        return FilterResult(
            category="good",
            reason=f"IT keywords: {', '.join(good_matches[:5])}",
        )

    bad_matches = [
        word
        for word in SOFT_BAD_KEYWORDS
        if keyword_in_text(word, text_lower)
    ]

    if bad_matches:
        return FilterResult(
            category="bad",
            reason=f"Не IT keywords: {', '.join(bad_matches[:5])}",
        )

    return FilterResult(
        category="maybe",
        reason="Немає явних IT-слів, але немає жорстких стоп-слів.",
    )


def basic_filter(title: str, description: str) -> bool:
    return classify_project(title, description).category != "bad"


def count_good_keyword_matches(title: str, description: str) -> list[str]:
    text_lower = f"{title or ''} {description or ''}".lower()
    return [word for word in GOOD_KEYWORDS if keyword_in_text(word, text_lower)]


def estimate_competition(numeric_bids_count: int | None) -> str:
    if numeric_bids_count is None:
        return "unknown"

    if numeric_bids_count >= 40:
        return "very_high"

    if numeric_bids_count >= 21:
        return "high"

    if numeric_bids_count >= 11:
        return "medium"

    return "low"


def parse_budget_amount(budget) -> int | None:
    if budget is None:
        return None

    text = str(budget).lower().replace(" ", "")
    numbers = re.findall(r"\d+", text)

    if not numbers:
        return None

    return int(numbers[0])


def budget_score_adjustment(budget) -> tuple[int, str]:
    amount = parse_budget_amount(budget)

    if amount is None:
        return 0, "unknown"

    if 500 <= amount <= 5000:
        return 8, "yes"

    if amount > 15000:
        return -12, "no"

    if amount > 8000:
        return -6, "partial"

    return 2, "partial"


def competition_score_adjustment(numeric_bids_count: int | None) -> int:
    competition = estimate_competition(numeric_bids_count)

    if competition == "low":
        return 10

    if competition == "medium":
        return 0

    if competition == "high":
        return -12

    if competition == "very_high":
        return -22

    return 0


def should_skip_high_competition(
    numeric_bids_count: int | None,
    good_matches: list[str],
) -> bool:
    if numeric_bids_count is None or numeric_bids_count < 40:
        return False

    return len(good_matches) < 2


def calculate_rules_score(
    filter_result: FilterResult,
    good_matches: list[str],
    numeric_bids_count: int | None,
    budget,
) -> int:
    if filter_result.category == "good":
        score = 42 + min(30, len(good_matches) * 5)
    else:
        score = 34

    score += competition_score_adjustment(numeric_bids_count)
    score += budget_score_adjustment(budget)[0]

    return max(0, min(100, score))


def build_rules_fallback_analysis(
    filter_result: FilterResult,
    title: str,
    description: str,
    numeric_bids_count: int | None,
    budget,
) -> dict:
    good_matches = count_good_keyword_matches(title, description)
    competition = estimate_competition(numeric_bids_count)
    budget_delta, budget_ok = budget_score_adjustment(budget)
    score = calculate_rules_score(
        filter_result,
        good_matches,
        numeric_bids_count,
        budget,
    )

    if filter_result.category == "good":
        fit = "yes"
        summary = f"Fallback rules: {', '.join(good_matches[:5]) or 'IT keywords'}"
        risk = 4
    else:
        fit = "partial"
        summary = "Fallback rules: немає явних IT-слів"
        risk = 6

    if competition in {"high", "very_high"}:
        risk = min(10, risk + 2)

    if budget_ok == "no":
        risk = min(10, risk + 2)

    return {
        "fit": fit,
        "summary": summary,
        "difficulty": 5,
        "risk": risk,
        "success_chance": score,
        "competition": competition,
        "budget_ok": budget_ok,
        "should_apply": score >= 40,
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

        if any(keyword_in_text(word, good_text) for word in matched_keywords):
            bonus += 3

    for bad_title, bad_description in bad_rows:
        bad_text = f"{bad_title or ''} {bad_description or ''}".lower()

        if any(keyword_in_text(word, bad_text) for word in matched_keywords):
            bonus -= 3

    return max(-15, min(15, bonus))
