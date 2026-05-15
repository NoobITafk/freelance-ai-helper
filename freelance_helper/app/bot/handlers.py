import time

from telegram import Update
from telegram.ext import ContextTypes

from ..ai_analyzer import (
    analyze_project_json,
    format_analysis,
    calculate_score,
    generate_bid,
    generate_questions,
    normalize_analysis,
)
from ..config import AI_ANALYSIS_ENABLED, OLLAMA_MODEL, OLLAMA_URL, USER_PROFILE
from ..freelancehunt_api import get_projects
from ..database import (
    get_project,
    get_recent_projects,
    set_project_rating,
    get_stats,
    get_setting,
    set_setting,
)
from ..services.project_service import process_and_send_project
from ..logger import logger


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    await update.message.reply_text(f"Бот працює ✅\nТвій chat_id: {chat_id}")


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = """
🤖 Команди бота

/start — запуск бота
/help — список команд
/check — перевірити проєкти зараз
/auto_on — увімкнути автопошук
/auto_off — вимкнути автопошук
/stats — статистика
/settings — показати мінімальний score
/settings 35 — змінити мінімальний score
/threshold 35 — те саме, коротше
/profile — показати профіль виконавця
/profile_set текст — змінити профіль
/ai_on — увімкнути AI-аналіз
/ai_off — вимкнути AI-аналіз
/recent — останні знайдені проєкти
/why project_id — показати збережений аналіз

📌 Кнопки:
🔥 Дуже підходить — найкращий тип задач
✅ Добрий — хороший проєкт
🤔 Можливо — потенційно цікавий проєкт
🚫 Не моє — не твій напрям
❌ Поганий — поганий проєкт
💬 Ставка — генерація відповіді
❓ Уточнення — питання клієнту
🔁 Нова ставка — перегенерувати відповідь
⏭ Пропустити — пропустити проєкт
"""
    await update.message.reply_text(text)


async def test_ai(update: Update, context: ContextTypes.DEFAULT_TYPE):
    test_project = """
Потрібен Python-скрипт для парсингу товарів із сайту.
Результат зберегти в Excel.
Бюджет: 1000 грн.
Термін: 1 день.
"""

    await update.message.reply_text(
        f"Тестую AI...\nМодель: {OLLAMA_MODEL}\nURL: {OLLAMA_URL}"
    )

    try:
        started_at = time.monotonic()
        user_profile = get_setting("user_profile", USER_PROFILE)
        analysis_data = normalize_analysis(analyze_project_json(test_project, user_profile))
        score = calculate_score(analysis_data)
        analysis = format_analysis(analysis_data)
        elapsed = time.monotonic() - started_at
    except Exception as error:
        logger.exception("AI test failed")
        await update.message.reply_text(f"AI-тест не пройшов:\n{error}")
        return

    await update.message.reply_text(f"Score: {score}/100\nЧас: {elapsed:.1f} сек\n\n{analysis}")


