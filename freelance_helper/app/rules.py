import ast
import re
from dataclasses import dataclass

GOOD_KEYWORDS = [
    "python",
    "telegram",
    "bot",
    "бот",
    "api",
    "backend",
    "fastapi",
    "django",
    "flask",
    "webhook",
    "вебхук",
    "selenium",
    "playwright",
    "beautifulsoup",
    "bs4",
    "requests",
    "pandas",
    "openai",
    "chatgpt",
    "llm",
    "ai",
    "штучний інтелект",
    "parsing",
    "парсинг",
    "scraping",
    "parser",
    "html",
    "css",
    "javascript",
    "typescript",
    "wordpress",
    "opencart",
    "опенкарт",
    "shopify",
    "prestashop",
    "woocommerce",
    "sqlite",
    "postgresql",
    "mysql",
    "mongodb",
    "firebase",
    "sql",
    "database",
    "база даних",
    "бд",
    "авторизація",
    "authorization",
    "authentication",
    "excel",
    "google sheets",
    "google sheet",
    "automation",
    "автоматизація",
    "bug fix",
    "bugfix",
    "виправити помилку",
    "form",
    "форма",
    "landing",
    "лендінг",
    "docker",
    "linux",
    "bash",
    "інтеграція",
    "integration",
    "скрипт",
    "script",
    "node",
    "node.js",
    "next",
    "next.js",
    "nextjs",
    "react",
    "vue",
    "nuxt",
    "angular",
    "svelte",
    "frontend",
    "фронтенд",
    "fullstack",
    "фулстек",
    "база данных",
    "базы данных",
    "бази даних",
    "доработка",
    "доработки",
    "доробка",
    "доробки",
    "правки",
    "код",
    "code",
    "dev",
    "supabase",
    "vercel",
    "render",
    "dashboard",
    "адмін",
    "адмінка",
    "кабінет",
    "crm",
    "bootstrap",
    "tailwind",
    "веб-розробка",
    "розробка сайту",
    "розробка сайтів",
    "створення сайту",
    "створення сайтів",
    "інтернет-магазин",
    "інтернет магазин",
    "вебсайт",
    "веб-сайт",
    "телеграм-бот",
    "телеграм бот",
    "telegram-bot",
    "бот для",
    "парсинг даних",
    "збір даних",
    "програміст",
    "программист",
    "розробник",
    "разработчик",
    "aiogram",
    "pytelegrambotapi",
    "telebot",
    "веб-додаток",
    "веб додаток",
    "flutter",
    "react native",
    "android",
    "ios",
    "swift",
    "kotlin",
    "nginx",
    "vps",
    "деплой",
    "deploy",
]

HARD_BAD_KEYWORDS = [
    "crypto",
    "крипта",
    "casino",
    "казино",
    "nft",
    "trading",
    "трейдинг",
    "forex",
    "blockchain",
    "блокчейн",
    "payment gateway",
    "платіжний шлюз",
    "meta app review",
    "facebook app review",
    "highload",
    "high load",
    "erp",
    "1с",
    "бухгалтерія",
]

