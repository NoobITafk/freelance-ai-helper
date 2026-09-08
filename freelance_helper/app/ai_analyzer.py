import json
import re
from pathlib import Path
from typing import Any
import httpx
import requests

from .config import OLLAMA_MODEL, OLLAMA_URL, PROJECT_ROOT, USER_PROFILE

ANALYSIS_NUM_PREDICT = 500
TEXT_NUM_PREDICT = 500
AI_RAW_LOG_PATH = PROJECT_ROOT / "logs" / "ai_raw.log"
BID_VARIANTS = ("short", "technical", "cautious")

TECHNICAL_KEYWORDS = {
    "python",
    "telegram",
    "телеграм",
    "bot",
    "бот",
    "api",
    "fastapi",
    "django",
    "flask",
    "backend",
    "webhook",
    "вебхук",
    "парсинг",
    "parsing",
    "parser",
    "scraping",
    "selenium",
    "playwright",
    "beautifulsoup",
    "bs4",
    "requests",
    "pandas",
    "html",
    "css",
    "wordpress",
    "javascript",
    "typescript",
    "node",
    "node.js",
    "react",
    "vue",
    "sqlite",
    "postgresql",
    "mysql",
    "mongodb",
    "database",
    "база даних",
    "google sheets",
    "google sheet",
    "excel",
    "bugfix",
    "bug fix",
    "інтеграція",
    "integration",
    "форма",
    "form",
    "landing",
    "лендінг",
    "openai",
    "chatgpt",
    "llm",
    "ai",
    "штучний інтелект",
    "адмін",
    "адмінка",
    "dashboard",
    "crm",
}

NON_TECHNICAL_KEYWORDS = {
    "логотип": ("дизайн/логотип", "Illustrator/CorelDRAW/Figma/Inkscape"),
    "logo": ("дизайн/логотип", "Illustrator/CorelDRAW/Figma/Inkscape"),
    "векториза": ("векторизація зображення", "Illustrator/CorelDRAW/Inkscape"),
    "vector": ("векторизація зображення", "Illustrator/CorelDRAW/Inkscape"),
    "банер": ("банери/графічний дизайн", "Photoshop/Illustrator/Figma"),
    "banner": ("банери/графічний дизайн", "Photoshop/Illustrator/Figma"),
    "дизайн": ("дизайн", "Figma/Photoshop/Illustrator"),
    "design": ("дизайн", "Figma/Photoshop/Illustrator"),
    "презентац": ("презентації", "PowerPoint/Keynote/Canva"),
    "presentation": ("презентації", "PowerPoint/Keynote/Canva"),
    "поліграф": ("поліграфія", "Illustrator/CorelDRAW/InDesign"),
    "polygraph": ("поліграфія", "Illustrator/CorelDRAW/InDesign"),
    "ілюстрац": ("ілюстрації", "Illustrator/Photoshop/Procreate"),
    "illustration": ("ілюстрації", "Illustrator/Photoshop/Procreate"),
    "відеомонтаж": ("відеомонтаж", "Premiere Pro/DaVinci Resolve/After Effects"),
    "video editing": ("відеомонтаж", "Premiere Pro/DaVinci Resolve/After Effects"),
    "копірайт": ("копірайтинг", "копірайтинг/редактура"),
    "copywriting": ("копірайтинг", "копірайтинг/редактура"),
    "переклад": ("переклади", "професійний переклад/локалізація"),
    "translation": ("переклади", "професійний переклад/локалізація"),
    "translator": ("переклади", "професійний переклад/локалізація"),
    "data entry": ("ручне внесення даних", "уважність до даних/операторська робота"),
    "внесення даних": ("ручне внесення даних", "уважність до даних/операторська робота"),
    "smm": ("SMM", "SMM/контент-маркетинг"),
}


