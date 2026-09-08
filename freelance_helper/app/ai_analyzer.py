import json
import re
from pathlib import Path
from typing import Any
import httpx
import requests

from .config import OLLAMA_MODEL, OLLAMA_URL, PROJECT_ROOT, USER_PROFILE
from .rules import format_budget_display

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


def detect_project_language(title: str, description: str) -> str:
    text = f"{title} {description}"
    cyrillic_count = len(re.findall(r"[а-яіїєґА-ЯІЇЄҐёЁ]", text))
    latin_count = len(re.findall(r"[a-zA-Z]", text))
    if latin_count > 40 and cyrillic_count < 10:
        return "en"
    return "uk"


def determine_tech_stack(kind: str, tech_list: list[str]) -> str:
    tech_lower = {t.lower() for t in tech_list}
    if kind == "telegram_bot":
        framework = "aiogram 3" if "aiogram" in tech_lower else ("pyTelegramBotAPI" if "pytelegrambotapi" in tech_lower or "telebot" in tech_lower else "aiogram 3")
        db = "PostgreSQL" if any(t in tech_lower for t in ["postgresql", "postgres"]) else "SQLite"
        return f"Python ({framework}, {db}, зручне меню та кнопки)"

    if kind == "parsing":
        tool = "Playwright/Selenium" if any(t in tech_lower for t in ["playwright", "selenium"]) else "requests / BeautifulSoup"
        return f"Python ({tool}, експорт в Excel/CSV)"

    if kind in {"backend", "api"}:
        framework = "FastAPI" if "fastapi" in tech_lower else ("Django" if "django" in tech_lower else ("Flask" if "flask" in tech_lower else "FastAPI / Django"))
        db = "PostgreSQL" if any(t in tech_lower for t in ["postgresql", "postgres"]) else ("MySQL" if "mysql" in tech_lower else "PostgreSQL / SQLite")
        return f"Python ({framework}, {db}, перевірка даних)"

    if kind == "ai_integration":
        return "Python, OpenAI API (ChatGPT / GPT-4o), точні інструкції"

    if kind == "frontend":
        framework = "Next.js / React" if "next.js" in tech_lower or "nextjs" in tech_lower else ("React" if "react" in tech_lower else ("Vue" if "vue" in tech_lower else "React"))
        return f"{framework}, адаптивність для смартфонів"

    if kind == "html_css":
        return "HTML5, CSS3, JavaScript (ідеально відкривається на смартфонах)"

    if kind == "wordpress":
        return "WordPress, PHP, налаштування теми, CSS/JS"

    if kind == "excel":
        return "Google Sheets / Excel (автоматичні формули, очищення даних)"

    if tech_list:
        clean_tech = ", ".join(tech_list[:3])
        return f"{clean_tech} (надійний та перевірений код)"

    return "Python та сучасні надійні інструменти"


def determine_tech_stack_en(kind: str, tech_list: list[str]) -> str:
    tech_lower = {t.lower() for t in tech_list}
    if kind == "telegram_bot":
        framework = "aiogram 3" if "aiogram" in tech_lower else ("pyTelegramBotAPI" if "pytelegrambotapi" in tech_lower or "telebot" in tech_lower else "aiogram 3")
        db = "PostgreSQL" if any(t in tech_lower for t in ["postgresql", "postgres"]) else "SQLite"
        return f"Python ({framework}, {db}, clean menu & buttons)"

    if kind == "parsing":
        tool = "Playwright/Selenium" if any(t in tech_lower for t in ["playwright", "selenium"]) else "requests / BeautifulSoup"
        return f"Python ({tool}, export to Excel/CSV)"

    if kind in {"backend", "api"}:
        framework = "FastAPI" if "fastapi" in tech_lower else ("Django" if "django" in tech_lower else ("Flask" if "flask" in tech_lower else "FastAPI / Django"))
        db = "PostgreSQL" if any(t in tech_lower for t in ["postgresql", "postgres"]) else ("MySQL" if "mysql" in tech_lower else "PostgreSQL / SQLite")
        return f"Python ({framework}, {db}, robust validation)"

    if kind == "ai_integration":
        return "Python, OpenAI API (ChatGPT / GPT-4o), prompt engineering"

    if kind == "frontend":
        framework = "Next.js / React" if "next.js" in tech_lower or "nextjs" in tech_lower else ("React" if "react" in tech_lower else ("Vue" if "vue" in tech_lower else "React"))
        return f"{framework}, fully responsive for mobile"

    if kind == "html_css":
        return "HTML5, CSS3, JavaScript (mobile-friendly & clean code)"

    if kind == "wordpress":
        return "WordPress, PHP, theme customizations, CSS/JS"

    if kind == "excel":
        return "Google Sheets / Excel (automated formulas & data cleaning)"

    if tech_list:
        clean_tech = ", ".join(tech_list[:3])
        return f"{clean_tech} (clean, well-tested code)"

    return "Python & modern reliable tools"