SOFT_BAD_KEYWORDS = [
    "seo",
    "seo strategy",
    "seo стратег",
    "seo-стратег",
    "seo просування",
    "figma",
    "photoshop",
    "illustrator",
    "logo",
    "логотип",
    "векторизація",
    "векторизувати",
    "vector",
    "банер",
    "banner",
    "презентація",
    "presentation",
    "поліграфія",
    "поліграф",
    "ілюстрація",
    "ілюстрації",
    "illustration",
    "відеомонтаж",
    "video editing",
    "копірайт",
    "копірайтинг",
    "рерайт",
    "переклад",
    "перекладач",
    "translation",
    "translator",
    "smm",
    "таргет",
    "instagram",
    "tiktok",
    "реферат",
    "курсова",
    "дипломна",
    "tilda",
    "wix",
    "shopify",
    "дизайн",
    "design",
    "озвучка",
    "озвучки",
    "озвучення",
    "озвучити",
    "диктор",
    "диктора",
    "дикторський",
    "аудіо",
    "голос",
    "голосом",
    "voice",
    "voiceover",
    "audio",
    "sound",
    "саунд",
    "звукозапис",
    "вокал",
    "музика",
    "пісня",
    "трек",
    "відео",
    "відеоролик",
    "ролик",
    "монтаж",
    "зйомка",
    "зйомки",
    "відеозйомка",
    "титри",
    "субтитри",
    "анімація",
    "animation",
    "motion",
    "моушн",
    "after effects",
    "premiere",
    "davinci",
    "capcut",
    "ретуш",
    "фотосесія",
    "фотограф",
    "обробка фото",
    "стаття",
    "пост",
    "контент",
    "сценарій",
    "вірш",
    "книга",
    "набір тексту",
    "транскрибація",
    "розшифровка",
    "дзвінки",
    "обдзвін",
    "холодні дзвінки",
    "менеджер з продажу",
    "дропшипінг",
]

WEAK_GOOD_KEYWORDS = {
    "wordpress",
    "excel",
    "html",
    "css",
    "bootstrap",
    "landing",
    "лендінг",
    "form",
    "форма",
}


@dataclass(frozen=True)
class FilterResult:
    category: str
    reason: str


def keyword_in_text(word: str, text_lower: str) -> bool:
    keyword = word.lower()
    return re.search(rf"(?<!\w){re.escape(keyword)}(?!\w)", text_lower) is not None


def classify_project(title: str, description: str, extra_text: str = "") -> FilterResult:
    text = f"{title or ''} {description or ''} {extra_text or ''}"
    text_lower = text.lower()

    hard_bad = []
    for word in HARD_BAD_KEYWORDS:
        if word == "crypto":
            cleaned = re.sub(r"cryptobot|crypto pay|cryptopay|@cryptobot", "", text_lower)
            if re.search(r"(?<!\w)crypto(?!\w)", cleaned):
                hard_bad.append(word)
        elif keyword_in_text(word, text_lower):
            hard_bad.append(word)

    if hard_bad:
        return FilterResult(
            category="bad",
            reason=f"Стоп-слово: {', '.join(hard_bad[:3])}",
        )

    bad_matches = [word for word in SOFT_BAD_KEYWORDS if keyword_in_text(word, text_lower)]
    good_matches = [word for word in GOOD_KEYWORDS if keyword_in_text(word, text_lower)]
    strong_good_matches = [
        word for word in good_matches if word.lower() not in WEAK_GOOD_KEYWORDS
    ]

    if bad_matches and not strong_good_matches and len(good_matches) < 2:
        return FilterResult(
            category="bad",
            reason=f"Не IT keywords: {', '.join(bad_matches[:5])}",
        )

    if good_matches:
        return FilterResult(
            category="good",
            reason=f"IT keywords: {', '.join(good_matches[:5])}",
        )

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


def count_good_keyword_matches(
    title: str,
    description: str,
    extra_text: str = "",
) -> list[str]:
    text_lower = f"{title or ''} {description or ''} {extra_text or ''}".lower()
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