def check_ollama_available(timeout: float = 5.0) -> tuple[bool, str]:
    base_url = OLLAMA_URL.rsplit("/api/", 1)[0]
    tags_url = f"{base_url}/api/tags"

    try:
        with httpx.Client(timeout=timeout) as client:
            response = client.get(tags_url)
    except (httpx.RequestError, requests.RequestException, Exception) as error:
        return False, str(error)

    if response.is_success:
        return True, "OK"

    return False, f"HTTP {response.status_code}"


def ask_ollama(
    prompt: str,
    temperature: float = 0.3,
    num_predict: int = 500,
    timeout: float = 120.0,
) -> str:
    payload = {
        "model": OLLAMA_MODEL,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": temperature,
            "num_predict": num_predict,
        },
    }

    with httpx.Client(timeout=timeout) as client:
        response = client.post(OLLAMA_URL, json=payload)
        response.raise_for_status()
        data = response.json()
        return str(data.get("response", "")).strip()


def log_raw_ai_response(task: str, response: str) -> None:
    AI_RAW_LOG_PATH.parent.mkdir(exist_ok=True)

    try:
        if AI_RAW_LOG_PATH.is_file() and AI_RAW_LOG_PATH.stat().st_size > 10 * 1024 * 1024:
            backup_path = AI_RAW_LOG_PATH.with_suffix(".log.1")
            backup_path.unlink(missing_ok=True)
            AI_RAW_LOG_PATH.rename(backup_path)
    except OSError:
        pass

    with AI_RAW_LOG_PATH.open("a", encoding="utf-8") as file:
        file.write(f"\n--- {task} ---\n")
        file.write(response.strip())
        file.write("\n")


def extract_json(text: str) -> dict:
    json_match = re.search(r"\{.*\}", text, re.DOTALL)

    if not json_match:
        raise ValueError(f"AI не повернув JSON. Відповідь AI: {text[:300]}")

    json_text = json_match.group(0)

    try:
        return json.loads(json_text)

    except json.JSONDecodeError as error:
        raise ValueError(f"Некоректний JSON від AI: {error}") from error


def safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)

    except (TypeError, ValueError):
        return default


def normalize_analysis(data: dict) -> dict:
    fit = str(data.get("fit", "no")).lower()
    competition = str(data.get("competition", "unknown")).lower()
    budget_ok = str(data.get("budget_ok", "unknown")).lower()

    if fit not in {"yes", "partial", "no"}:
        fit = "no"

    if competition not in {"low", "medium", "high", "very_high", "unknown"}:
        competition = "unknown"

    if budget_ok not in {"yes", "partial", "no", "unknown"}:
        budget_ok = "unknown"

    questions = data.get("questions", [])

    if not isinstance(questions, list):
        questions = []

    return {
        "fit": fit,
        "summary": str(data.get("summary", "Немає даних")).strip(),
        "difficulty": max(1, min(10, safe_int(data.get("difficulty"), 10))),
        "risk": max(1, min(10, safe_int(data.get("risk"), 10))),
        "success_chance": max(0, min(100, safe_int(data.get("success_chance"), 0))),
        "competition": competition,
        "budget_ok": budget_ok,
        "should_apply": bool(data.get("should_apply", False)),
        "reason": str(data.get("reason", "Немає висновку")).strip(),
        "questions": [str(question).strip() for question in questions[:5] if str(question).strip()],
    }