def extract_project_insights(project: dict) -> dict:
    title = str(project.get("title") or "").strip()
    desc = str(project.get("description") or "").strip()
    full_text = f"{title} {desc}".lower()
    kind = project_type(project)
    budget = format_budget_display(project.get("budget"))

    # Clean task name from title with proper grammatical context
    task_name = title
    for prefix in [
        "потрібно зробити", "потрібно", "потрібен", "потрібна", "потрібні",
        "шукаю розробника для", "шукаю розробника зі стеком", "шукаю розробника",
        "шукаю", "треба", "разработка", "нужно сделать", "нужен", "нужна",
        "требуется", "допрацювання проєкту", "допрацювання сайту",
        "доработка проекта", "доработка существующего", "доработка",
    ]:
        if task_name.lower().startswith(prefix):
            task_name = task_name[len(prefix):].strip()
            break
    task_name = task_name.rstrip(".!:").strip()
    if task_name:
        c_lower = task_name.lower()
        if c_lower.startswith("telegram-бот") or c_lower.startswith("телеграм-бот"):
            task_name = "розробку Telegram-бота" + task_name[12:]
        elif c_lower.startswith("telegram бот") or c_lower.startswith("телеграм бот"):
            task_name = "розробку Telegram-бота" + task_name[12:]
        elif c_lower.startswith("бот"):
            task_name = "розробку бота" + task_name[3:]
        elif c_lower.startswith("скрипт"):
            task_name = "розробку скрипта" + task_name[6:]
        elif c_lower.startswith("парсер"):
            task_name = "розробку парсера" + task_name[6:]
        elif c_lower.startswith("парсинг"):
            task_name = "парсинг" + task_name[7:]
        elif c_lower.startswith("розробка"):
            task_name = "розробку" + task_name[8:]
        elif c_lower.startswith("створення"):
            task_name = "створення" + task_name[9:]
        elif c_lower.startswith("налаштування"):
            task_name = "налаштування" + task_name[12:]
        elif c_lower.startswith("автоматизація"):
            task_name = "автоматизацію" + task_name[13:]
        elif c_lower.startswith("інтеграція"):
            task_name = "інтеграцію" + task_name[10:]
        elif c_lower.startswith("верстка"):
            task_name = "верстку" + task_name[7:]
        elif c_lower.startswith("лендинг") or c_lower.startswith("лендінг"):
            task_name = "верстку лендингу" + task_name[7:]
        elif c_lower.startswith("ai-") or c_lower.startswith("ai "):
            task_name = "AI-" + task_name[3:] if c_lower.startswith("ai-") else "AI " + task_name[3:]
        elif not re.search(r"[а-яіїєґ]", task_name[:5].lower()):
            task_name = f"проєкт «{task_name}»"
        else:
            task_name = task_name[0].lower() + task_name[1:]
    else:
        task_name = "це завдання"

    # English task name extraction
    lang = detect_project_language(title, desc)
    task_name_en = title
    for prefix in [
        "need a", "need an", "need", "looking for a", "looking for an", "looking for",
        "wanted", "developer needed for", "developer needed", "urgent:", "job:",
    ]:
        if task_name_en.lower().startswith(prefix):
            task_name_en = task_name_en[len(prefix):].strip()
            break
    task_name_en = task_name_en.rstrip(".!:").strip()
    if not task_name_en:
        task_name_en = "your project"

    # Known sources / websites
    sources = []
    domains = re.findall(r"\b[a-z0-9-]+\.(?:com|ua|net|org|io|co|pl|de|site|info)\b", full_text)
    if domains:
        sources.extend(domains[:2])
    for site_kw, site_name in [
        ("rozetka", "Rozetka"), ("prom", "Prom.ua"), ("olx", "OLX"),
        ("instagram", "Instagram"), ("telegram", "Telegram"), ("youtube", "YouTube"),
    ]:
        if site_kw in full_text and site_name not in sources:
            sources.append(site_name)

    # Known formats
    formats = []
    if any(k in full_text for k in ["excel", "ексель", "xlsx", "xls"]):
        formats.append("Excel (.xlsx)")
    if any(k in full_text for k in ["google sheet", "google таблиц", "гугл таблиц", "гугл шит"]):
        formats.append("Google Таблиці")
    if "csv" in full_text:
        formats.append("CSV")
    if "json" in full_text:
        formats.append("JSON")
    if "xml" in full_text:
        formats.append("XML")
    if any(k in full_text for k in ["баз", "database", "sqlite", "postgres", "mysql"]):
        formats.append("База даних")

    # Known tech mentioned
    tech = []
    if any(k in full_text for k in ["aiogram"]):
        tech.append("aiogram")
    if any(k in full_text for k in ["telebot", "pytelegrambotapi"]):
        tech.append("pyTelegramBotAPI")
    if any(k in full_text for k in ["fastapi"]):
        tech.append("FastAPI")
    if any(k in full_text for k in ["django"]):
        tech.append("Django")
    if any(k in full_text for k in ["flask"]):
        tech.append("Flask")
    if any(k in full_text for k in ["playwright"]):
        tech.append("Playwright")
    if any(k in full_text for k in ["selenium"]):
        tech.append("Selenium")
    if any(k in full_text for k in ["beautifulsoup", "bs4"]):
        tech.append("BeautifulSoup")
    if any(k in full_text for k in ["react"]):
        tech.append("React")
    if any(k in full_text for k in ["next.js", "nextjs"]):
        tech.append("Next.js")
    if any(k in full_text for k in ["vue"]):
        tech.append("Vue")
    if any(k in full_text for k in ["wordpress", "вордпрес"]):
        tech.append("WordPress")
    if any(k in full_text for k in ["figma", "фігма"]):
        tech.append("Figma")

    has_auth = any(k in full_text for k in ["авториз", "auth", "login", "парол", "ролі"])
    has_admin = any(k in full_text for k in ["адмін", "admin", "кабінет", "панель"])
    has_db = bool(formats and "База даних" in formats) or any(
        k in full_text for k in ["баз", "database", "sqlite", "postgres", "mysql"]
    )
    has_payment = any(k in full_text for k in ["оплат", "платіж", "payment", "wayforpay", "liqpay", "stripe", "mono"])

    return {
        "title": title,
        "desc": desc,
        "task_name": task_name,
        "task_name_en": task_name_en,
        "lang": lang,
        "kind": kind,
        "budget": budget,
        "has_fixed_budget": budget != "Не вказано",
        "sources": sources,
        "formats": formats,
        "tech": tech,
        "has_auth": has_auth,
        "has_admin": has_admin,
        "has_db": has_db,
        "has_payment": has_payment,
    }


