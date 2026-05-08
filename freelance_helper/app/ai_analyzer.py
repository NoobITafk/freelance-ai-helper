import json
import re
import ollama

from app.config import OLLAMA_MODEL


def ask_ollama(prompt: str) -> str:
    response = ollama.chat(
        model=OLLAMA_MODEL,
        messages=[{"role": "user", "content": prompt}],
        options={
            "temperature": 0.5,
            "num_predict": 500,
        },
    )

    return response["message"]["content"].strip()


def extract_json(text: str) -> dict:
    match = re.search(r"\{.*\}", text, re.DOTALL)

    if not match:
        raise ValueError("AI не повернув JSON")

    return json.loads(match.group(0))


def analyze_project_json(project_text: str) -> dict:
    prompt = f"""
Ти аналізуєш фриланс-завдання для junior розробника.

Навички:
- Python
- C#
- HTML/CSS
- SQL
- Telegram bots
- парсинг
- Excel automation
- проста автоматизація
- базовий backend

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

    questions_text = "\n".join(f"- {q}" for q in questions)

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

❓ Що уточнити:
{questions_text}

🧾 Висновок:
{data.get("reason", "Немає висновку")}
""".strip()


def calculate_score(data: dict) -> int:
    success = int(data.get("success_chance", 0))
    difficulty = int(data.get("difficulty", 10))
    risk = int(data.get("risk", 10))

    score = success - difficulty * 4 - risk * 3

    if data.get("fit") == "yes":
        score += 15
    elif data.get("fit") == "partial":
        score += 5
    elif data.get("fit") == "no":
        score -= 30

    if data.get("budget_ok") == "yes":
        score += 10
    elif data.get("budget_ok") == "no":
        score -= 20

    if data.get("competition") == "high":
        score -= 15
    elif data.get("competition") == "low":
        score += 10

    return max(0, min(100, score))


def generate_bid(project: dict) -> str:
    prompt = f"""
Напиши коротку ставку клієнту на Freelancehunt.

Назва: {project.get("title")}
Бюджет: {project.get("budget")}
Опис:
{project.get("description")}

Стиль:
- українською або мовою завдання
- 4-7 речень
- без брехні про великий досвід
- впевнено
- як junior, який реально може виконати задачу
- додай 1-2 уточнювальні питання
"""

    return ask_ollama(prompt)


def generate_questions(project: dict) -> str:
    prompt = f"""
Склади 3-5 коротких питань клієнту.

Назва: {project.get("title")}
Опис:
{project.get("description")}

Відповідай списком українською.
"""

    return ask_ollama(prompt)