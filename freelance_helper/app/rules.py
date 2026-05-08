import re


GOOD_KEYWORDS = [
    "python", "api", "backend", "fastapi", "django", "flask",
    "sql", "postgresql", "mysql", "база даних",
    "docker", "linux", "bash", "сервер", "деплой",
    "telegram", "bot", "бот", "ai", "штучний інтелект",
    "c#", ".net", "java", "c++", "архітектура",
    "javascript", "typescript", "react", "vue", "node"
]

BAD_KEYWORDS = [
    "crypto", "крипта", "casino", "казино", "nft", "trading", "трейдинг",
    "figma", "photoshop", "illustrator", "дизайн", "logo", "банер",
    "копірайт", "рерайт", "текст", "переклад", "seo", "просування", "таргет",
    "wordpress", "tilda", "wix", "shopify",
    "1с", "bas", "бухгалтерія",
    "excel", "word", "презентація"
]


GOOD_PATTERN = re.compile(
    "|".join(re.escape(word) for word in GOOD_KEYWORDS),
    re.IGNORECASE,
)

BAD_PATTERN = re.compile(
    "|".join(re.escape(word) for word in BAD_KEYWORDS),
    re.IGNORECASE,
)


def basic_filter(title: str, description: str) -> bool:
    text = f"{title or ''} {description or ''}"

    if BAD_PATTERN.search(text):
        return False

    return GOOD_PATTERN.search(text) is not None


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