def smart_project_questions(insights: dict) -> list[str]:
    kind = insights["kind"]
    sources = insights["sources"]
    formats = insights["formats"]
    has_payment = insights.get("has_payment", False)
    questions = []

    if kind == "parsing":
        if not sources:
            questions.append("з якого саме сайту потрібно зібрати дані?")
        else:
            questions.append(f"чи є список посилань або розділів для збору з {sources[0]}?")

        if not formats:
            questions.append("у якому форматі зручніше отримати таблицю (Excel чи Google Таблиця)?")
        else:
            questions.append("збір даних потрібен один раз чи плануєте оновлювати регулярно?")

        questions.append("які саме поля обов'язково зібрати (назва, ціна, фото, контакти чи наявність)?")

    elif kind == "telegram_bot":
        questions.append("які основні кнопки та дії має бачити користувач у меню бота?")
        if has_payment:
            questions.append("яку платіжну систему плануєте підключити (WayForPay, LiqPay чи Monobank)?")
        else:
            questions.append("куди вам зручніше отримувати сповіщення про нові заявки (в особисті повідомлення чи групу)?")
        questions.append("чи є вже сервер для роботи бота, чи допомогти з вибором та запуском?")

    elif kind in {"backend", "api"}:
        questions.append("чи є короткий опис, які саме дані має приймати та повертати система?")
        if not insights["has_auth"]:
            questions.append("чи потрібна реєстрація користувачів та поділ на ролі?")
        questions.append("де планується розміщення проєкту (сервер/хостинг)?")

    elif kind in {"frontend", "html_css"}:
        if "Figma" not in insights["tech"]:
            questions.append("чи є готовий зразок або макет сторінки (Figma чи приклад іншого сайту)?")
        else:
            questions.append("чи повністю затверджений макет у Figma?")
        questions.append("куди мають приходити заявки з форми (на пошту чи в Telegram)?")

    elif kind == "excel":
        questions.append("чи є зразок файлу з прикладом початкових даних та бажаного звіту?")
        questions.append("дані мають оновлюватися автоматично чи за кнопкою?")

    elif kind == "wordpress":
        questions.append("чи є доступ до панелі керування сайтом (WordPress або хостингу)?")
        questions.append("який список правок потрібно зробити в першу чергу?")

    elif kind == "ai_integration":
        questions.append("які саме завдання має вирішувати штучний інтелект (відповіді клієнтам, аналіз чи допомога в чаті)?")
        questions.append("чи є вже створений акаунт OpenAI (ChatGPT), чи допомогти налаштувати новий?")

    else:
        questions.append("який кінцевий результат очікується на виході?")
        questions.append("чи є готові початкові матеріали або доступи?")
        questions.append("які орієнтири за термінами виконання?")

    return questions[:3]


def smart_project_questions_en(insights: dict) -> list[str]:
    kind = insights["kind"]
    sources = insights["sources"]
    formats = insights["formats"]
    questions = []

    if kind == "parsing":
        if not sources:
            questions.append("Which exact website or data source do you need scraped?")
        else:
            questions.append(f"Do you have a specific list of links or categories to scrape from {sources[0]}?")
        if not formats:
            questions.append("What output format do you prefer (Excel/CSV or Google Sheets)?")
        else:
            questions.append("Is this a one-time data extraction or should it run periodically?")
        questions.append("Which specific data fields are required (titles, prices, images, contacts, etc.)?")

    elif kind == "telegram_bot":
        questions.append("What key actions and buttons should users see in the bot menu?")
        questions.append("Where would you like to receive notifications about new leads (direct message or group)?")
        questions.append("Do you already have a VPS server for hosting, or would you like me to set it up?")

    elif kind in {"backend", "api"}:
        questions.append("Do you have documentation or a summary of the required endpoints and data formats?")
        if not insights.get("has_auth"):
            questions.append("Does the system require user authentication and role-based access?")
        questions.append("Where will the backend be hosted (your server/cloud platform)?")

    elif kind in {"frontend", "html_css"}:
        if "Figma" not in insights["tech"]:
            questions.append("Do you have a ready design or mockup (Figma, wireframe, or reference website)?")
        else:
            questions.append("Is the Figma design finalized and ready for development?")
        questions.append("Where should contact form submissions be sent (email or Telegram)?")

    elif kind == "excel":
        questions.append("Could you share a sample of the input data and the expected summary report?")
        questions.append("Should the data calculation run automatically or via a button/script?")

    elif kind == "wordpress":
        questions.append("Do you have admin access to WordPress and hosting panel?")
        questions.append("What is the priority list of fixes/changes to start with?")

    elif kind == "ai_integration":
        questions.append("What specific tasks should the AI handle (customer support, data analysis, or chat assistance)?")
        questions.append("Do you have an existing OpenAI API key, or do you need assistance getting one configured?")

    else:
        questions.append("What is the expected final deliverable for this project?")
        questions.append("Do you have initial assets, credentials, or API documentation ready?")
        questions.append("What is your preferred timeline for completion?")

    return questions[:3]