def analyze_project_json(project_text: str, user_profile: str | None = None) -> dict:
    profile = user_profile or USER_PROFILE
    prompt = f"""
Ти аналізуєш фриланс-завдання для junior Software Engineer.
Відповідай українською.

Профіль виконавця:
{profile}

Проєкт:
{project_text}

Поверни тільки JSON без пояснень.
Оцінюй не занадто суворо: якщо junior з AI може розібратися і виконати задачу,
став fit="partial" або "yes", але чесно піднімай risk/difficulty.
Дивись на теги/категорії так само уважно, як на опис.
Визнач:
- чи задача справді технічна для профілю виконавця;
- який очікуваний результат треба здати клієнту;
- які доступи, API, дані, макети або приклади потрібні;
- що може зірвати оцінку термінів/ціни.
Питання мають бути конкретні до цього проєкту, а не загальні.

Формат:
{{
  "fit": "yes/partial/no",
  "summary": "коротка суть завдання і очікуваний результат",
  "difficulty": число від 1 до 10,
  "risk": число від 1 до 10,
  "success_chance": число від 0 до 100,
  "competition": "low/medium/high/very_high/unknown",
  "budget_ok": "yes/partial/no/unknown",
  "should_apply": true або false,
  "reason": "коротко чому підходить або не підходить",
  "questions": ["конкретне питання 1", "конкретне питання 2", "конкретне питання 3", "конкретне питання 4"]
}}
"""

    raw = ask_ollama(prompt, num_predict=ANALYSIS_NUM_PREDICT)
    log_raw_ai_response("analysis", raw)

    try:
        return extract_json(raw)
    except ValueError:
        repair_prompt = f"""
Перетвори відповідь нижче на валідний JSON рівно у вказаному форматі.
Не додавай markdown, пояснення або текст поза JSON.

Відповідь:
{raw}

Формат:
{{
  "fit": "yes/partial/no",
  "summary": "коротка суть завдання",
  "difficulty": 1,
  "risk": 1,
  "success_chance": 50,
  "competition": "low/medium/high/unknown",
  "budget_ok": "yes/partial/no/unknown",
  "should_apply": true,
  "reason": "коротко чому",
  "questions": ["питання 1", "питання 2", "питання 3"]
}}
"""
        repaired = ask_ollama(repair_prompt, temperature=0.1, num_predict=ANALYSIS_NUM_PREDICT)
        log_raw_ai_response("analysis_repair", repaired)
        return extract_json(repaired)


def format_analysis(data: dict) -> str:
    questions = data.get("questions", [])
    questions_text = "\n".join(f"- {question}" for question in questions)

    if not questions_text:
        questions_text = "- Немає уточнень"

    should_apply = "так" if data.get("should_apply") else "ні"

    return f"""
📌 Суть:
{data.get("summary", "Немає даних")}

✅ Підходить:
{data.get("fit", "unknown")}

📊 Складність:
{data.get("difficulty", "?")}/10

⚠️ Ризик:
{data.get("risk", "?")}/10

🎯 Шанс виконати:
{data.get("success_chance", "?")}%

👥 Конкуренція:
{data.get("competition", "unknown")}

💰 Бюджет:
{data.get("budget_ok", "unknown")}

📝 Подаватися:
{should_apply}

❓ Що уточнити:
{questions_text}

🧾 Висновок:
{data.get("reason", "Немає висновку")}
""".strip()


def calculate_score(data: dict) -> int:
    success = safe_int(data.get("success_chance"), 0)
    difficulty = safe_int(data.get("difficulty"), 10)
    risk = safe_int(data.get("risk"), 10)

    score = success - difficulty * 4 - risk * 3

    fit = data.get("fit")

    if fit == "yes":
        score += 15
    elif fit == "partial":
        score += 5
    elif fit == "no":
        score -= 30

    budget_ok = data.get("budget_ok")

    if budget_ok == "yes":
        score += 10
    elif budget_ok == "partial":
        score += 2
    elif budget_ok == "no":
        score -= 20

    competition = data.get("competition")

    if competition == "low":
        score += 10
    elif competition == "medium":
        score -= 3
    elif competition == "high":
        score -= 15

    if data.get("should_apply"):
        score += 5
    else:
        score -= 5

    return max(0, min(100, score))


def project_text(project: dict) -> str:
    return f"{project.get('title', '')} {project.get('description', '')}".lower()


def contains_keyword(text: str, keyword: str) -> bool:
    if " " in keyword:
        return keyword in text

    return re.search(rf"(?<!\w){re.escape(keyword)}(?!\w)", text) is not None