async def check_projects(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Шукаю нові проєкти...")
    logger.info("Manual check started")

    try:
        projects = get_projects()
        logger.info("Fetched projects: %s", len(projects))
    except Exception as error:
        logger.exception("Freelancehunt API error")
        await update.message.reply_text(f"Помилка Freelancehunt API:\n{error}")
        return

    sent_count = 0
    processed_count = 0

    for project in projects:
        if processed_count >= 20:
            break

        try:
            was_sent = await process_and_send_project(
                update.message.reply_text,
                project,
            )
            processed_count += 1

        except Exception as error:
            logger.exception("Project processing error")
            await update.message.reply_text(f"Помилка обробки проєкту:\n{error}")
            continue

        if was_sent:
            sent_count += 1

        if sent_count >= 3:
            break

    if sent_count == 0:
        await update.message.reply_text("Нових відповідних проєктів поки немає.")

    logger.info(
        "Manual check finished | sent=%s | processed=%s",
        sent_count,
        processed_count,
    )


async def auto_check(context: ContextTypes.DEFAULT_TYPE):
    chat_id = context.job.chat_id
    logger.info("Auto check started")

    try:
        projects = get_projects()
        logger.info("Fetched projects: %s", len(projects))
    except Exception as error:
        logger.exception("Auto API error")
        await context.bot.send_message(chat_id=chat_id, text=f"Помилка API:\n{error}")
        return

    async def send_func(text, reply_markup=None):
        await context.bot.send_message(
            chat_id=chat_id,
            text=text,
            reply_markup=reply_markup,
        )

    sent_count = 0
    processed_count = 0

    for project in projects:
        if processed_count >= 20:
            break

        try:
            was_sent = await process_and_send_project(
                send_func,
                project,
            )
            processed_count += 1

        except Exception:
            logger.exception("Auto project processing error")
            continue

        if was_sent:
            sent_count += 1

        if sent_count >= 3:
            break

    logger.info(
        "Auto check finished | sent=%s | processed=%s",
        sent_count,
        processed_count,
    )


async def auto_on(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    current_jobs = context.job_queue.get_jobs_by_name(str(chat_id))

    if current_jobs:
        await update.message.reply_text("Автоперевірка вже увімкнена ✅")
        return

    context.job_queue.run_repeating(
        auto_check,
        interval=180,
        first=5,
        chat_id=chat_id,
        name=str(chat_id),
    )

    logger.info("Auto check enabled for chat_id=%s", chat_id)
    await update.message.reply_text("Автоперевірку увімкнено ✅\nІнтервал: 3 хвилини.")


async def auto_off(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    current_jobs = context.job_queue.get_jobs_by_name(str(chat_id))

    for job in current_jobs:
        job.schedule_removal()

    logger.info("Auto check disabled for chat_id=%s", chat_id)
    await update.message.reply_text("Автоперевірку вимкнено ⏹")


async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    stats = get_stats()
    min_score = get_setting("min_score", "45")
    ai_enabled = get_setting("ai_enabled", str(AI_ANALYSIS_ENABLED)).lower()

    text = f"""
📊 Статистика

Усього проєктів у базі: {stats["total"]}

🔥 Дуже підходять: {stats["great"]}
✅ Добрі: {stats["good"]}
🤔 Можливо: {stats["maybe"]}
❌ Погані: {stats["bad"]}
🚫 Не моє: {stats["not_mine"]}
⏭ Пропущені: {stats["skip"]}
⚪ Без оцінки: {stats["unrated"]}

🎯 Мінімальний score: {min_score}
🤖 AI-аналіз: {ai_enabled}
"""

    await update.message.reply_text(text)


async def settings_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        min_score = get_setting("min_score", "45")
        await update.message.reply_text(
            f"Поточний мінімальний score: {min_score}\n\n"
            f"Щоб змінити:\n/settings 35"
        )
        return

    value = context.args[0]

    if not value.isdigit():
        await update.message.reply_text("Score має бути числом. Наприклад: /settings 35")
        return

    score = int(value)

    if score < 0 or score > 100:
        await update.message.reply_text("Score має бути від 0 до 100.")
        return

    set_setting("min_score", str(score))
    logger.info("Min score changed to %s", score)

    await update.message.reply_text(f"✅ Мінімальний score змінено на {score}")


async def threshold_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await settings_command(update, context)


async def profile_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    profile = get_setting("user_profile", USER_PROFILE)
    await update.message.reply_text(f"👤 Поточний профіль:\n\n{profile}")


async def profile_set_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    profile = " ".join(context.args).strip()

    if len(profile) < 20:
        await update.message.reply_text(
            "Профіль занадто короткий. Напиши хоча б 20 символів після /profile_set."
        )
        return

    set_setting("user_profile", profile)
    logger.info("User profile changed")
    await update.message.reply_text("✅ Профіль оновлено.")


async def ai_on(update: Update, context: ContextTypes.DEFAULT_TYPE):
    set_setting("ai_enabled", "true")
    await update.message.reply_text("✅ AI-аналіз увімкнено.")


async def ai_off(update: Update, context: ContextTypes.DEFAULT_TYPE):
    set_setting("ai_enabled", "false")
    await update.message.reply_text("⏹ AI-аналіз вимкнено. Бот працюватиме через fallback.")


async def recent_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    projects = get_recent_projects(limit=5)

    if not projects:
        await update.message.reply_text("Поки немає збережених проєктів.")
        return

    lines = ["🕘 Останні проєкти:"]

    for project in projects:
        rating = project.get("user_rating") or "без оцінки"
        lines.append(
            f"\nID: {project['project_id']}\n"
            f"{project['title']}\n"
            f"Оцінка: {rating}\n"
            f"{project.get('url') or ''}"
        )

    await update.message.reply_text("\n".join(lines)[:4000])


async def why_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Вкажи ID проєкту. Наприклад: /why 123456")
        return

    project_id = context.args[0]
    project = get_project(project_id)

    if not project:
        await update.message.reply_text("Проєкт не знайдено в базі.")
        return

    text = f"""
📌 {project.get("title")}

{project.get("analysis") or "Аналіз не збережено."}

🔗 {project.get("url") or ""}
""".strip()

    await update.message.reply_text(text[:4000])


async def handle_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query

    if not query or not query.data:
        return

    try:
        await query.answer()
    except Exception:
        pass

    action, project_id = query.data.split(":", 1)
    project = get_project(project_id)

    if not project:
        await query.message.reply_text("Проєкт не знайдено в базі.")
        return

    if action in {"great", "good", "maybe", "bad", "not_mine", "skip"}:
        set_project_rating(project_id, action)
        logger.info("Project rated %s: %s", action, project_id)

        labels = {
            "great": "🔥 Збережено: дуже підходить.",
            "good": "✅ Збережено: добрий проєкт.",
            "maybe": "🤔 Збережено: можливо.",
            "bad": "❌ Збережено: поганий проєкт.",
            "not_mine": "🚫 Збережено: не твоє.",
            "skip": "⏭ Проєкт пропущено.",
        }
        await query.message.reply_text(labels[action])

    elif action in ["bid", "rebid"]:
        await query.message.reply_text("Генерую ставку...")

        try:
            user_profile = get_setting("user_profile", USER_PROFILE)
            short_bid = generate_bid(project, user_profile=user_profile, variant="short")
            confident_bid = generate_bid(project, user_profile=user_profile, variant="confident")
        except Exception as error:
            logger.exception("Bid generation error")
            await query.message.reply_text(f"Помилка генерації ставки:\n{error}")
            return

        await query.message.reply_text(
            f"💬 Коротка ставка:\n\n{short_bid}\n\n"
            f"💪 Впевненіша ставка:\n\n{confident_bid}\n\n"
            f"🔗 {project.get('url')}"
        )

    elif action == "questions":
        await query.message.reply_text("Генерую питання клієнту...")

        try:
            questions = generate_questions(project)
        except Exception as error:
            logger.exception("Questions generation error")
            await query.message.reply_text(f"Помилка генерації питань:\n{error}")
            return

        await query.message.reply_text(
            f"❓ Що уточнити:\n\n{questions}\n\n🔗 {project.get('url')}"
        )