def fallback_bid_en(project: dict, variant: str = "short") -> str:
    kind = project_type(project)
    insights = extract_project_insights(project)
    task_name = insights["task_name_en"]
    budget = insights["budget"]
    has_fixed = insights["has_fixed_budget"]
    questions = smart_project_questions_en(insights)
    stack = determine_tech_stack_en(kind, insights["tech"])

    # Dynamic realistic timeline
    if kind == "telegram_bot":
        time_estimate = "3-5 days" if (insights.get("has_payment") or insights.get("has_admin")) else "1-2 days"
    elif kind in {"backend", "api"}:
        time_estimate = "3-6 days" if (insights.get("has_auth") or insights.get("has_payment")) else "2-4 days"
    elif kind == "parsing":
        time_estimate = "2-4 days" if insights.get("sources") else "1-2 days"
    elif kind in {"frontend", "html_css"}:
        time_estimate = "2-4 days" if insights.get("has_auth") else "1-2 days"
    elif kind == "ai_integration":
        time_estimate = "2-4 days"
    elif kind in {"wordpress", "excel"}:
        time_estimate = "1-2 days"
    else:
        time_estimate = "1-3 days"

    src_mention = f" from {insights['sources'][0]}" if insights["sources"] else " from the target website"
    fmt_mention = f" into {insights['formats'][0]}" if insights["formats"] else " into an organized spreadsheet"

    # Category-specific personalized action hooks
    hooks_en = {
        "telegram_bot": f"Hello! I am ready to develop a reliable and fast Telegram bot for {task_name}.",
        "parsing": f"Hello! I can set up clean and automated data scraping{src_mention} with structured export{fmt_mention}.",
        "backend": f"Hello! I will build a secure and well-architected backend for {task_name}.",
        "api": f"Hello! I can reliably integrate and configure the API for {task_name} with proper error handling.",
        "frontend": f"Hello! I am ready to create a clean, modern, and fully responsive frontend for {task_name}.",
        "html_css": f"Hello! I will build a lightweight, pixel-perfect layout for {task_name} that opens smoothly on all devices.",
        "wordpress": f"Hello! I can safely make the required updates and improvements for {task_name}.",
        "excel": f"Hello! I will automate your data processing and reporting for {task_name}.",
        "ai_integration": f"Hello! I can build a tailored AI integration for {task_name} with optimized prompts.",
    }
    hook_default = f"Hello! I reviewed your project and I am ready to complete {task_name}."
    hook_en = hooks_en.get(kind, hook_default)

    deliverables_map = {
        "telegram_bot": (
            "Develop a responsive Telegram bot: clean menu, interactive buttons, input validation, and secure database storage for leads.",
            "Free 24/7 deployment setup on your server with automatic restarts.",
        ),
        "parsing": (
            f"Set up reliable, structured data scraping{src_mention} and export{fmt_mention} with clean formatting and no duplicates.",
            "Deliver the completed data file and a simple 1-click script with instructions.",
        ),
        "backend": (
            "Build a fast, well-structured backend with clean database models, data validation, and error handling.",
            "Assist with server deployment and thoroughly test every endpoint prior to delivery.",
        ),
        "api": (
            "Integrate the required API service seamlessly with robust error and rate-limit handling.",
            "Ensure dependable performance and provide clear documentation for easy maintenance.",
        ),
        "frontend": (
            "Implement pixel-perfect, responsive UI matching your design flawlessly on mobile, tablet, and desktop.",
            "Test across all modern browsers and connect submission forms.",
        ),
        "html_css": (
            "Clean, semantic HTML5/CSS3 layout optimized for fast loading and all screen sizes.",
            "Verify form functionality and cross-browser responsiveness.",
        ),
        "wordpress": (
            "Apply all requested fixes and theme adjustments safely without breaking existing features.",
            "Perform a full backup before starting work for complete safety.",
        ),
        "excel": (
            "Automate calculations and data processing to eliminate manual spreadsheet routine.",
            "Set up foolproof formulas and provide clear step-by-step guidance.",
        ),
        "ai_integration": (
            "Integrate OpenAI/ChatGPT tailored to your specific workflow with optimized system prompts.",
            "Validate with real prompt testing and assist with deployment.",
        ),
    }

    deliverables, post_support = deliverables_map.get(
        kind,
        (
            "Write clean, maintainable code matching your exact specifications and test thoroughly before delivery.",
            "Remain available after completion for questions or minor adjustments.",
        ),
    )

    if has_fixed:
        budget_line = f"aligned with your budget ({budget})"
    else:
        estimates = {
            "telegram_bot": "$80 - $220 (depending on features and database)",
            "parsing": "$50 - $160 (depending on volume and target anti-bot protection)",
            "backend": "$100 - $300 (depending on scope and API endpoints)",
            "api": "$60 - $180 (depending on integrations required)",
            "frontend": "$60 - $180 (depending on page count and components)",
            "html_css": "$40 - $130 (depending on layout complexity)",
            "wordpress": "$40 - $130 (depending on task list)",
            "excel": "$40 - $110 (depending on logic complexity)",
            "ai_integration": "$90 - $250 (depending on use case and pipeline)",
        }
        budget_line = estimates.get(kind, "$50 - $160 after clarifying details")

    if variant == "technical":
        steps_map = {
            "telegram_bot": [
                "1. Clarify user flows: bot menus, commands, and notification triggers.",
                "2. Implement bot logic, database integration, and admin alerts.",
                "3. Thorough end-to-end testing on mobile and desktop clients.",
                "4. Free server deployment for 24/7 uninterrupted uptime.",
            ],
            "parsing": [
                f"1. Inspect website structure{src_mention} and confirm column requirements.",
                "2. Implement scraper with anti-blocking and pagination safeguards.",
                f"3. Clean and format the collected data{fmt_mention}.",
                "4. Provide the dataset and easy 1-click execution guide.",
            ],
            "backend": [
                "1. Finalize endpoints specification and database schema.",
                "2. Develop core API logic with validation and error handling.",
                "3. Test endpoints under realistic scenarios.",
                "4. Deploy to server and deliver clear instructions.",
            ],
            "api": [
                "1. Confirm required methods, authentication, and data schemas.",
                "2. Implement integration with graceful exception handling.",
                "3. Verify data flow and validate edge cases.",
                "4. Deliver working code with practical usage examples.",
            ],
            "ai_integration": [
                "1. Configure AI model integration and craft specialized system prompts.",
                "2. Implement context management and token usage optimization.",
                "3. Test output accuracy across diverse test cases.",
                "4. Deliver turnkey solution ready for production.",
            ],
            "frontend": [
                "1. Review design files (Figma) and structure components.",
                "2. Build responsive layout with smooth mobile behavior.",
                "3. Wire up interactions and form validations.",
                "4. Verify across all modern browsers before handoff.",
            ],
            "html_css": [
                "1. Review mockups and prepare semantic HTML structure.",
                "2. Style with clean, mobile-first responsive CSS.",
                "3. Configure buttons, animations, and form submissions.",
                "4. Test cross-device compatibility and page load speed.",
            ],
            "wordpress": [
                "1. Create full backup of files and database for security.",
                "2. Carefully implement required adjustments in theme/code.",
                "3. Check responsiveness across desktop and mobile screens.",
                "4. Verify forms, buttons, and site performance.",
            ],
            "excel": [
                "1. Clarify raw data format and expected output report structure.",
                "2. Build automated processing, formulas, and data cleanup.",
                "3. Protect sheet formulas and validate calculations.",
                "4. Provide a quick walkthrough on how to use the sheet.",
            ],
        }

        steps = steps_map.get(
            kind,
            [
                "1. Review technical requirements and confirm deliverables.",
                "2. Step-by-step implementation with ongoing testing.",
                "3. Demo completed work and apply any feedback.",
                "4. Final delivery, setup assistance, and warranty support.",
            ],
        )

        steps_text = "\n".join(steps)
        q_text = "\n".join(f"{i}. {q}" for i, q in enumerate(questions, 1))

        return (
            f"{hook_en}\n\n"
            f"📋 Work plan:\n"
            f"{steps_text}\n\n"
            f"✨ Deliverables:\n"
            f"• {deliverables}\n"
            f"• Fully tested, turnkey result with clear documentation.\n"
            f"• {post_support}\n\n"
            f"💰 Budget: {budget_line}\n"
            f"⏱ Estimated timeline: {time_estimate}\n"
            f"🛡 Warranty: 14 days of free post-delivery technical support.\n\n"
            f"A few quick questions before we begin:\n"
            f"{q_text}\n\n"
            f"Feel free to message me in chat to discuss the details and get started!"
        )

    elif variant == "cautious":
        q_text = "\n".join(f"{i}. {q}" for i, q in enumerate(questions, 1))
        return (
            f"{hook_en} I have practical experience with similar tasks.\n\n"
            f"To tailor everything precisely to your needs, could you please clarify:\n"
            f"{q_text}\n\n"
            f"Project highlights:\n"
            f"• {deliverables}\n"
            f"💰 Budget: {budget_line}\n"
            f"⏱ Timeline: {time_estimate} upon brief alignment\n"
            f"🛡 Warranty: 14 days of free post-delivery support.\n"
            f"🚀 Setup: {post_support}\n\n"
            f"Once confirmed, I can immediately start working. Looking forward to your message!"
        )

    else:  # "short"
        return (
            f"{hook_en}\n\n"
            f"Why choose me for this task:\n"
            f"• {deliverables}\n"
            f"• Tech stack: {stack}.\n"
            f"• Clean, tested, and reliable turnkey delivery.\n\n"
            f"💰 Budget: {budget_line}\n"
            f"⏱ Timeline: {time_estimate}\n"
            f"🛡 Warranty: 14 days of free post-delivery support (always reachable).\n"
            f"🚀 Setup: {post_support}\n\n"
            f"Available in chat to discuss details and start right away!"
        )