def has_technical_keyword(text: str) -> bool:
    return any(contains_keyword(text, word) for word in TECHNICAL_KEYWORDS)


def non_technical_reason(project: dict) -> tuple[str, str] | None:
    text = project_text(project)

    if "seo" in text and any(
        phrase in text for phrase in ["без зміни коду", "без коду", "без програмування"]
    ):
        return "SEO без програмування", "SEO/SMM-маркетинг"

    if any(phrase in text for phrase in ["data entry", "внесення даних"]):
        return "ручне внесення даних", "уважність до даних/операторська робота"

    if "seo" in text and not any(
        contains_keyword(text, word)
        for word in ["api", "html", "css", "код", "code", "розробка", "programming"]
    ):
        return "SEO без програмування", "SEO/SMM-маркетинг"

    for keyword, reason in NON_TECHNICAL_KEYWORDS.items():
        if keyword in text and not has_technical_keyword(text):
            return reason

    return None


def is_technical_project(project: dict) -> bool:
    text = project_text(project)
    return non_technical_reason(project) is None and has_technical_keyword(text)


def project_analysis_questions(project: dict) -> list[str]:
    analysis = str(project.get("analysis") or "")
    marker = "❓ Що уточнити:"

    if marker not in analysis:
        return []

    question_block = analysis.split(marker, 1)[1].split("🧾", 1)[0]
    questions = []

    for line in question_block.splitlines():
        cleaned = re.sub(r"^[-*\d.)\s]+", "", line).strip()
        if cleaned and "немає уточнень" not in cleaned.lower():
            questions.append(cleaned)

    return questions[:5]


def project_specific_questions(project: dict, base_questions: list[str], limit: int = 5) -> list[str]:
    text = project_text(project)
    questions = list(project_analysis_questions(project))

    def signal_in_text(keyword: str) -> bool:
        if keyword in {"ai", "api", "llm"}:
            return contains_keyword(text, keyword)

        return keyword in text

    signal_questions = [
        (
            ("авторизац", "login", "auth", "кабінет"),
            "які ролі користувачів, авторизація та права доступу потрібні?",
        ),
        (
            ("адмін", "admin"),
            "які дії має виконувати адмін і які дані потрібно бачити в адмін-частині?",
        ),
        (
            ("dashboard", "дашборд", "панель"),
            "які показники, таблиці або графіки потрібно показувати на дашборді?",
        ),
        (
            ("deploy", "деплой", "сервер", "hosting", "хостинг"),
            "де потрібно розгорнути рішення і чи є доступи до сервера або хостингу?",
        ),
        (
            ("api", "webhook", "вебхук", "інтеграц"),
            "чи є документація API, тестові ключі та приклади потрібних запитів?",
        ),
        (
            ("база", "database", "sqlite", "postgres", "mysql", "mongodb"),
            "які дані потрібно зберігати і чи є готова структура бази даних?",
        ),
        (
            ("openai", "chatgpt", "llm", "ai", "штучний інтелект"),
            "який AI-сервіс або модель потрібно використовувати і які обмеження по якості відповіді?",
        ),
        (
            ("cron", "schedule", "автоматично", "регулярно", "щодня"),
            "як часто має запускатися автоматизація і що робити при помилках?",
        ),
    ]

    for keywords, question in signal_questions:
        if any(signal_in_text(keyword) for keyword in keywords):
            questions.append(question)

    questions.extend(base_questions)

    unique_questions = []
    seen = set()

    for question in questions:
        normalized = question.strip().lower()
        if normalized and normalized not in seen:
            seen.add(normalized)
            unique_questions.append(question.strip())

    return unique_questions[:limit]


