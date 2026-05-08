from pydoc import text
from turtle import update
from turtle import update
import asyncio
from concurrent.futures import ThreadPoolExecutor

from telegram import Update
from telegram.ext import ContextTypes
from app.ai_analyzer import (
    analyze_project_json,
    format_analysis,
    calculate_score,
    generate_bid,
    generate_questions,
)
from app.freelancehunt_api import get_projects
from app.database import (
    get_project,
    set_project_rating,
    get_stats,
    get_setting,
    set_setting,
)
from app.services.project_service import process_and_send_project
from app.logger import logger
executor = ThreadPoolExecutor(max_workers=2)
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    await update.message.reply_text(f"Бот працює ✅\nТвій chat_id: {chat_id}")


async def test_ai(update: Update, context: ContextTypes.DEFAULT_TYPE):
    test_project = """
Потрібен Python-скрипт для парсингу товарів із сайту.
Результат зберегти в Excel.
Бюджет: 1000 грн.
Термін: 1 день.
"""

    analysis_data = analyze_project_json(test_project)
    score = calculate_score(analysis_data)
    analysis = format_analysis(analysis_data)

    await update.message.reply_text(f"Score: {score}/100\n\n{analysis}")


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
        if processed_count >= 5:
            break

        try:
            was_sent = await process_and_send_project(
                update.message.reply_text,
                project
            )

            processed_count += 1

        except Exception as error:
            logger.exception("Project processing error")
            await update.message.reply_text(
                f"Помилка обробки проєкту:\n{error}"
            )
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
    processed_count
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

    sent_count = 0
    processed_count = 0

    for project in projects:
        if processed_count >= 5:
            break

        try:
            was_sent = await process_and_send_project(
                send_func,
                project
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
    processed_count
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

    text = f"""
📊 Статистика

Усього проєктів у базі: {stats["total"]}

✅ Добрі: {stats["good"]}
❌ Погані: {stats["bad"]}
⏭ Пропущені: {stats["skip"]}
⚪ Без оцінки: {stats["unrated"]}

🎯 Мінімальний score: {min_score}
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

    if action == "good":
        set_project_rating(project_id, "good")
        logger.info("Project rated good: %s", project_id)
        await query.message.reply_text("✅ Збережено: добрий проєкт.")

    elif action == "bad":
        set_project_rating(project_id, "bad")
        logger.info("Project rated bad: %s", project_id)
        await query.message.reply_text("❌ Збережено: поганий проєкт.")

    elif action == "skip":
        set_project_rating(project_id, "skip")
        logger.info("Project skipped: %s", project_id)
        await query.message.reply_text("⏭ Проєкт пропущено.")

    elif action in ["bid", "rebid"]:
        await query.message.reply_text("Генерую ставку...")

        try:
            bid = generate_bid(project)
        except Exception as error:
            logger.exception("Bid generation error")
            await query.message.reply_text(f"Помилка генерації ставки:\n{error}")
            return

        await query.message.reply_text(
            f"💬 Готовий текст ставки:\n\n{bid}\n\n🔗 {project.get('url')}"
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
"""

    await update.message.reply_text(text)