def fallback_questions_en(project: dict) -> str:
    insights = extract_project_insights(project)
    questions = smart_project_questions_en(insights)
    numbered = "\n".join(f"{i}. {q}" for i, q in enumerate(questions, 1))

    return (
        f"❓ Key questions to ask the client ({insights['task_name_en']}):\n\n"
        f"{numbered}\n\n"
        "💡 Tip: Ask these questions in chat or include them in your proposal to demonstrate expertise and define clear specifications."
    )


def fallback_bid(project: dict, variant: str = "short") -> str:
    kind = project_type(project)
    if kind == "non_technical":
        return unsuitable_project_text(project)

    insights = extract_project_insights(project)
    if insights.get("lang") == "en":
        return fallback_bid_en(project, variant=variant)

    task_name = insights["task_name"]
    budget = insights["budget"]
    has_fixed = insights["has_fixed_budget"]
    questions = smart_project_questions(insights)
    stack = determine_tech_stack(kind, insights["tech"])

    # Dynamic realistic timeline
    if kind == "telegram_bot":
        time_estimate = "3-5 днів" if (insights.get("has_payment") or insights.get("has_admin")) else "1-2 дні"
    elif kind in {"backend", "api"}:
        time_estimate = "3-6 днів" if (insights.get("has_auth") or insights.get("has_payment")) else "2-4 дні"
    elif kind == "parsing":
        time_estimate = "2-4 дні" if insights.get("sources") else "1-2 дні"
    elif kind in {"frontend", "html_css"}:
        time_estimate = "2-4 дні" if insights.get("has_auth") else "1-2 дні"
    elif kind == "ai_integration":
        time_estimate = "2-4 дні"
    elif kind in {"wordpress", "excel"}:
        time_estimate = "1-2 дні"
    else:
        time_estimate = "1-3 дні"

    src_mention = f" з сайту {insights['sources'][0]}" if insights["sources"] else " із сайту"
    fmt_mention = f" у {insights['formats'][0]}" if insights["formats"] else " у зручну таблицю"

    # Category-specific personalized action hooks
    hook_bot = f"Вітаю! Створю швидкого та надійного Telegram-бота під ваше завдання."
    if "розробку Telegram-бота" in task_name:
        sub_task = task_name.replace("розробку Telegram-бота", "").strip()
        if sub_task:
            hook_bot = f"Вітаю! Створю швидкого та надійного Telegram-бота {sub_task}."
    elif task_name and task_name != "це завдання":
        hook_bot = f"Вітаю! Створю швидкого та надійного Telegram-бота для {task_name}."

    hooks_uk = {
        "telegram_bot": hook_bot,
        "parsing": f"Вітаю! Налаштую стабільний та швидкий збір даних{src_mention} з вивантаженням{fmt_mention}.",
        "backend": f"Вітаю! Розроблю чисту серверну частину під {task_name} з валідацією даних та безпечною базою.",
        "api": f"Вітаю! Надійно підключу та налаштую API для {task_name} з коректною обробкою запитів.",
        "frontend": f"Вітаю! Зроблю якісну, швидку та адаптивну фронтенд-частину для {task_name}.",
        "html_css": f"Вітаю! Зроблю чисту, адаптивну верстку для {task_name}, яка ідеально відкривається на смартфонах і комп'ютерах.",
        "wordpress": f"Вітаю! Акуратно та безпечно внесу всі необхідні правки для {task_name}.",
        "excel": f"Вітаю! Автоматизую розрахунки та звіти для {task_name}, щоб прибрати ручну рутину.",
        "ai_integration": f"Вітаю! Підключу та налаштую штучний інтелект для {task_name} під ваші завдання.",
    }
    hook_default = f"Вітаю! Ознайомився із завданням — готовий якісно виконати {task_name}."
    hook_uk = hooks_uk.get(kind, hook_default)

    deliverables_map = {
        "telegram_bot": (
            "Створю зручного та швидкого бота: зрозуміле меню, кнопки, валідація відповідей та збереження контактів/заявок.",
            "Безкоштовно налаштую автозапуск на сервері, щоб бот працював 24/7 і не вимикався.",
        ),
        "parsing": (
            f"Налаштую акуратний збір усіх потрібних даних{src_mention} та вивантаження{fmt_mention} без дублікатів і пропусків.",
            "Надам готовий файл та простий скрипт з інструкцією для запуску в 1 клік (за потреби налаштую автооновлення).",
        ),
        "backend": (
            "Реалізую швидку та надійну серверну частину з базою даних, перевіркою інформації та захистом від збоїв.",
            "Допоможу з налаштуванням сервера та перевірю роботу кожного запиту перед здачею.",
        ),
        "api": (
            "Надійно підключу необхідний сервіс (API) з правильною обробкою помилок та лімітів.",
            "Забезпечу стабільну роботу та надам просту інструкцію з використання.",
        ),
        "frontend": (
            "Зроблю якісну, швидку верстку компонентів точно за макетом з плавною адаптивністю під телефони та планшети.",
            "Перевірю відображення в усіх браузерах та допоможу підключити форми заявок.",
        ),
        "html_css": (
            "Зроблю акуратну та швидку верстку, яка ідеально відкривається на смартфонах, планшетах і комп'ютерах.",
            "Перевірю швидкість завантаження сторінки та коректність роботи форм.",
        ),
        "wordpress": (
            "Акуратно внесу всі необхідні правки на сайті, не зачіпаючи інший працюючий функціонал.",
            "Перед початком обов'язково зроблю резервну копію (бекап) сайту для повної безпеки.",
        ),
        "excel": (
            "Повністю автоматизую обробку даних та підготовку підсумкового звіту без ручної рутини.",
            "Налаштую формули та надам просту покрокову інструкцію, як користуватися таблицею.",
        ),
        "ai_integration": (
            "Підключу штучний інтелект (OpenAI/ChatGPT) під ваші задачі з точними інструкціями для відповідей.",
            "Перевірю роботу на тестових запитаннях і допоможу запустити рішення в роботу.",
        ),
    }

    deliverables, post_support = deliverables_map.get(
        kind,
        (
            "Напишу чистий, структурований код згідно з вашими вимогами та протестую перед здачею.",
            "Залишаюся на зв'язку після здачі для відповідей на запитання або дрібних правок.",
        ),
    )

    if has_fixed:
        budget_line = f"орієнтуюся на ваш бюджет {budget} (готовий виконати в цих межах)"
    else:
        estimates = {
            "telegram_bot": "від 3 000 - 8 000 грн (залежно від кількості кнопок та бази)",
            "parsing": "від 2 000 - 6 000 грн (залежно від обсягу даних та сайту)",
            "backend": "від 4 000 - 12 000 грн (залежно від функціоналу)",
            "api": "від 2 500 - 7 000 грн (залежно від кількості методів)",
            "frontend": "від 2 500 - 7 000 грн (залежно від кількості екранів)",
            "html_css": "від 1 500 - 5 000 грн (залежно від обсягу верстки)",
            "wordpress": "від 1 500 - 5 000 грн (залежно від списку правок)",
            "excel": "від 1 500 - 4 000 грн (залежно від складності розрахунків)",
            "ai_integration": "від 3 500 - 9 000 грн (залежно від сценарію використання)",
        }
        budget_line = estimates.get(kind, "від 2 000 - 6 000 грн після уточнення деталей")

    if variant == "technical":
        steps_map = {
            "telegram_bot": [
                "1. Узгодження сценаріїв: які кнопки бачить користувач і які повідомлення отримує.",
                "2. Створення меню, зручних кнопок та збереження контактів/заявок у базі даних.",
                "3. Налаштування миттєвих сповіщень для адміністратора та тестування на телефоні.",
                "4. Безкоштовний запуск на сервері для роботи 24/7 та передача вам результату.",
            ],
            "parsing": [
                f"1. Аналіз сайту{src_mention} та погодження списку колонок для збору.",
                "2. Налаштування стабільного збору інформації без блокувань та дублікатів.",
                f"3. Акуратне оформлення та збереження даних{fmt_mention} зі зручними фільтрами.",
                "4. Передача готової таблиці та простої інструкції для запуску скрипта.",
            ],
            "backend": [
                "1. Складання списку функцій та оптимальної структури бази даних.",
                "2. Розробка серверної частини з перевіркою введених даних та захистом від збоїв.",
                "3. Тестування роботи під навантаженням та підключення потрібних сервісів.",
                "4. Розгортання на сервері та надання зрозумілої інструкції.",
            ],
            "api": [
                "1. Узгодження списку необхідних запитів та форматів передачі даних.",
                "2. Підключення сервісу з правильною обробкою можливих мережевих помилок.",
                "3. Налаштування надійного збереження даних та повне тестування.",
                "4. Передача готового рішення з наочними прикладами роботи.",
            ],
            "ai_integration": [
                "1. Підключення штучного інтелекту та оптимізація інструкцій для відповідей.",
                "2. Налаштування збереження історії діалогів та захисту від некоректних відповідей.",
                "3. Оптимізація витрат, щоб запити працювали швидко та економно.",
                "4. Тестування на реальних запитаннях і запуск рішення під ключ.",
            ],
            "frontend": [
                "1. Аналіз макета (Figma) та підготовка структури сторінки.",
                "2. Акуратна верстка компонентів з плавною роботою на мобільних телефонах.",
                "3. Підключення інтерактивних кнопок, форм заявки та перевірка полів.",
                "4. Фінальне тестування в усіх браузерах перед передачею вам.",
            ],
            "html_css": [
                "1. Підготовка сторінки за вашим зразком чи макетом.",
                "2. Акуратна верстка з ідеальною адаптивністю під смартфони та комп'ютери.",
                "3. Налаштування кнопок, анімацій та форми відправки заявок.",
                "4. Перевірка швидкості відкриття сторінки на різних пристроях.",
            ],
            "wordpress": [
                "1. Створення повної резервної копії (бекапу) сайту для безпеки.",
                "2. Акуратне внесення необхідних змін у тему чи налаштування.",
                "3. Перевірка коректності відображення на телефонах та комп'ютерах.",
                "4. Тестування роботи форм заявок та кнопок після внесених правок.",
            ],
            "excel": [
                "1. Узгодження структури початкових даних та бажаного підсумкового звіту.",
                "2. Автоматизація обробки: очищення від помилок, зведення та розрахунки.",
                "3. Налаштування надійних формул та захисту від випадкових змін.",
                "4. Перевірка розрахунків та надання простої інструкції користувача.",
            ],
        }

        steps = steps_map.get(
            kind,
            [
                "1. Узгодження деталей завдання та бажаного фінального результату.",
                "2. Покрокова реалізація та тестування на реальних сценаріях.",
                "3. Демонстрація готового результату та внесення правок за потреби.",
                "4. Передача під ключ, налаштування та підтримка.",
            ],
        )

        steps_text = "\n".join(steps)
        q_text = "\n".join(f"{i}. {q}" for i, q in enumerate(questions, 1))

        return (
            f"{hook_uk}\n\n"
            f"📋 Порядок виконання:\n"
            f"{steps_text}\n\n"
            f"✨ Що ви отримаєте в результаті:\n"
            f"• {deliverables}\n"
            f"• Повністю готове та протестоване рішення з простою інструкцією.\n"
            f"• {post_support}\n\n"
            f"💰 Бюджет: {budget_line}\n"
            f"⏱ Орієнтовний термін: {time_estimate}\n"
            f"🛡 Гарантія: 14 днів безкоштовної техпідтримки після здачі проєкту.\n\n"
            f"Перед стартом підкажіть лише:\n"
            f"{q_text}\n\n"
            f"Напишіть у чат — обговоримо деталі та одразу розпочну роботу!"
        )

    elif variant == "cautious":
        q_text = "\n".join(f"{i}. {q}" for i, q in enumerate(questions, 1))
        return (
            f"{hook_uk} Маю практичний досвід у таких завданнях.\n\n"
            f"Щоб погодити всі деталі та зробити все точно під ваші вимоги, підкажіть, будь ласка:\n"
            f"{q_text}\n\n"
            f"Орієнтири за проєктом:\n"
            f"• {deliverables}\n"
            f"💰 Бюджет: {budget_line}\n"
            f"⏱ Термін: {time_estimate} після короткого узгодження\n"
            f"🛡 Гарантія: 14 днів безкоштовного супроводу після передачі проєкту.\n"
            f"🚀 Налаштування: {post_support}\n\n"
            f"Після ваших відповідей готовий одразу зафіксувати фінальні деталі та розпочати роботу. На зв'язку!"
        )

    else:  # "short"
        return (
            f"{hook_uk}\n\n"
            f"Чому варто довірити задачу мені:\n"
            f"• {deliverables}\n"
            f"• Стек: {stack}.\n"
            f"• Чистий та надійний результат під ключ, усе перевірю перед здачею.\n\n"
            f"💰 Бюджет: {budget_line}\n"
            f"⏱ Термін: {time_estimate}\n"
            f"🛡 Гарантія: 14 днів безкоштовної техпідтримки після здачі (я завжди на зв'язку).\n"
            f"🚀 Налаштування: {post_support}\n\n"
            f"Готовий відповісти на запитання в чаті та швидко розпочати роботу!"
        )


