import re
from dataclasses import dataclass


GOOD_KEYWORDS = [
    "python", "api", "backend", "fastapi", "django", "flask",
    "sql", "postgresql", "mysql", "база даних",
    "docker", "linux", "bash", "сервер", "деплой",
    "telegram", "bot", "бот", "ai", "штучний інтелект",
    "c#", ".net", "java", "c++", "архітектура",
    "javascript", "typescript", "react", "vue", "node",
    "парсинг", "скрипт", "автоматизація", "інтеграція",
]

HARD_BAD_KEYWORDS = [
    "crypto", "крипта", "casino", "казино", "nft", "trading", "трейдинг",
    "1с", "bas", "бухгалтерія",
]

SOFT_BAD_KEYWORDS = [
    "figma", "photoshop", "illustrator", "дизайн", "logo", "банер",
    "копірайт", "рерайт", "переклад", "seo", "просування", "таргет",
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


def classify_project(title: str, description: str) -> FilterResult:
    text = f"{title or ''} {description or ''}"

    hard_bad = HARD_BAD_PATTERN.search(text)

    if hard_bad:
        return FilterResult(
            category="bad",
            reason=f"Стоп-слово: {hard_bad.group(0)}",
        )

    good = GOOD_PATTERN.search(text)

    if good:
        return FilterResult(
            category="good",
            reason=f"Збіг по ключовому слову: {good.group(0)}",
        )

    soft_bad = SOFT_BAD_PATTERN.search(text)

    if soft_bad:
        return FilterResult(
            category="bad",
            reason=f"Схоже не на IT-задачу: {soft_bad.group(0)}",
        )

    return FilterResult(
        category="maybe",
        reason="Немає явного збігу, але й немає жорстких стоп-слів.",
    )


def basic_filter(title: str, description: str) -> bool:
    return classify_project(title, description).category != "bad"


def learning_bonus(title: str, description: str, good_bad_keywords) -> int:
    text = f"{title or ''} {description or ''}".lower()
    good_rows, bad_rows = good_bad_keywords

    matched_keywords = {
        word
        for word in GOOD_KEYWORDS
        if word in text
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
