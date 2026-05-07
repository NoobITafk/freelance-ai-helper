GOOD_KEYWORDS = [
    "python",
    "c#",
    "html",
    "css",
    "sql",
    "telegram",
    "bot",
    "бот",
    "парсер",
    "парсинг",
    "excel",
    "скрипт",
    "автоматизація",
    "automation",
    "api",
    "backend",
    "fastapi",
    "django",
    "flask",

]

BAD_KEYWORDS = [
    "crypto",
    "крипта",
    "casino",
    "казино",
    "nft",
    "trading",
    "трейдинг",

    "figma",
    "photoshop",
    "illustrator",
    "банер",
    "banner",
    "листівка",
    "логотип",
    "logo",
    "дизайн",
    "design",

]


def basic_filter(title: str, description: str) -> bool:
    text = f"{title} {description}".lower()

    if any(word in text for word in BAD_KEYWORDS):
        return False

    return any(word in text for word in GOOD_KEYWORDS)


def learning_bonus(title: str, description: str, good_bad_keywords) -> int:
    text = f"{title} {description}".lower()
    good_rows, bad_rows = good_bad_keywords

    bonus = 0

    for good_title, good_description in good_rows:
        good_text = f"{good_title} {good_description}".lower()

        for word in GOOD_KEYWORDS:
            if word in text and word in good_text:
                bonus += 3

    for bad_title, bad_description in bad_rows:
        bad_text = f"{bad_title} {bad_description}".lower()

        for word in GOOD_KEYWORDS:
            if word in text and word in bad_text:
                bonus -= 3

    return max(-15, min(15, bonus))