def parse_budget_info(budget) -> tuple[int | None, str, int | None]:
    """
    Parses raw budget into (amount, currency, amount_uah).
    Supports dicts (Freelancehunt v2 API) and strings ('3000 грн', '$300', etc.).
    """
    if budget is None:
        return None, "UAH", None

    currency = "UAH"
    amount = None

    if isinstance(budget, str) and budget.strip().startswith("{") and budget.strip().endswith("}"):
        try:
            parsed_dict = ast.literal_eval(budget.strip())
            if isinstance(parsed_dict, dict):
                budget = parsed_dict
        except (ValueError, SyntaxError):
            pass

    if isinstance(budget, dict):
        raw_amount = budget.get("amount")
        if raw_amount is not None:
            try:
                amount = int(raw_amount)
            except (ValueError, TypeError):
                pass
        currency = str(budget.get("currency", "UAH")).upper()
    else:
        text = str(budget).lower().strip()
        if not text or text in {"не вказано", "none", "null"}:
            return None, "UAH", None

        if "$" in text or "usd" in text or "дол" in text:
            currency = "USD"
        elif "€" in text or "eur" in text or "євр" in text:
            currency = "EUR"
        elif "pln" in text or "злот" in text or "zł" in text:
            currency = "PLN"
        elif "грн" in text or "uah" in text:
            currency = "UAH"

        clean_digits = text.replace(" ", "").replace(",", "")
        numbers = re.findall(r"\d+", clean_digits)
        if numbers:
            try:
                amount = int(numbers[0])
            except ValueError:
                pass

    if amount is None:
        return None, currency, None

    rate = 1.0
    if currency == "USD":
        rate = 41.0
    elif currency == "EUR":
        rate = 44.0
    elif currency == "PLN":
        rate = 10.5

    amount_uah = int(amount * rate)
    return amount, currency, amount_uah


def parse_budget_amount(budget) -> int | None:
    _, _, amount_uah = parse_budget_info(budget)
    return amount_uah


def format_budget_display(budget) -> str:
    """Formats raw budget (dict or string) into a clean user-facing string."""
    if budget is None:
        return "Не вказано"

    if isinstance(budget, str) and budget.strip().startswith("{") and budget.strip().endswith("}"):
        try:
            parsed_dict = ast.literal_eval(budget.strip())
            if isinstance(parsed_dict, dict):
                budget = parsed_dict
        except (ValueError, SyntaxError):
            pass

    if isinstance(budget, dict):
        amount = budget.get("amount")
        currency = str(budget.get("currency", "UAH")).upper()
        if amount is not None:
            try:
                amount_int = int(amount)
                return f"{amount_int:,} {currency}".replace(",", " ")
            except (ValueError, TypeError):
                return f"{amount} {currency}"
        return "Не вказано"

    text = str(budget).strip()
    if not text or text.lower() in {"не вказано", "none", "null"}:
        return "Не вказано"

    return text


def budget_score_adjustment(budget) -> tuple[int, str]:
    _, _, amount_uah = parse_budget_info(budget)

    if amount_uah is None:
        return 0, "unknown"

    # Inadequately tiny budget (< 500 UAH / < $12)
    if amount_uah < 500:
        return -8, "no"

    # Micro task (500 - 1500 UAH / $12 - $36)
    if amount_uah < 1500:
        return 2, "partial"

    # Sweet spot for freelance tasks (1500 - 30 000 UAH / $36 - $730)
    if amount_uah <= 30000:
        return 8, "yes"

    # Solid high-budget projects (30 000 - 75 000 UAH / $730 - $1800)
    if amount_uah <= 75000:
        return 6, "yes"

    # Large / enterprise projects (> 75 000 UAH / > $1800)
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
    if filter_result.category == "bad":
        return 0

    if filter_result.category == "good":
        score = 42 + min(30, len(good_matches) * 5)
    else:
        score = 15 + (len(good_matches) * 5)

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

    good_matched = {word for word in GOOD_KEYWORDS if keyword_in_text(word, text)}
    bad_matched = {word for word in SOFT_BAD_KEYWORDS if keyword_in_text(word, text)}

    if not good_matched and not bad_matched:
        return 0

    bonus = 0

    if good_matched:
        for good_title, good_description in good_rows:
            good_text = f"{good_title or ''} {good_description or ''}".lower()
            if any(keyword_in_text(word, good_text) for word in good_matched):
                bonus += 3

        for bad_title, bad_description in bad_rows:
            bad_text = f"{bad_title or ''} {bad_description or ''}".lower()
            if any(keyword_in_text(word, bad_text) for word in good_matched):
                bonus -= 3

    if bad_matched:
        for bad_title, bad_description in bad_rows:
            bad_text = f"{bad_title or ''} {bad_description or ''}".lower()
            if any(keyword_in_text(word, bad_text) for word in bad_matched):
                bonus -= 4

    return max(-20, min(15, bonus))