def project_type(project: dict) -> str:
    text = f"{project.get('title', '')} {project.get('description', '')}".lower()

    if non_technical_reason(project):
        return "non_technical"

    if any(contains_keyword(text, word) for word in ["telegram", "телеграм", "bot", "бот"]):
        return "telegram_bot"

    if any(word in text for word in ["openai", "chatgpt", "llm", "ai", "штучний інтелект"]):
        return "ai_integration"

    if any(word in text for word in ["fastapi", "django", "flask", "backend"]):
        return "backend"

    if any(word in text for word in ["react", "vue", "next.js", "frontend"]):
        return "frontend"

    if "wordpress" in text or "вордпрес" in text:
        return "wordpress"

    if any(word in text for word in ["парсинг", "parser", "parsing", "scraping", "scrape"]):
        return "parsing"

    if any(word in text for word in ["html", "css", "верстк", "layout", "landing", "лендінг"]):
        return "html_css"

    if "api" in text:
        return "api"

    if any(word in text for word in ["excel", "google sheets", "google sheet", "таблиц"]):
        return "excel"

    if any(word in text for word in TECHNICAL_KEYWORDS):
        return "unknown"

    return "unknown"


def project_tags_text(project: dict) -> str:
    tags = project.get("tags") or project.get("categories") or project.get("skills") or []

    if isinstance(tags, str):
        return tags

    if isinstance(tags, list):
        values = []
        for tag in tags:
            if isinstance(tag, dict):
                values.append(str(tag.get("name") or tag.get("title") or tag.get("id") or "").strip())
            else:
                values.append(str(tag).strip())

        return ", ".join(value for value in values if value)

    return ""


def project_context(project: dict) -> str:
    description = str(project.get("description") or "").strip()
    is_short_description = len(description) < 220

    lines = [
        f"title: {project.get('title') or 'Не вказано'}",
        f"description: {description or 'Опис відсутній'}",
        f"budget: {project.get('budget') or 'Не вказано'}",
        f"bids_count: {project.get('bids_count') or 'Невідомо'}",
        f"tags/categories: {project_tags_text(project) or 'Не вказано'}",
        f"project_url: {project.get('url') or 'Не вказано'}",
        f"score: {project.get('score') if project.get('score') is not None else 'Невідомо'}",
        f"why_fit: {project.get('reason') or 'Не вказано'}",
        f"risks: {project.get('analysis') or 'Не вказано'}",
        f"saved_questions: {'; '.join(project_analysis_questions(project)) or 'Не вказано'}",
        f"is_technical_project: {str(is_technical_project(project)).lower()}",
        f"project_type: {project_type(project)}",
    ]

    if is_short_description:
        lines.append(
            "Опис короткий, тому ставка має бути обережною і з уточнюючими питаннями."
        )

    return "\n".join(lines)


def preliminary_bid_estimate(project: dict) -> str:
    kind = project_type(project)
    budget = str(project.get("budget") or "").strip()

    estimates = {
        "telegram_bot": "Орієнтовно: 3-7 днів, від 4000-12000 грн залежно від сценаріїв, бази даних, адмін-функцій і деплою.",
        "ai_integration": "Орієнтовно: 2-6 днів, від 4000-12000 грн залежно від AI-сервісу, промптів, інтеграції та тестування якості.",
        "backend": "Орієнтовно: 3-8 днів, від 5000-15000 грн залежно від API, бази даних, авторизації та деплою.",
        "frontend": "Орієнтовно: 2-6 днів, від 3000-10000 грн залежно від макета, станів інтерфейсу, адаптиву та інтеграції з API.",
        "wordpress": "Орієнтовно: 1-4 дні, від 1500-6000 грн залежно від кількості правок, доступів і теми.",
        "parsing": "Орієнтовно: 2-5 днів, від 3000-9000 грн залежно від джерела, захисту сайту, полів і формату результату.",
        "html_css": "Орієнтовно: 1-5 днів, від 2000-8000 грн залежно від кількості сторінок, макета, адаптиву і форм.",
        "api": "Орієнтовно: 2-6 днів, від 3000-10000 грн залежно від API, сценаріїв, доступів і обробки помилок.",
        "excel": "Орієнтовно: 1-3 дні, від 1000-5000 грн залежно від структури таблиць, формул і автоматизації.",
        "unknown": "Орієнтовно: 2-5 днів, від 2000-8000 грн після уточнення обсягу, доступів і формату результату.",
    }

    estimate = estimates.get(kind, estimates["unknown"])

    if budget and budget.lower() not in {"не вказано", "none"}:
        return f"{estimate} Якщо бюджет проєкту фіксований ({budget}), можу підлаштувати обсяг під нього."

    return estimate


