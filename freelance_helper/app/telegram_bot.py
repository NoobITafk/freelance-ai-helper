from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes, CallbackQueryHandler

from app.config import TELEGRAM_BOT_TOKEN
from app.ai_analyzer import (
    analyze_project_json,
    format_analysis,
    calculate_score,
    generate_bid,
    generate_questions,
)
from app.freelancehunt_api import get_projects
from app.database import (
    init_db,
    is_seen,
    save_project,
    get_project,
    set_project_rating,
    get_stats,
    get_setting,
    set_setting,
    get_good_bad_keywords,
)
from app.rules import basic_filter, learning_bonus


def get_project_url(project: dict, attributes: dict) -> str:
    links = project.get("links", {})
    return (
        attributes.get("url")
        or attributes.get("link")
        or links.get("self", {}).get("web")
        or links.get("self", {}).get("href")
        or "Посилання не знайдено"
    )


def project_keyboard(project_id: str):
    keyboard = [
        [
            InlineKeyboardButton("✅ Добрий", callback_data=f"good:{project_id}"),
            InlineKeyboardButton("❌ Поганий", callback_data=f"bad:{project_id}"),
        ],
        [
            InlineKeyboardButton("💬 Ставка", callback_data=f"bid:{project_id}"),
            InlineKeyboardButton("❓ Уточнення", callback_data=f"questions:{project_id}"),
        ],
        [
            InlineKeyboardButton("🔁 Нова ставка", callback_data=f"rebid:{project_id}"),
            InlineKeyboardButton("⏭ Пропустити", callback_data=f"skip:{project_id}"),
        ],
    ]
    return InlineKeyboardMarkup(keyboard)


async def send_project(chat_send_func, project):
    project_id = str(project.get("id"))
    attributes = project.get("attributes", {})

    title = attributes.get("name", "Без назви")
    description = attributes.get("description", "")
    budget = attributes.get("budget", "Не вказано")
    bids_count = (
        attributes.get("bid_count")
        or attributes.get("bids_count")
        or attributes.get("bids")
        or "Невідомо"
    )
    url = get_project_url(project, attributes)

    if not project_id or is_seen(project_id):
        return False

    if not basic_filter(title, description):
        return False

    project_text = f"""
Назва: {title}
Бюджет: {budget}
Кількість ставок: {bids_count}
Посилання: {url}

Опис:
{description}
"""

    analysis_data = analyze_project_json(project_text)
    score = calculate_score(analysis_data)

    bonus = learning_bonus(
        title,
        description,
        get_good_bad_keywords()
    )

    final_score = score + bonus
    min_score = int(get_setting("min_score", "45"))

    if final_score < min_score:
        return False

    analysis = format_analysis(analysis_data)

    save_project(
        project_id=project_id,
        title=title,
        description=description,
        budget=budget,
        bids_count=bids_count,
        url=url,
        analysis=analysis,
    )

    message = f"""
🆕 Новий проєкт

📌 {title}
💰 Бюджет: {budget}
👥 Ставок: {bids_count}
🎯 Score: {final_score}/100
🔗 {url}

{analysis}
"""

    await chat_send_func(
        message[:4000],
        reply_markup=project_keyboard(project_id)
    )

    return True


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

    try:
        projects = get_projects()
    except Exception as error:
        await update.message.reply_text(f"Помилка Freelancehunt API:\n{error}")
        return

    sent_count = 0

    for project in projects:
        try:
            was_sent = await send_project(update.message.reply_text, project)
        except Exception as error:
            await update.message.reply_text(f"Помилка обробки проєкту:\n{error}")
            continue

        if was_sent:
            sent_count += 1

        if sent_count >= 3:
            break

    if sent_count == 0:
        await update.message.reply_text("Нових відповідних проєктів поки немає.")


async def auto_check(context: ContextTypes.DEFAULT_TYPE):
    print("Auto check started")
    chat_id = context.job.chat_id

    try:
        projects = get_projects()
    except Exception as error:
        await context.bot.send_message(chat_id=chat_id, text=f"Помилка API:\n{error}")
        return

    sent_count = 0

    async def send_func(text, reply_markup=None):
        await context.bot.send_message(
            chat_id=chat_id,
            text=text,
            reply_markup=reply_markup
        )

    for project in projects:
        try:
            was_sent = await send_project(send_func, project)
        except Exception:
            continue

        if was_sent:
            sent_count += 1

        if sent_count >= 3:
            break


async def auto_on(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    current_jobs = context.job_queue.get_jobs_by_name(str(chat_id))

    if current_jobs:
        await update.message.reply_text("Автоперевірка вже увімкнена ✅")
        return

    context.job_queue.run_repeating(
        auto_check,
        interval=300,
        first=5,
        chat_id=chat_id,
        name=str(chat_id),
    )

    await update.message.reply_text("Автоперевірку увімкнено ✅\nІнтервал: 5 хвилин.")


async def auto_off(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    current_jobs = context.job_queue.get_jobs_by_name(str(chat_id))

    for job in current_jobs:
        job.schedule_removal()

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
        await query.message.reply_text("✅ Збережено: добрий проєкт.")

    elif action == "bad":
        set_project_rating(project_id, "bad")
        await query.message.reply_text("❌ Збережено: поганий проєкт.")

    elif action == "skip":
        set_project_rating(project_id, "skip")
        await query.message.reply_text("⏭ Проєкт пропущено.")

    elif action in ["bid", "rebid"]:
        await query.message.reply_text("Генерую ставку...")

        try:
            bid = generate_bid(project)
        except Exception as error:
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
            await query.message.reply_text(f"Помилка генерації питань:\n{error}")
            return

        await query.message.reply_text(
            f"❓ Що уточнити:\n\n{questions}\n\n🔗 {project.get('url')}"
        )


def run_bot():
    if not TELEGRAM_BOT_TOKEN:
        raise ValueError("TELEGRAM_BOT_TOKEN не знайдено в .env")

    init_db()

    from app.config import TELEGRAM_CHAT_ID

    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    if TELEGRAM_CHAT_ID:
        app.job_queue.run_repeating(
            auto_check,
            interval=180,
            first=10,
            chat_id=int(TELEGRAM_CHAT_ID),
            name="auto_search",
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("test_ai", test_ai))
    app.add_handler(CommandHandler("check", check_projects))
    app.add_handler(CommandHandler("auto_on", auto_on))
    app.add_handler(CommandHandler("auto_off", auto_off))
    app.add_handler(CommandHandler("stats", stats_command))
    app.add_handler(CommandHandler("settings", settings_command))
    app.add_handler(CallbackQueryHandler(handle_button))

    app.run_polling()