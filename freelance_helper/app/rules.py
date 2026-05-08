import re


GOOD_KEYWORDS = [
    "python",
    "c#",
    "csharp",
    "html",
    "css",
    "javascript",
    "js",
    "sql",
    "telegram",
    "bot",
    "бот",
    "парсер",
    "парсинг",
    "scraping",
    "parser",
    "excel",
    "xlsx",
    "csv",
    "скрипт",
    "script",
    "автоматизація",
    "automation",
    "api",
    "backend",
    "fastapi",
    "django",
    "flask",
    "selenium",
    "beautifulsoup",
    "bs4",
    "requests",
    "pandas",
]

BAD_KEYWORDS = [
    "crypto",
    "крипта",
    "casino",
    "казино",
    "nft",
    "trading",
    "трейдинг",
    "forex",
    "ставки",
    "беттинг",

    "figma",
    "photoshop",
    "illustrator",
    "canva",
    "банер",
    "banner",
    "листівка",
    "логотип",
    "logo",
    "дизайн",
    "design",
    "ui/ux",
    "ui",
    "ux",

    "копірайтинг",
    "copywriting",
    "рерайт",
    "rewrite",
    "переклад",
    "translation",
    "текст",
    "seo",
    "smm",
    "instagram",
    "tiktok",

    "erp",
    "crm архітектор",
    "архітектор",
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