def fallback_bid(project: dict, variant: str = "short") -> str:
    kind = project_type(project)
    title = str(project.get("title") or "цим завданням").strip()

    if kind == "non_technical":
        return unsuitable_project_text(project)

    if kind == "telegram_bot":
        task = "реалізацією Telegram-бота на Python"
        stack = "python-telegram-bot або aiogram, за потреби SQLite, логування та деплой"
        questions = [
            "які команди або сценарії має виконувати бот?",
            "чи потрібна база даних?",
            "чи потрібні адмін-команди та логування?",
            "де бот має бути розгорнутий?",
        ]

    elif kind == "ai_integration":
        task = "інтеграцією AI-сервісу або автоматизацією на основі LLM"
        stack = "Python, API потрібної AI-моделі, промпти, валідацію відповідей і логування"
        questions = [
            "який AI-сервіс або модель потрібно використовувати?",
            "які вхідні дані й очікуваний формат відповіді?",
            "чи є приклади хороших і поганих відповідей?",
            "чи потрібне збереження історії або логування?",
        ]

    elif kind == "backend":
        task = "невеликою backend-розробкою"
        stack = "Python/FastAPI або Django, базу даних, API-ендпоінти, логування та деплой"
        questions = [
            "які endpoints або сценарії потрібно реалізувати?",
            "чи потрібна авторизація та ролі користувачів?",
            "яка база даних або структура даних очікується?",
            "чи є вимоги до деплою та документації API?",
        ]

    elif kind == "frontend":
        task = "frontend-розробкою або правками інтерфейсу"
        stack = "React/Vue або чистий HTML/CSS/JavaScript залежно від поточного проєкту"
        questions = [
            "чи є Figma або приклад бажаного інтерфейсу?",
            "які стани екранів і адаптив потрібні?",
            "чи є готовий backend/API для інтеграції?",
            "у якому репозиторії або стеку треба вносити правки?",
        ]

    elif kind == "wordpress":
        task = "правками або налаштуванням WordPress-сайту"
        stack = "адмінку WordPress, тему сайту, CSS/HTML-правки та перевірку адаптивності"
        questions = [
            "чи є доступ до адмінки та хостингу?",
            "який точний список правок потрібно внести?",
            "тема готова чи кастомна?",
            "чи є макет або приклад бажаного результату?",
        ]

    elif kind == "parsing":
        task = "парсингом даних і підготовкою результату у потрібному форматі"
        stack = "Python, requests/BeautifulSoup або Playwright, залежно від сайту та захисту"
        questions = [
            "з якого джерела потрібно збирати дані?",
            "які поля потрібно отримати?",
            "у якому форматі потрібен результат?",
            "чи є авторизація, CAPTCHA або інший захист?",
        ]

    elif kind == "html_css":
        task = "HTML/CSS-версткою або правками інтерфейсу"
        stack = "семантичний HTML, CSS/адаптив, за потреби JavaScript для простих взаємодій"
        questions = [
            "чи є Figma або інший макет?",
            "скільки сторінок потрібно зробити?",
            "які брейкпоінти адаптиву потрібні?",
            "чи потрібні форми або інтеграція з CMS?",
        ]

    elif kind == "api":
        task = "інтеграцією API або невеликою backend-задачею"
        stack = "Python, requests/httpx або FastAPI, залежно від потрібного сценарію"
        questions = [
            "чи є документація API?",
            "які саме сценарії потрібно реалізувати?",
            "який формат даних очікується?",
            "чи потрібне логування помилок?",
        ]

    elif kind == "excel":
        task = "автоматизацією Google Sheets або Excel"
        stack = "формули, Apps Script або Python-скрипт, залежно від джерела даних"
        questions = [
            "яка структура вхідних таблиць?",
            "який результат має бути на виході?",
            "дані потрібно оновлювати вручну чи автоматично?",
            "чи є приклад готового звіту?",
        ]

    else:
        task = f"виконанням завдання: {title}"
        stack = "простий технічний підхід після уточнення вимог, доступів і формату результату"
        questions = [
            "який кінцевий результат потрібно отримати?",
            "які матеріали або доступи вже є?",
            "у якому форматі потрібно передати готову роботу?",
        ]

    questions = project_specific_questions(project, questions)

    if variant == "technical":
        intro = f"Добрий день. Можу допомогти з {task}."
        approach = f"Технічно бачу реалізацію через {stack}."
    elif variant == "cautious":
        intro = f"Добрий день. Можу допомогти з {task}, але перед оцінкою варто уточнити обсяг."
        approach = f"Попередній підхід: {stack}. Якщо ТЗ коротке, краще спочатку зафіксувати сценарії та очікуваний результат."
    else:
        intro = f"Добрий день. Можу допомогти з {task}."
        approach = f"Попередньо бачу реалізацію через {stack}."

    questions_text = "\n".join(
        f"{index}. {question}" for index, question in enumerate(questions, 1)
    )
    estimate = preliminary_bid_estimate(project)

    return (
        f"{intro}\n\n"
        f"{approach}\n\n"
        f"{estimate}\n\n"
        "Перед точною оцінкою потрібно уточнити:\n"
        f"{questions_text}\n\n"
        "Після відповідей підтверджу фінальні терміни й вартість."
    )


