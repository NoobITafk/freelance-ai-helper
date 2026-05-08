import json
import re
from typing import Any

import ollama

from app.config import OLLAMA_MODEL


ANALYSIS_NUM_PREDICT = 350
TEXT_NUM_PREDICT = 500


def ask_ollama(
    prompt: str,
    temperature: float = 0.3,
    num_predict: int = 500,
) -> str:
    response = ollama.chat(
        model=OLLAMA_MODEL,
        messages=[
            {"role": "user", "content": prompt}
        ],
        options={
            "temperature": temperature,
            "num_predict": num_predict,
        },
    )

    return response["message"]["content"].strip()


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


def analyze_project_json(project_text: str) -> dict:
    prompt = f"""
Ти аналізуєш фриланс-завдання для junior Software Engineer.

Навички:
- Python (FastAPI, створення API)
- Бази даних (PostgreSQL, SQL)
- Інфраструктура (Docker, Linux/Arch)
- Telegram bots (python-telegram-bot)
- Парсинг даних
- Базовий Frontend (HTML, Tailwind CSS)

Проєкт:
{project_text}

Поверни тільки JSON без пояснень.

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

    raw = ask_ollama(prompt)
    return extract_json(raw)


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


def generate_bid(project: dict) -> str:
    prompt = f"""
Напиши коротку ставку клієнту на Freelancehunt.

Дані проєкту:
Назва: {project.get("title")}
Бюджет: {project.get("budget")}
Кількість ставок: {project.get("bids_count")}
Опис:
{project.get("description")}

Стиль:
- мовою завдання;
- 4-7 речень;
- без брехні про великий досвід;
- впевнено, але без перебільшень;
- як junior developer, який може виконати задачу;
- не згадуй, що текст написаний AI;
- додай 1-2 уточнювальні питання.

Поверни тільки готовий текст ставки.
"""

    return ask_ollama(
        prompt=prompt,
        temperature=0.5,
        num_predict=TEXT_NUM_PREDICT,
    )


def generate_questions(project: dict) -> str:
    prompt = f"""
Склади 3-5 коротких питань клієнту.

Дані проєкту:
Назва: {project.get("title")}
Бюджет: {project.get("budget")}
Опис:
{project.get("description")}

Питання мають уточнити:
- обсяг роботи;
- формат результату;
- терміни;
- технічні ризики.

Поверни тільки список питань українською.
"""

    return ask_ollama(
        prompt=prompt,
        temperature=0.4,
        num_predict=300,
    )