def fallback_questions(project: dict) -> str:
    kind = project_type(project)
    non_technical = non_technical_reason(project)

    if kind == "non_technical" and non_technical:
        return unsuitable_project_text(project)

    insights = extract_project_insights(project)
    if insights.get("lang") == "en":
        return fallback_questions_en(project)

    questions = smart_project_questions(insights)
    numbered = "\n".join(f"{i}. {q}" for i, q in enumerate(questions, 1))

    return (
        f"❓ Що варто уточнити у замовника ({insights['task_name']}):\n\n"
        f"{numbered}\n\n"
        "💡 Порада: задайте ці питання у чаті або додайте до своєї ставки, щоб показати експертність і зафіксувати точне ТЗ."
    )


def generate_chat_pitch(project: dict) -> str:
    """Generates an ultra-concise, professional pitch (2-3 sentences) for quick messaging in chat."""
    kind = project_type(project)
    insights = extract_project_insights(project)
    task_name = insights["task_name"]
    task_en = insights["task_name_en"]
    lang = insights.get("lang", "uk")

    if lang == "en":
        pitches_en = {
            "telegram_bot": f"Hello! I specialize in Telegram bot development and automation. Ready to implement {task_en} with clean code and free 24/7 server deployment. Let's discuss details in chat!",
            "parsing": f"Hello! I have solid experience with web scraping and data processing. Can collect and format the required data accurately into Excel/Sheets without duplicates. Ready to start right away!",
            "backend": f"Hello! I specialize in Python backend development (FastAPI/Django) and databases. Ready to build a clean, secure backend for {task_en}. Reach out in chat to discuss!",
            "api": f"Hello! I can reliably integrate the required API for {task_en} with comprehensive error handling and testing. Let me know when convenient to connect!",
            "frontend": f"Hello! I can create a pixel-perfect, responsive interface for {task_en} that works smoothly on mobile and desktop. Ready to review the design and start!",
            "html_css": f"Hello! I can quickly build clean, mobile-friendly HTML/CSS layout for {task_en}. Ready to start as soon as mockups are provided!",
            "wordpress": f"Hello! I can safely and promptly apply the required WordPress fixes for {task_en} with a backup made prior to work. Ready to begin!",
            "excel": f"Hello! I can fully automate calculations and reports in Excel/Google Sheets for {task_en} to eliminate manual routine. Let's discuss details!",
            "ai_integration": f"Hello! I can integrate OpenAI/ChatGPT into {task_en} with customized prompt instructions and reliable API handling. Happy to discuss!",
        }
        return pitches_en.get(kind, f"Hello! I reviewed your project and have experience with similar tasks. Ready to take on {task_en} professionally. Let's discuss details in chat!")

    bot_target = f"під ваше завдання"
    if "розробку Telegram-бота" in task_name:
        sub = task_name.replace("розробку Telegram-бота", "").strip()
        bot_target = sub if sub else "під ключ"
    elif task_name and task_name != "це завдання":
        bot_target = f"для {task_name}"

    pitches_uk = {
        "telegram_bot": f"Вітаю! Спеціалізуюся на розробці Telegram-ботів. Готовий надійно створити бота {bot_target} з автозапуском на сервері 24/7. Напишіть у чат — обговоримо деталі та одразу розпочну!",
        "parsing": f"Вітаю! Маю великий практичний досвід у зборі даних. Налаштую швидкий парсинг з вивантаженням в Excel без пропусків і дублікатів. Готовий розпочати роботу сьогодні!",
        "backend": f"Вітаю! Розробляю надійну серверну частину на Python з базою даних та валідацією. Готовий взятися за {task_name}. Напишіть у чат — узгодимо деталі!",
        "api": f"Вітаю! Професійно підключу та налаштую API для {task_name} з правильною обробкою помилок. Готовий відповісти на запитання в чаті та почати!",
        "frontend": f"Вітаю! Зроблю швидку, якісну верстку для {task_name} з ідеальною адаптивністю під смартфони. Готовий ознайомитися з макетом та взятися за роботу!",
        "html_css": f"Вітаю! Зроблю чисту та адаптивну HTML/CSS-верстку для {task_name}. Сторінка відкриватиметься швидко на всіх пристроях. Готовий стартувати!",
        "wordpress": f"Вітаю! Акуратно та безпечно внесу всі необхідні правки у WordPress під {task_name} (з обов'язковим бекапом перед стартом). На зв'язку в чаті!",
        "excel": f"Вітаю! Повністю автоматизую розрахунки та звітність у Excel/Google Таблицях для {task_name}, щоб прибрати рутину. Обговоримо деталі?",
        "ai_integration": f"Вітаю! Підключу штучний інтелект (OpenAI/ChatGPT) під ваше завдання з точними інструкціями для відповідей. Напишіть у чат — розпочнемо!",
    }
    return pitches_uk.get(kind, f"Вітаю! Ознайомився із завданням, маю практичний досвід у таких проєктах. Готовий якісно виконати {task_name}. Напишіть у чат для обговорення деталей!")


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