def fallback_questions(project: dict) -> str:
    kind = project_type(project)
    non_technical = non_technical_reason(project)

    question_sets = {
        "telegram_bot": [
            "які команди або сценарії має виконувати бот?",
            "чи потрібна база даних для користувачів, історії або налаштувань?",
            "чи потрібні адмін-команди або окрема адмін-панель?",
            "який AI/API-сервіс потрібно використовувати, якщо він потрібен?",
            "де бот має бути розгорнутий?",
            "чи потрібне логування помилок або дій користувачів?",
        ],
        "ai_integration": [
            "який AI-сервіс або модель потрібно використовувати?",
            "які вхідні дані і який формат відповіді потрібен?",
            "чи є приклади правильних відповідей або тестові кейси?",
            "чи потрібно зберігати історію запитів і відповідей?",
            "які обмеження по швидкості, вартості або приватності даних?",
        ],
        "backend": [
            "які endpoints або бізнес-сценарії потрібно реалізувати?",
            "чи потрібна авторизація, ролі користувачів або адмін-частина?",
            "які сутності потрібно зберігати в базі даних?",
            "чи є вимоги до деплою, логування та документації API?",
            "чи є приклади запитів/відповідей або готове ТЗ?",
        ],
        "frontend": [
            "чи є Figma або приклад потрібного інтерфейсу?",
            "які екрани, стани і брейкпоінти адаптиву потрібні?",
            "чи є готовий backend/API для інтеграції?",
            "у якому стеку або репозиторії потрібно вносити правки?",
            "чи потрібна підтримка форм, валідації або авторизації?",
        ],
        "wordpress": [
            "чи є доступ до адмінки WordPress і хостингу?",
            "тема вже готова чи використовується кастомна?",
            "який точний список правок потрібно внести?",
            "чи потрібна адаптивність для мобільних пристроїв?",
            "чи є макет або приклади бажаного результату?",
        ],
        "parsing": [
            "з якого джерела потрібно збирати дані?",
            "які саме поля потрібно отримати?",
            "у якому форматі потрібен результат?",
            "як часто має запускатися парсинг?",
            "чи є авторизація, CAPTCHA або інший захист?",
        ],
        "html_css": [
            "чи є Figma або інший макет?",
            "скільки сторінок потрібно зверстати?",
            "які брейкпоінти адаптиву потрібні?",
            "чи потрібні форми?",
            "чи потрібна інтеграція з CMS?",
        ],
        "api": [
            "з яким API потрібно працювати?",
            "які endpoints або сценарії потрібні?",
            "чи є документація та тестові доступи?",
            "який формат даних очікується?",
            "чи потрібне логування помилок?",
        ],
        "excel": [
            "які саме дані потрібно обробляти?",
            "який формат вхідного файлу або таблиці?",
            "який результат має бути на виході?",
            "чи потрібна автоматизація запуску?",
        ],
        "general": [
            "який кінцевий результат потрібно отримати?",
            "які доступи або матеріали вже є?",
            "які обмеження по термінах?",
            "у якому форматі потрібно передати готову роботу?",
        ],
    }

    if kind == "non_technical" and non_technical:
        sphere, _skills = non_technical

        if "переклади" in sphere:
            questions = [
                "який обсяг тексту потрібно перекласти?",
                "з якої мови на яку потрібен переклад?",
                "чи потрібна адаптація стилю або лише дослівний переклад?",
                "у якому форматі потрібно передати результат?",
            ]
        elif "SEO" in sphere:
            questions = [
                "чи потрібна тільки SEO-стратегія, чи також технічні правки на сайті?",
                "чи є список сторінок і ключових запитів?",
                "чи потрібна робота з мета-тегами, контентом або структурою сайту?",
                "чи передбачені зміни в коді або тільки маркетингова оптимізація?",
            ]
        elif any(word in sphere for word in ["логотип", "векторизація", "поліграфія", "ілюстрації"]):
            questions = [
                "який точний формат результату потрібен?",
                "які розміри, матеріали або технічні вимоги до друку?",
                "чи є вихідні файли або приклади бажаного результату?",
                "у яких форматах потрібно передати готові файли?",
            ]
        else:
            questions = [
                "який кінцевий результат потрібно отримати?",
                "які матеріали або приклади вже є?",
                "у якому форматі потрібно передати готову роботу?",
                "які терміни та обмеження важливі?",
            ]
    else:
        questions = question_sets.get(kind, question_sets["general"])

    questions = project_specific_questions(project, questions, limit=6)
    numbered = "\n".join(f"{index}. {question}" for index, question in enumerate(questions, 1))

    return (
        "Перед оцінкою потрібно уточнити:\n\n"
        f"{numbered}\n\n"
        "Після відповідей можна буде точніше визначити стек, терміни й вартість."
    )


def generate_bid(project: dict, user_profile: str | None = None, variant: str = "short") -> str:
    if not is_technical_project(project):
        return unsuitable_project_text(project)
    return fallback_bid(project, variant=variant)


def generate_questions(project: dict) -> str:
    return fallback_questions(project)


def unsuitable_project_text(project: dict) -> str:
    reason = non_technical_reason(project)
    sphere, skills = reason or ("нетехнічна задача", "профільні нетехнічні інструменти")

    return (
        "⚠️ Проєкт, імовірно, не підходить.\n\n"
        "Причина:\n"
        f"- задача стосується {sphere};\n"
        "- немає Python, Telegram-ботів, API, парсингу, HTML/CSS, WordPress, "
        "Google Sheets/Excel або простих інтеграцій;\n"
        f"- для виконання потрібні навички {skills}.\n\n"
        "Рекомендація:\n"
        "Краще пропустити, якщо немає досвіду в цій сфері."
    )
