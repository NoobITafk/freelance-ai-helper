import json
import re
from pathlib import Path
from typing import Any
import requests

from .config import OLLAMA_MODEL, OLLAMA_URL, USER_PROFILE

ANALYSIS_NUM_PREDICT = 350
TEXT_NUM_PREDICT = 500
AI_RAW_LOG_PATH = Path("logs/ai_raw.log")
BID_VARIANTS = ("short", "technical", "cautious")


def check_ollama_available(timeout: float = 5) -> tuple[bool, str]:
    base_url = OLLAMA_URL.rsplit("/api/", 1)[0]
    tags_url = f"{base_url}/api/tags"

    try:
        response = requests.get(tags_url, timeout=timeout)
    except requests.RequestException as error:
        return False, str(error)

    if response.ok:
        return True, "OK"

    return False, f"HTTP {response.status_code}"


def ask_ollama(
    prompt: str,
    temperature: float = 0.3,
    num_predict: int = 500,
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

    response = requests.post(OLLAMA_URL, json=payload, timeout=120)
    response.raise_for_status()

    data = response.json()
    return str(data.get("response", "")).strip()


def log_raw_ai_response(task: str, response: str) -> None:
    AI_RAW_LOG_PATH.parent.mkdir(exist_ok=True)

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

    if competition not in {"low", "medium", "high", "unknown"}:
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

Формат:
{{
  "fit": "yes/partial/no",
  "summary": "коротка суть завдання",
  "difficulty": число від 1 до 10,
  "risk": число від 1 до 10,
  "success_chance": число від 0 до 100,
  "competition": "low/medium/high/unknown",
  "budget_ok": "yes/partial/no/unknown",
  "should_apply": true або false,
  "reason": "коротко чому",
  "questions": ["питання 1", "питання 2", "питання 3"]
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


def project_type(project: dict) -> str:
    text = f"{project.get('title', '')} {project.get('description', '')}".lower()

    if any(word in text for word in ["telegram", "телеграм", "bot", "бот"]):
        return "telegram_bot"

    if "wordpress" in text or "вордпрес" in text:
        return "wordpress"

    if any(word in text for word in ["парсинг", "parser", "parsing", "scraping", "scrape"]):
        return "parsing"

    return "general"


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
    ]

    if is_short_description:
        lines.append(
            "Опис короткий, тому ставка має бути обережною і з уточнюючими питаннями."
        )

    return "\n".join(lines)


def fallback_bid(project: dict, variant: str = "short") -> str:
    kind = project_type(project)

    if kind == "telegram_bot":
        return (
            "Добрий день. Можу допомогти з реалізацією Telegram-бота на Python. "
            "Перед точною оцінкою потрібно уточнити основні сценарії роботи бота, "
            "чи потрібна база даних, який AI/API-сервіс планується використовувати "
            "та де бот має бути розгорнутий. Після цього можна буде визначити "
            "оптимальний стек, терміни й вартість."
        )

    if kind == "wordpress":
        return (
            "Добрий день. Можу допомогти з правками або налаштуванням WordPress-сайту. "
            "Перед оцінкою потрібно побачити список правок, доступи до адмінки або "
            "хостингу, тему сайту та вимоги до адаптивності. Після уточнення обсягу "
            "можна буде точніше визначити терміни й вартість."
        )

    if kind == "parsing":
        return (
            "Добрий день. Можу допомогти з парсингом даних і підготовкою результату "
            "у зручному форматі. Перед оцінкою потрібно уточнити джерело даних, поля "
            "для збору, формат результату, частоту запуску та чи є авторизація або "
            "захист. Після цього можна буде підібрати підхід, терміни й вартість."
        )

    return (
        "Добрий день. Можу допомогти з виконанням цього технічного завдання. "
        "Попередньо потрібно уточнити очікуваний результат, доступи, формат готової "
        "роботи та обмеження по термінах. Після відповідей можна буде точніше "
        "визначити стек, терміни й вартість."
    )


def fallback_questions(project: dict) -> str:
    kind = project_type(project)

    question_sets = {
        "telegram_bot": [
            "які команди або сценарії має виконувати бот?",
            "чи потрібна база даних для користувачів, історії або налаштувань?",
            "чи потрібні адмін-команди або окрема адмін-панель?",
            "який AI/API-сервіс потрібно використовувати, якщо він потрібен?",
            "де бот має бути розгорнутий?",
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
        "general": [
            "який кінцевий результат потрібно отримати?",
            "які доступи або матеріали вже є?",
            "які обмеження по термінах?",
            "у якому форматі потрібно передати готову роботу?",
        ],
    }
    questions = question_sets[kind]
    numbered = "\n".join(f"{index}. {question}" for index, question in enumerate(questions, 1))

    return (
        "Перед оцінкою потрібно уточнити:\n\n"
        f"{numbered}\n\n"
        "Після відповідей можна буде точніше визначити стек, терміни й вартість."
    )


def generate_bid(project: dict, user_profile: str | None = None, variant: str = "short") -> str:
    variant_instruction = {
        "short": "Коротка ставка: найважливіше, без зайвих деталей.",
        "technical": "Більш технічна ставка: коротко поясни стек або етапи реалізації.",
        "cautious": "Обережна ставка: менше обіцянок, більше уточнюючих питань.",
    }.get(variant, "Коротка ставка: найважливіше, без зайвих деталей.")

    prompt = f"""
Напиши ставку клієнту на Freelancehunt.

Контекст проєкту:
{project_context(project)}

Варіант:
{variant_instruction}

Вимоги до ставки:
- відповідай мовою проєкту, не змішуй мови;
- 800-1200 символів максимум;
- тон впевнений, нейтральний, без перебільшень;
- не згадуй, що виконавець студент, навчається, новачок;
- не згадуй AI/vibe coding як спосіб виконання;
- не вигадуй досвід, клієнтів або факти;
- не пиши "маю 5 років досвіду", "гарантую результат", "робив десятки таких проєктів";
- використовуй формулювання на кшталт "Можу допомогти", "Попередньо бачу реалізацію через...", "Перед точною оцінкою потрібно уточнити...";
- якщо опис короткий, дай більше питань і менше обіцянок.

Структура:
1. Привітання.
2. Що саме можна зробити по цьому проєкту.
3. Попередній стек або підхід.
4. 2-5 уточнюючих питань, якщо ТЗ нечітке.
5. Фраза, що точні терміни/вартість можна сказати після уточнення.

Поверни тільки текст ставки без заголовків і markdown.
"""

    try:
        return ask_ollama(
            prompt=prompt,
            temperature=0.55 if variant != "cautious" else 0.45,
            num_predict=TEXT_NUM_PREDICT,
        )
    except requests.RequestException:
        return fallback_bid(project, variant=variant)


def generate_questions(project: dict) -> str:
    prompt = f"""
Склади уточнюючі питання клієнту. Не пиши ставку.

Контекст проєкту:
{project_context(project)}

Формат відповіді:
Перед оцінкою потрібно уточнити:

1. ...
2. ...
3. ...
4. ...

Після відповідей можна буде точніше визначити стек, терміни й вартість.

Вимоги:
- відповідай мовою проєкту, не змішуй мови;
- питання мають залежати від типу проєкту;
- для Telegram-бота уточни сценарії/команди, базу даних, адмін-функції, AI/API-сервіс, деплой;
- для WordPress уточни доступи, тему, список правок, адаптивність, макет;
- для парсингу уточни джерело, поля, формат результату, частоту запуску, авторизацію/захист;
- не додавай пропозицію виконання робіт, тільки питання у вказаному форматі.
"""

    try:
        return ask_ollama(
            prompt=prompt,
            temperature=0.35,
            num_predict=350,
        )
    except requests.RequestException:
        return fallback_questions(project)
