import asyncio
import html
import re
import time
from datetime import datetime
from urllib.parse import quote

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    LabeledPrice,
    PreCheckoutQuery,
    Update,
    WebAppInfo,
)
from telegram.error import BadRequest, Forbidden, TelegramError
from telegram.ext import ContextTypes

from ..ai_analyzer import (
    BID_VARIANTS,
    analyze_project_json,
    check_ollama_available,
    format_analysis,
    calculate_score,
    extract_project_insights,
    fallback_bid,
    fallback_questions,
    generate_bid,
    generate_chat_pitch,
    generate_questions,
    is_technical_project,
    normalize_analysis,
    project_type,
    unsuitable_project_text,
)
from ..rules import format_budget_display, parse_budget_info
from .keyboards import (
    MINI_APP_URL,
    bid_keyboard,
    confirm_publish_keyboard,
    project_keyboard,
    questions_keyboard,
    unsuitable_project_keyboard,
)
from ..config import (
    AI_ANALYSIS_ENABLED,
    AI_TIMEOUT_SECONDS,
    AUTO_CHECK_FIRST_RUN_SECONDS,
    AUTO_CHECK_INTERVAL_SECONDS,
    FREELANCEHUNT_TOKEN,
    MIN_SCORE,
    OLLAMA_MODEL,
    OLLAMA_URL,
    PAYMENT_PROVIDER_TOKEN,
    SUBSCRIPTION_MONTH_PRICE,
    SUBSCRIPTION_REQUIRED,
    SUBSCRIPTION_STARS_PRICE,
    TELEGRAM_BOT_TOKEN,
    TELEGRAM_CHAT_ID,
    TRIAL_DAYS,
    USER_PROFILE,
)
from ..freelancehunt_api import FreelancehuntAPIError, get_projects, submit_project_bid
from ..database import (
    activate_user_subscription,
    add_bonus_days,
    add_feedback,
    add_portfolio_case,
    check_database,
    cleanup_old_projects,
    create_database_backup,
    delete_portfolio_case,
    export_crm_data_csv,
    get_active_subscribers,
    get_all_subscriptions,
    get_crm_stats,
    get_market_digest_stats,
    get_night_projects,
    get_portfolio_cases,
    get_portfolio_links,
    get_project,
    get_recent_projects,
    get_referral_stats,
    get_setting,
    get_stats,
    get_user_subscription,
    grant_user_subscription,
    init_user_subscription,
    is_project_broadcast,
    is_quiet_hours_now,
    is_user_subscribed,
    process_referral,
    record_channel_broadcast,
    set_portfolio_link,
    set_project_rating,
    set_setting,
    update_project_pipeline,
)
from .keyboards import (
    bid_keyboard,
    confirm_publish_keyboard,
    crm_pipeline_keyboard,
    project_keyboard,
    questions_keyboard,
    unsuitable_project_keyboard,
)
from ..services.project_service import format_project_message, process_and_send_project
from ..logger import logger

LAST_PROJECTS_LIMIT = 10


async def reply_text(update: Update, text: str, **kwargs) -> bool:
    message = update.effective_message

    if not message:
        logger.warning("Cannot reply: update has no effective_message")
        return False

    await message.reply_text(text, **kwargs)
    return True


def is_auto_search_on(context: ContextTypes.DEFAULT_TYPE, chat_id: int) -> bool:
    job_queue = context.job_queue

    if not job_queue:
        return False

    return bool(
        job_queue.get_jobs_by_name("auto_search") or job_queue.get_jobs_by_name(str(chat_id))
    )


def set_last_check_stats(
    received_count: int,
    sent_count: int,
    error: str = "",
) -> None:
    set_setting("last_check_at", datetime.now().isoformat(timespec="seconds"))
    set_setting("last_projects_received", str(received_count))
    set_setting("last_projects_sent", str(sent_count))
    set_setting("last_check_error", error)


def make_check_debug_stats() -> dict:
    return {
        "basic_rejected": 0,
        "already_seen": 0,
        "ai_analyzed": 0,
        "fallback_used": 0,
        "sent": 0,
        "low_score_skipped": 0,
        "competition_skipped": 0,
        "api_errors": [],
        "ai_errors": [],
        "api_ok": True,
        "ai_ok": True,
    }


def format_check_debug_stats(
    stats: dict,
    received_count: int,
    processed_count: int,
) -> str:
    filter_rejected = stats["basic_rejected"]

    lines = [
        "🔍 Перевірка завершена",
        "",
        f"Отримано з Freelancehunt: {received_count}",
        f"Оброблено: {processed_count}",
        f"Вже були в базі: {stats['already_seen']}",
        f"Відкинуто фільтрами: {filter_rejected}",
        f"Передано в AI: {stats['ai_analyzed']}",
        f"Fallback без AI: {stats['fallback_used']}",
        f"Відкинуто через score: {stats['low_score_skipped']}",
        f"Відкинуто через конкуренцію: {stats['competition_skipped']}",
        f"Надіслано: {stats['sent']}",
        "",
        f"API: {'OK' if stats['api_ok'] and not stats['api_errors'] else 'ERROR'}",
    ]

    if stats["api_errors"]:
        lines.append(f"Остання помилка API: {stats['api_errors'][-1][:200]}")

    if stats["ai_ok"] and stats["fallback_used"] == 0 and stats["ai_analyzed"] > 0:
        lines.append("AI: OK")
    elif stats["fallback_used"] > 0:
        lines.append("AI: unavailable, used fallback rules")
    elif not stats["ai_ok"]:
        lines.append("AI: ERROR")
    else:
        lines.append("AI: OK")

    if stats["ai_errors"]:
        lines.append(f"Остання помилка AI: {stats['ai_errors'][-1][:200]}")

    return "\n".join(lines)


def env_status(value) -> str:
    return "OK" if value else "missing"


def project_short_description(project: dict, limit: int = 200) -> str:
    description = project.get("description") or ""
    description = " ".join(description.split())

    if len(description) <= limit:
        return description or "Опис відсутній"

    return f"{description[:limit].rstrip()}..."


async def check_user_access(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    user = update.effective_user
    user_id = user.id if user else (update.effective_chat.id if update.effective_chat else None)
    if not user_id:
        return True

    if is_user_subscribed(user_id):
        return True

    sub = get_user_subscription(user_id)
    price = get_setting("sub_price", str(SUBSCRIPTION_MONTH_PRICE))
    status_msg = (
        "Ваш 7-денний безкоштовний пробний період закінчився."
        if sub and sub.get("status") == "expired"
        else "Для користування ботом потрібна активна підписка."
    )

    msg = (
        f"⛔️ {status_msg}\n\n"
        f"💎 Вартість підписки: {price} грн / 30 днів.\n"
        f"У підписку входить: щохвилинний моніторинг Freelancehunt, AI-генератор відгуків, CRM та сповіщення.\n\n"
        f"👉 Щоб отримати підписку, натисніть: /subscribe"
    )
    await reply_text(update, msg)
    return False


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_chat:
        logger.warning("Cannot start: update has no effective_chat")
        return

    chat_id = update.effective_chat.id
    user = update.effective_user
    user_id = user.id if user else chat_id
    username = user.username if user else ""
    full_name = user.full_name if user else ""

    sub = init_user_subscription(
        user_id=user_id,
        chat_id=chat_id,
        username=username,
        full_name=full_name,
        trial_days=TRIAL_DAYS,
    )

    # Process referral code if new user was referred
    if context.args and context.args[0].startswith("ref_"):
        referrer_id = context.args[0][4:].strip()
        if referrer_id and referrer_id != str(user_id):
            rewarded = process_referral(referrer_id, user_id, bonus_days=7)
            if rewarded:
                try:
                    await context.bot.send_message(
                        chat_id=int(referrer_id),
                        text=(
                            f"🎉 <b>Новий реферал!</b>\n"
                            f"За вашим запрошенням до бота приєднався новий користувач ({full_name or username or user_id}).\n"
                            f"🎁 Вам нараховано <b>+7 днів безкоштовної підписки</b>!"
                        ),
                        parse_mode="HTML",
                    )
                except Exception as e:
                    logger.debug("Could not notify referrer %s: %s", referrer_id, e)

    # Check if user came from a channel post for a specific project (e.g. /start bid_12345)
    if context.args and context.args[0].startswith("bid_"):
        pid = context.args[0][4:].strip()
        proj = get_project(pid)
        if proj:
            p_title = proj.get("name") or proj.get("title") or "Замовлення"
            p_budget = proj.get("budget") or "Договірний"
            p_desc = proj.get("description") or ""
            p_url = proj.get("url") or ""

            card_text = (
                f"🎯 <b>Замовлення #{pid}</b>\n\n"
                f"📌 <b>{html.escape(p_title)}</b>\n"
                f"💰 <b>Бюджет:</b> {html.escape(str(p_budget))}\n\n"
                f"📝 {html.escape(p_desc[:250])}...\n\n"
                f"Оберіть дію нижче для миттєвої генерації відгуку:"
            )
            kb = [
                [
                    InlineKeyboardButton("📝 Згенерувати ставку", callback_data=f"bid_preview:{pid}"),
                    InlineKeyboardButton("❓ Питання замовнику", callback_data=f"questions:{pid}"),
                ],
                [
                    InlineKeyboardButton("🔗 На біржу", url=p_url) if p_url else InlineKeyboardButton("💼 В CRM", callback_data=f"crm_save:{pid}"),
                    InlineKeyboardButton("💼 Подав ставку", callback_data=f"pipeline:applied:{pid}"),
                ],
            ]
            await reply_text(update, card_text, reply_markup=InlineKeyboardMarkup(kb), parse_mode="HTML")
            return

    if sub.get("status") == "lifetime":
        sub_info = "⭐️ Статус: Безстроковий доступ (Адміністратор)"
    elif sub.get("status") == "trial":
        sub_info = f"🎁 Вам надано 7 днів безкоштовного пробного доступу (до {sub['expires_at'][:10]}, ще {sub['days_left']} дн.)."
    elif sub.get("status") == "active":
        sub_info = f"✅ Ваша підписка активна (до {sub['expires_at'][:10]}, ще {sub['days_left']} дн.)."
    else:
        sub_info = "⛔️ Безкоштовний період закінчився. Оформити підписку: /subscribe"

    await reply_text(
        update,
        f"Бот працює ✅\n"
        f"{sub_info}\n\n"
        f"💡 Натисніть /help для переліку команд, /ref для отримання реферального посилання (+7 днів за друга) або /webapp для відкриття Mini App.",
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = """
🤖 Команди бота

/start — запуск бота
/help — список команд
/ref — реферальне посилання (+7 днів за кожного запрошеного друга)
/check — перевірити проєкти зараз
/subscribe — оформити або подовжити підписку
/subscription — перевірити статус підписки
/auto_on — увімкнути автопошук
/auto_off — вимкнути автопошук
/stats — статистика
/health — діагностика бота, API, бази та налаштувань
/last — те саме, що /recent
/recent — останні проєкти з бази
/settings — показати мінімальний score
/settings 35 — змінити мінімальний score
/threshold 35 — те саме, коротше
/profile — показати профіль виконавця
/profile_set текст — змінити профіль
/portfolio — посилання на портфоліо
/portfolio_set кат посилання — задати посилання (bot, parsing, backend, web, mobile, devops, excel, general)
/cases — список реальних кейсів для ставок
/case_add кат назва | url | опис — додати кейс у базу
/case_del ID — видалити кейс із бази
/income (або /crm) — воронка заявок, конверсія та заробіток
/quiet — налаштування тихих нічних годин
/digest — ранковий дайджест проєктів за ніч
/backup — надіслати бекап бази даних у чат
/webapp — Telegram Mini App інтерфейс
/test_ai — тест роботи аналізатора
/why project_id — показати збережений аналіз
/hot — топ свіжих замовлень (працює і в групах)
/subscribers — статистика підписників (адмін)
/grant_sub ID днів — нарахувати підписку (адмін)
/set_price сума — змінити ціну підписки (адмін)
/set_channel @канал [score] — підключити публічний канал для автопостингу (адмін)
/channel_off — вимкнути автопостинг у канал (адмін)

📌 Кнопки під проєктом:
✅ Добрий | ❌ Поганий
📝 Ставка | 💬 Відгук у чат
❓ Уточнення | 💼 Я подав ставку
🔁 Нова ставка | ⏭ Пропустити
"""
    await reply_text(update, text)


async def ref_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id if user else (update.effective_chat.id if update.effective_chat else None)
    if not user_id:
        return

    bot_username = context.bot.username if context.bot and context.bot.username else "HUNTua_bot"
    ref_link = f"https://t.me/{bot_username}?start=ref_{user_id}"
    stats = get_referral_stats(user_id)
    invited = stats.get("invited_count", 0)
    bonus_days = stats.get("bonus_days_earned", 0)

    share_text = "Привіт! Спробуй AI-бота для Freelancehunt — моніторить проекти та пише влучні ставки. Перші 7 днів безкоштовно!"
    share_url = f"https://t.me/share/url?url={ref_link}&text={quote(share_text)}"

    text = (
        f"🎁 <b>Партнерська програма (Реферали)</b>\n\n"
        f"Запрошуйте знайомих фрілансерів і отримуйте <b>+7 днів безкоштовної підписки</b> за кожного нового користувача!\n\n"
        f"🔗 <b>Ваше персональне посилання:</b>\n"
        f"<code>{ref_link}</code>\n\n"
        f"📊 <b>Ваша статистика:</b>\n"
        f"• Запрошено колег: <b>{invited}</b>\n"
        f"• Отримано бонусних днів: <b>+{bonus_days} дн.</b>\n\n"
        f"💡 Скопіюйте це посилання або натисніть кнопку нижче, щоб надіслати в чат або другові."
    )
    keyboard = [
        [InlineKeyboardButton("📢 Поділитися посиланням", url=share_url)],
        [InlineKeyboardButton("💎 Оформити підписку", callback_data="sub_open")],
    ]
    await reply_text(update, text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")


async def broadcast_project_to_channel(bot, channel_id: str, project: dict):
    attributes = project.get("attributes", {})
    pid = str(project.get("id", ""))
    title = attributes.get("name", "Нове замовлення")
    budget_raw = attributes.get("budget")
    budget = format_budget_display(budget_raw)
    url = attributes.get("url") or f"https://freelancehunt.com/project/{pid}.html"

    from ..services.project_service import extract_project_tags
    tags = extract_project_tags(attributes)
    stack_text = f"🛠 <b>Стек:</b> {html.escape(tags)}\n" if tags else ""

    desc = attributes.get("description", "")
    short_desc = " ".join(desc.split())
    if len(short_desc) > 220:
        short_desc = short_desc[:220].rstrip() + "..."

    bot_username = bot.username or "HUNTua_bot"
    deep_link = f"https://t.me/{bot_username}?start=bid_{pid}"

    text = (
        f"🔥 <b>Нове замовлення на Freelancehunt!</b>\n\n"
        f"📌 <b>{html.escape(title)}</b>\n"
        f"💰 <b>Бюджет:</b> {html.escape(budget)}\n"
        f"{stack_text}"
        f"📝 <i>{html.escape(short_desc)}</i>\n\n"
        f"⚡️ <i>Згенеруйте виграшний відгук за 2 секунди за допомогою AI:</i>"
    )

    keyboard = [
        [
            InlineKeyboardButton("🤖 Отримати AI-ставку", url=deep_link),
            InlineKeyboardButton("🔗 На біржу", url=url),
        ]
    ]

    await bot.send_message(
        chat_id=channel_id,
        text=text,
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(keyboard),
        disable_web_page_preview=True,
    )


async def set_channel_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not user or str(user.id) != str(TELEGRAM_CHAT_ID):
        await reply_text(update, "Ця команда доступна лише адміністратору.")
        return

    args = context.args
    if not args:
        curr = get_setting("public_channel", "")
        min_s = get_setting("channel_min_score", "50")
        if curr:
            await reply_text(
                update,
                f"📢 Поточний канал трансляції: <b>{curr}</b>\n"
                f"Мінімальний Score для каналу: <b>{min_s}</b>\n\n"
                f"Змінити: <code>/set_channel @channel_username [min_score]</code>\n"
                f"Вимкнути: <code>/channel_off</code>",
                parse_mode="HTML",
            )
        else:
            await reply_text(
                update,
                f"📢 Трансляція в публічний канал наразі <b>вимкнена</b>.\n\n"
                f"Щоб підключити канал:\n"
                f"1. Створіть публічний канал у Telegram та додайте туди бота @HUNTua_bot як адміністратора з правом публікації.\n"
                f"2. Надішліть: <code>/set_channel @username_каналу</code>",
                parse_mode="HTML",
            )
        return

    chan = args[0].strip()
    if not chan.startswith("@") and not chan.startswith("-100"):
        chan = "@" + chan

    min_s = int(args[1]) if len(args) > 1 and args[1].isdigit() else 50
    set_setting("public_channel", chan)
    set_setting("channel_min_score", str(min_s))

    try:
        await context.bot.send_message(
            chat_id=chan,
            text="🚀 <b>Freelance AI Helper підключено!</b>\nСюди автоматично публікуватимуться гарячі замовлення з Freelancehunt.",
            parse_mode="HTML",
        )
        ping_res = "Тестове повідомлення успішно надіслано в канал ✅"
    except Exception as e:
        ping_res = f"⚠️ Повідомлення не надіслано: {e}.\nПереконайтеся, що бота додано в адміністратори каналу з правом публікації!"

    await reply_text(
        update,
        f"✅ Канал трансляції встановлено: <b>{chan}</b> (Score від {min_s})\n\n{ping_res}",
        parse_mode="HTML",
    )


async def channel_off_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not user or str(user.id) != str(TELEGRAM_CHAT_ID):
        await reply_text(update, "Ця команда доступна лише адміністратору.")
        return

    set_setting("public_channel", "")
    await reply_text(update, "⏹ Трансляцію в публічний канал вимкнено.")


_group_hot_cooldown: dict[int, float] = {}


async def hot_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    is_group = update.effective_chat and update.effective_chat.type in ("group", "supergroup")
    bot_username = context.bot.username or "HUNTua_bot"

    if is_group:
        chat_id = update.effective_chat.id
        now = time.time()
        last_call = _group_hot_cooldown.get(chat_id, 0.0)
        if now - last_call < 600.0:  # 10 minutes cooldown per group
            wait_sec = int(600.0 - (now - last_call))
            wait_min = max(1, (wait_sec + 59) // 60)
            await reply_text(
                update,
                f"⏱ <b>Команда /hot у групах доступна раз на 10 хв</b> (антиспам захист).\n"
                f"Зачекайте ще {wait_min} хв або запустіть @{bot_username} в особистих повідомленнях — там проекти приходять миттєво!",
                parse_mode="HTML",
            )
            return
        _group_hot_cooldown[chat_id] = now

    recent = get_recent_projects(limit=3)
    if not recent:
        await reply_text(update, "Наразі немає свіжих замовлень у базі. Зачекайте автоперевірки через кілька хвилин!")
        return

    lines = ["🔥 <b>Топ свіжих замовлень Freelancehunt:</b>\n"]

    for idx, p in enumerate(recent, 1):
        pid = p.get("id", "")
        title = p.get("name") or p.get("title") or "Замовлення"
        budget = p.get("budget") or "Договірний"
        url = p.get("url") or f"https://freelancehunt.com/project/{pid}.html"
        deep_link = f"https://t.me/{bot_username}?start=bid_{pid}"

        lines.append(f"{idx}. <b>{html.escape(title[:60])}</b>")
        lines.append(f"   💰 {html.escape(str(budget))}")
        lines.append(f"   👉 <a href=\"{deep_link}\">Отримати AI-ставку</a> | <a href=\"{url}\">На біржу</a>\n")

    lines.append(f"💡 <i>Щоб моніторити біржу 24/7 та писати відгуки за 2 сек — відкрийте @{bot_username} (7 днів безкоштовно)!</i>")

    keyboard = [
        [InlineKeyboardButton("🚀 Запустити персонального бота", url=f"https://t.me/{bot_username}?start=group_hot")]
    ]
    await reply_text(update, "\n".join(lines), reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML", disable_web_page_preview=True)


async def feedback_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not user:
        return
    user_id = str(user.id)
    text = " ".join(context.args).strip() if context.args else ""
    bot_username = context.bot.username or "HUNTua_bot"

    if not text:
        await reply_text(
            update,
            f"💡 <b>Маєте ідею, як покращити бота, або помітили баг?</b>\n\n"
            f"Напишіть нам прямо зараз:\n"
            f"<code>/feedback Текст вашої ідеї або зауваження</code>\n\n"
            f"🎁 <b>Бонус:</b> За кожну змістовну пропозицію ми автоматично нараховуємо <b>+3 дні безкоштовної підписки</b> до вашого акаунту!\n\n"
            f"Також можна надіслати ідею через Mini App у розділі «Параметри».",
            parse_mode="HTML",
        )
        return

    if len(text) > 2000:
        await reply_text(update, "⚠️ Текст занадто довгий. Будь ласка, скоротіть до 2000 символів.")
        return

    username = user.username or ""
    full_name = user.full_name or ""
    add_feedback(user_id=user_id, text=text, username=username, full_name=full_name)

    try:
        add_bonus_days(user_id, days=3, reason="feedback")
    except Exception as bonus_err:
        logger.debug("Failed adding feedback bonus days: %s", bonus_err)

    if TELEGRAM_CHAT_ID:
        try:
            user_label = f"@{username}" if username else (full_name or f"ID: {user_id}")
            admin_msg = (
                f"💡 <b>Нова пропозиція / ідея від користувача!</b>\n\n"
                f"👤 Від: <b>{html.escape(user_label)}</b> (<code>{user_id}</code>)\n"
                f"🎁 Нараховано бонус: +3 дні підписки\n\n"
                f"📝 <i>{html.escape(text)}</i>"
            )
            await context.bot.send_message(chat_id=int(TELEGRAM_CHAT_ID), text=admin_msg, parse_mode="HTML")
        except Exception as admin_err:
            logger.debug("Failed notifying admin of feedback: %s", admin_err)

    reply_msg = (
        f"🎉 <b>Дякуємо за ваш відгук!</b>\n\n"
        f"Вашу пропозицію успішно збережено та передано розробнику.\n"
        f"🎁 Вам нараховано <b>+3 дні повної підписки</b> як подяку за допомогу в розвитку бота!"
    )
    await reply_text(update, reply_msg, parse_mode="HTML")


async def share_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not user:
        return
    user_id = str(user.id)
    bot_username = context.bot.username or "HUNTua_bot"
    ref_link = f"https://t.me/{bot_username}?start=ref_{user_id}"

    share_text = (
        "🔥 Знайшов крутого AI-бота для Freelancehunt: "
        "моніторить проекти кожні 3 хв і за 2 сек пише виграшні відгуки з розрахунком ціни! "
        "Спробуй безкоштовно 7 днів 👇"
    )
    share_url = f"https://t.me/share/url?url={ref_link}&text={quote(share_text)}"

    text = (
        f"📢 <b>Поділитися ботом із колегами (+7 днів за кожного)</b>\n\n"
        f"Натисніть кнопку нижче, щоб надіслати рекомендацію у свої чати фрілансерів або друзям.\n\n"
        f"🔗 <b>Ваше партнерське посилання:</b>\n<code>{ref_link}</code>\n\n"
        f"🎁 За кожного, хто приєднається, ви автоматично отримуєте <b>+7 днів повної підписки</b>!"
    )
    keyboard = [
        [InlineKeyboardButton("📢 Надіслати в чат / другу", url=share_url)],
        [InlineKeyboardButton("📊 Статистика партнерки", callback_data="sub_open")],
    ]
    await reply_text(update, text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")


async def market_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    stats = get_market_digest_stats()
    bot_username = context.bot.username or "HUNTua_bot"
    user = update.effective_user
    user_id = str(user.id) if user else ""
    ref_link = f"https://t.me/{bot_username}?start=ref_{user_id}" if user_id else f"https://t.me/{bot_username}"

    total = stats.get("total_projects", 0)
    sent = stats.get("sent_projects", 0)
    deals = stats.get("completed_deals_count", 0)
    deals_sum = stats.get("completed_deals_sum", 0.0)
    top = stats.get("recent_top", [])

    lines = [
        "📊 <b>Пульс біржі Freelancehunt (Аналітика AI Helper):</b>\n",
        f"🔍 Оброблено замовлень у базі: <b>{total}</b>",
        f"🎯 Релевантних IT-проектів: <b>{sent}</b>",
        f"💰 Зафіксовано угод у CRM: <b>{deals}</b> (на суму <b>{deals_sum:,.0f} грн</b>)\n",
    ]

    if top:
        lines.append("🔥 <b>Останні гарячі замовлення з високим Score:</b>")
        for idx, p in enumerate(top[:3], 1):
            t = p.get("title", "")
            b = p.get("budget") or "Договірний"
            s = p.get("score", 0)
            lines.append(f"{idx}. {html.escape(t[:45])} — <b>{html.escape(str(b))}</b> ({s}%)")
        lines.append("")

    lines.append(f"⚡️ <i>Отримуйте такі замовлення миттєво з готовою ставкою в @{bot_username}!</i>")

    share_text = f"📊 Пульс біржі Freelancehunt: {total} проектів у моніторингу! AI помічник для ставок: {ref_link}"
    share_url = f"https://t.me/share/url?url={ref_link}&text={quote(share_text)}"

    keyboard = [
        [InlineKeyboardButton("📢 Поділитися аналітикою в чат", url=share_url)],
        [InlineKeyboardButton("🚀 Запустити пошук проектів", url=f"https://t.me/{bot_username}?start=market")]
    ]

    await reply_text(update, "\n".join(lines), reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")



async def group_added_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    if not chat or chat.type not in ("group", "supergroup"):
        return

    new_members = update.message.new_chat_members if update.message else []
    bot_id = context.bot.id
    if not any(m.id == bot_id for m in new_members):
        return

    bot_username = context.bot.username or "HUNTua_bot"
    welcome_text = (
        f"👋 <b>Вітаю, учасники чату!</b>\n\n"
        f"Я <b>@{bot_username}</b> — AI-асистент для біржі <b>Freelancehunt</b>.\n\n"
        f"🔍 <b>Чим я корисний:</b>\n"
        f"• Моніторю нові замовлення кожні 3 хвилини\n"
        f"• Розраховую адекватний бюджет та оцінюю стек\n"
        f"• За 2 секунди пишу виграшні відгуки під клієнта\n\n"
        f"📌 Напишіть <b>/hot</b>, щоб побачити свіжі замовлення прямо тут у чаті.\n\n"
        f"👉 <a href=\"https://t.me/{bot_username}?start=group_welcome\">Запустити бота особисто</a> (перші 7 днів безкоштовно)!"
    )
    keyboard = [
        [InlineKeyboardButton("🚀 Запустити бота (7 днів безкоштовно)", url=f"https://t.me/{bot_username}?start=group_welcome")]
    ]
    try:
        await context.bot.send_message(
            chat_id=chat.id,
            text=welcome_text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="HTML",
        )
    except Exception as e:
        logger.debug("Could not send group welcome: %s", e)


async def subscribe_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user = update.effective_user
    user_id = user.id if user else chat_id

    if TELEGRAM_CHAT_ID and str(user_id) == str(TELEGRAM_CHAT_ID):
        await reply_text(update, "⭐️ Ви є власником бота! Для вас діє безстроковий безкоштовний доступ (VIP/Admin).")
        return

    price_uah = int(get_setting("sub_price", str(SUBSCRIPTION_MONTH_PRICE)))
    title = "Підписка на Freelance Helper (1 місяць)"
    description = "30 днів доступу: моніторинг Freelancehunt, AI-генерація пропозицій та CRM."
    payload = f"sub_month_{user_id}_{int(time.time())}"

    if PAYMENT_PROVIDER_TOKEN:
        prices = [LabeledPrice("Підписка на 1 місяць (30 днів)", price_uah * 100)]
        try:
            await context.bot.send_invoice(
                chat_id=chat_id,
                title=title,
                description=description,
                payload=payload,
                provider_token=PAYMENT_PROVIDER_TOKEN,
                currency="UAH",
                prices=prices,
                start_parameter=f"sub_{user_id}",
            )
            return
        except Exception as err:
            logger.error("Error sending UAH invoice: %s", err)

    # Fallback to Telegram Stars
    try:
        stars_price = int(get_setting("sub_stars_price", str(SUBSCRIPTION_STARS_PRICE)))
        prices = [LabeledPrice("Підписка на 1 місяць (30 днів)", stars_price)]
        await context.bot.send_invoice(
            chat_id=chat_id,
            title=title,
            description=description,
            payload=payload,
            provider_token="",
            currency="XTR",
            prices=prices,
            start_parameter=f"sub_{user_id}",
        )
    except Exception as e:
        logger.warning("Could not send Stars invoice: %s", e)
        await reply_text(
            update,
            f"💳 Оформлення підписки на 1 місяць (30 днів)\n\n"
            f"Вартість: {price_uah} грн.\n"
            f"Для завершення налаштування еквайрингу підключіть платіжного провайдера в @BotFather або зверніться до адміністратора."
        )


async def pre_checkout_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.pre_checkout_query
    if query and query.invoice_payload.startswith("sub_"):
        await query.answer(ok=True)
    elif query:
        await query.answer(ok=False, error_message="Недійсний запит оплати.")


async def successful_payment_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    sp = update.message.successful_payment
    user = update.effective_user
    user_id = user.id if user else update.effective_chat.id
    amount = sp.total_amount / 100.0 if sp.currency == "UAH" else float(sp.total_amount)

    sub = activate_user_subscription(
        user_id=user_id,
        days=30,
        amount=amount,
        provider=f"telegram_{sp.currency.lower()}",
        payment_id=sp.telegram_payment_charge_id,
        currency=sp.currency,
        chat_id=update.effective_chat.id,
        username=user.username if user else "",
        full_name=user.full_name if user else "",
    )

    exp_date = sub["expires_at"][:10]
    await reply_text(
        update,
        f"🎉 Оплату успішно зараховано!\n\n"
        f"✅ Вашу підписку активовано на 30 днів до {exp_date} (ще {sub['days_left']} дн.).\n"
        f"Всі можливості Freelance Helper розблоковано. Успішних замовлень! 🚀",
    )
    logger.info("Automatic subscription activated for user %s (amount: %s %s)", user_id, amount, sp.currency)


async def subscription_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id if user else update.effective_chat.id
    sub = get_user_subscription(user_id)
    price = get_setting("sub_price", str(SUBSCRIPTION_MONTH_PRICE))

    if not sub:
        await reply_text(update, f"У вас немає активної підписки.\nОформити на 1 місяць ({price} грн): /subscribe")
        return

    if sub.get("status") == "lifetime":
        await reply_text(update, "⭐️ Статус: Безстроковий доступ (Адміністратор)")
        return

    is_act = sub.get("is_active")
    exp_date = sub.get("expires_at", "")[:10]
    days_left = sub.get("days_left", 0)

    if is_act:
        status_name = "Пробний період" if sub.get("status") == "trial" else "Платна підписка"
        msg = (
            f"📋 Інформація про підписку:\n\n"
            f"• Статус: {status_name} ✅\n"
            f"• Дійсна до: {exp_date}\n"
            f"• Залишилося: {days_left} дн.\n\n"
            f"Продовжити на 30 днів ({price} грн): /subscribe"
        )
    else:
        msg = (
            f"⛔️ Ваша підписка закінчилася ({exp_date}).\n\n"
            f"Поновити на 30 днів ({price} грн): /subscribe"
        )
    await reply_text(update, msg)


async def grant_sub_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not user or str(user.id) != str(TELEGRAM_CHAT_ID):
        await reply_text(update, "Ця команда доступна лише адміністратору.")
        return

    args = context.args
    if not args:
        await reply_text(update, "Використання: /grant_sub <user_id> [кількість_днів]")
        return

    target_user_id = args[0].strip()
    days = int(args[1]) if len(args) > 1 and args[1].isdigit() else 30

    sub = grant_user_subscription(target_user_id, days=days, admin_note=f"granted by {user.id}")
    await reply_text(
        update,
        f"✅ Користувачу {target_user_id} нараховано {days} днів підписки!\n"
        f"Дійсна до: {sub['expires_at'][:10]} (ще {sub['days_left']} дн.)."
    )
    if sub.get("chat_id"):
        try:
            await context.bot.send_message(
                chat_id=int(sub["chat_id"]),
                text=f"🎁 Адміністратор надав вам {days} днів підписки!\nДійсна до {sub['expires_at'][:10]}.",
            )
        except Exception:
            pass


async def subscribers_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not user or str(user.id) != str(TELEGRAM_CHAT_ID):
        await reply_text(update, "Ця команда доступна лише адміністратору.")
        return

    all_subs = get_all_subscriptions()
    if not all_subs:
        await reply_text(update, "Поки немає жодного підписника.")
        return

    active_count = sum(1 for s in all_subs if s.get("is_active"))
    trial_count = sum(1 for s in all_subs if s.get("status") == "trial" and s.get("is_active"))
    paid_count = sum(1 for s in all_subs if s.get("status") == "active" and s.get("is_active"))

    lines = [
        "📊 Підписники бота:\n",
        f"• Всього зареєстровано: {len(all_subs)}",
        f"• Активних: {active_count} (платних: {paid_count}, тріал: {trial_count})\n",
    ]

    for s in all_subs[:20]:
        uname = f"@{s['username']}" if s.get("username") else s.get("full_name") or s["user_id"]
        exp = s["expires_at"][:10]
        status_icon = "✅" if s.get("is_active") else "❌"
        lines.append(f"{status_icon} {uname} ({s.get('status')}): до {exp} ({s.get('days_left', 0)} дн.)")

    await reply_text(update, "\n".join(lines))


async def set_price_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not user or str(user.id) != str(TELEGRAM_CHAT_ID):
        await reply_text(update, "Ця команда доступна лише адміністратору.")
        return

    args = context.args
    if not args or not args[0].isdigit():
        curr_price = get_setting("sub_price", str(SUBSCRIPTION_MONTH_PRICE))
        curr_stars = get_setting("sub_stars_price", str(SUBSCRIPTION_STARS_PRICE))
        await reply_text(update, f"Поточна вартість підписки: {curr_price} грн ({curr_stars} ⭐️ Stars).\nЗмінити: /set_price <сума_в_грн> [кількість_зірок]")
        return

    new_price = int(args[0])
    set_setting("sub_price", str(new_price))
    if len(args) > 1 and args[1].isdigit():
        new_stars = int(args[1])
    else:
        new_stars = new_price
    set_setting("sub_stars_price", str(new_stars))
    await reply_text(update, f"✅ Вартість підписки на 1 місяць встановлено: {new_price} грн ({new_stars} ⭐️ Stars).")


async def test_ai(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_user_access(update, context):
        return
    test_project = {
        "title": "Python-скрипт для парсингу товарів із сайту",
        "description": "Потрібен Python-скрипт для парсингу товарів із сайту. Результат зберегти в Excel.",
        "budget": "1500 грн",
        "bids_count": 4,
        "url": "https://example.com/test",
    }

    started_at = time.monotonic()
    from ..rules import classify_project, count_good_keyword_matches, build_rules_fallback_analysis
    f_res = classify_project(test_project["title"], test_project["description"])
    g_matches = count_good_keyword_matches(test_project["title"], test_project["description"])
    analysis_data = build_rules_fallback_analysis(f_res, test_project["title"], test_project["description"], 4, "1500 грн")
    score = int(analysis_data.get("success_chance", 0))
    elapsed = time.monotonic() - started_at

    sample_msg = format_project_message(
        title=test_project["title"],
        budget=test_project["budget"],
        bids_count=test_project["bids_count"],
        url=test_project["url"],
        score=score,
        analysis_data=analysis_data,
        filter_result=f_res,
        numeric_bids_count=4,
        good_matches=g_matches,
        project_dict=test_project,
    )

    await reply_text(
        update,
        f"✅ Тест евристичного аналізатора ({elapsed:.4f} сек):\n\n{sample_msg}",
    )


async def check_projects(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.effective_message

    if not message:
        logger.warning("Cannot run /check: update has no effective_message")
        return

    if not await check_user_access(update, context):
        return

    await message.reply_text("Шукаю нові проєкти...")
    logger.info("Manual check started")
    debug_stats = make_check_debug_stats()

    try:
        projects = await get_projects()
        logger.info("Fetched projects: %s", len(projects))
    except Exception as error:
        logger.exception("Freelancehunt API error")
        debug_stats["api_ok"] = False
        debug_stats["api_errors"].append(str(error))
        set_last_check_stats(0, 0, str(error))
        await message.reply_text(f"Помилка Freelancehunt API:\n{error}")
        await message.reply_text(format_check_debug_stats(debug_stats, 0, 0))
        return

    if not projects:
        await message.reply_text("Отримано 0 проєктів з Freelancehunt.")
        set_last_check_stats(0, 0)
        await message.reply_text(format_check_debug_stats(debug_stats, 0, 0))
        return

    sent_count = 0
    processed_count = 0

    for project in projects:
        if processed_count >= 20:
            break

        try:
            was_sent = await process_and_send_project(
                message.reply_text,
                project,
                debug_stats=debug_stats,
            )
            processed_count += 1

        except Exception as error:
            logger.exception("Project processing error")
            debug_stats["ai_ok"] = False
            debug_stats["ai_errors"].append(str(error)[:200])
            await message.reply_text(f"Помилка обробки проєкту:\n{error}")
            continue

        if was_sent:
            sent_count += 1
            await asyncio.sleep(0.35)

        if sent_count >= 3:
            break

    if sent_count == 0:
        await message.reply_text("Нових відповідних проєктів поки немає.")

    set_last_check_stats(len(projects), sent_count)
    await message.reply_text(
        format_check_debug_stats(debug_stats, len(projects), processed_count)[:4000]
    )

    logger.info(
        "Manual check finished | sent=%s | processed=%s",
        sent_count,
        processed_count,
    )


async def auto_check(context: ContextTypes.DEFAULT_TYPE):
    chat_id = context.job.chat_id
    logger.info("Auto check started")

    try:
        projects = await get_projects()
        logger.info("Fetched projects: %s", len(projects))
    except Exception as error:
        logger.exception("Auto API error")
        set_last_check_stats(0, 0, str(error))
        try:
            await context.bot.send_message(chat_id=chat_id, text=f"Помилка API:\n{error}")
        except TelegramError:
            pass
        return

    active_subs = get_active_subscribers()
    recipient_chats = set()
    if chat_id:
        recipient_chats.add(chat_id)
    if TELEGRAM_CHAT_ID:
        try:
            recipient_chats.add(int(TELEGRAM_CHAT_ID))
        except ValueError:
            pass
    for s in active_subs:
        if s.get("chat_id"):
            try:
                recipient_chats.add(int(s["chat_id"]))
            except (ValueError, TypeError):
                pass

    async def send_func(text, reply_markup=None, **kwargs):
        for cid in recipient_chats:
            try:
                await context.bot.send_message(
                    chat_id=cid,
                    text=text,
                    reply_markup=reply_markup,
                    **kwargs,
                )
            except BadRequest as b_err:
                if "chat not found" in str(b_err).lower():
                    logger.warning("Chat not found (chat_id=%s)", cid)
            except Forbidden as f_err:
                logger.warning("Bot blocked by user (chat_id=%s): %s", cid, f_err)
            except Exception as e:
                logger.debug("Failed sending to subscriber %s: %s", cid, e)

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
            await asyncio.sleep(0.35)

            # Broadcast to public showcase channel if configured
            public_chan = get_setting("public_channel", "").strip()
            if public_chan:
                raw_pid = str(project.get("id", ""))
                if raw_pid and not is_project_broadcast(raw_pid):
                    try:
                        await broadcast_project_to_channel(context.bot, public_chan, project)
                        record_channel_broadcast(raw_pid, public_chan)
                    except Exception as chan_err:
                        logger.warning("Channel broadcast error (%s): %s", public_chan, chan_err)

        if sent_count >= 3:
            break

    logger.info(
        "Auto check finished | sent=%s | processed=%s",
        sent_count,
        processed_count,
    )
    set_last_check_stats(len(projects), sent_count)

    try:
        cleaned = cleanup_old_projects(days=30)
        if cleaned > 0:
            logger.info("DB cleanup: removed %s old skipped projects", cleaned)
    except Exception as cleanup_err:
        logger.warning("DB cleanup error: %s", cleanup_err)


async def auto_on(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_chat:
        logger.warning("Cannot enable auto check: update has no effective_chat")
        return

    if update.effective_chat.type in ("group", "supergroup"):
        bot_username = context.bot.username or "HUNTua_bot"
        await reply_text(
            update,
            f"⚠️ <b>Автоперевірка доступна лише в особистих повідомленнях!</b>\n\n"
            f"У групових чатах автоматичну розсилку кожні 3 хвилини вимкнено, щоб уникнути спаму та бану бота.\n"
            f"👉 Запустіть бота особисто: @{bot_username}",
            parse_mode="HTML",
        )
        return

    if not context.job_queue:
        await reply_text(update, "Job queue недоступний. Перевстанови python-telegram-bot[job-queue].")
        return

    chat_id = update.effective_chat.id
    current_jobs = context.job_queue.get_jobs_by_name(str(chat_id))

    if current_jobs:
        await reply_text(update, "Автоперевірка вже увімкнена ✅")
        return

    context.job_queue.run_repeating(
        auto_check,
        interval=AUTO_CHECK_INTERVAL_SECONDS,
        first=AUTO_CHECK_FIRST_RUN_SECONDS,
        chat_id=chat_id,
        name=str(chat_id),
    )

    logger.info("Auto check enabled for chat_id=%s", chat_id)
    await reply_text(
        update,
        f"Автоперевірку увімкнено ✅\nІнтервал: {AUTO_CHECK_INTERVAL_SECONDS} сек."
    )


async def auto_off(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_chat:
        logger.warning("Cannot disable auto check: update has no effective_chat")
        return

    if not context.job_queue:
        await reply_text(update, "Job queue недоступний.")
        return

    chat_id = update.effective_chat.id
    current_jobs = context.job_queue.get_jobs_by_name(str(chat_id))

    for job in current_jobs:
        job.schedule_removal()

    logger.info("Auto check disabled for chat_id=%s", chat_id)
    await reply_text(update, "Автоперевірку вимкнено ⏹")


async def health_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    database_ok, database_reason = check_database()
    min_score = get_setting("min_score", str(MIN_SCORE))

    api_status = "OK"
    api_reason = "not checked"

    try:
        projects = await get_projects()
        api_reason = f"{len(projects)} projects"
    except Exception as error:
        logger.warning("Health Freelancehunt API check failed: %s", error)
        api_status = "error"
        api_reason = str(error)[:120]

    text = f"""
🩺 Health

Bot: OK
TELEGRAM_BOT_TOKEN: {env_status(TELEGRAM_BOT_TOKEN)}
TELEGRAM_CHAT_ID: {env_status(TELEGRAM_CHAT_ID)}
FREELANCEHUNT_TOKEN: {env_status(FREELANCEHUNT_TOKEN)}
Database: {"OK" if database_ok else "error"} ({database_reason})
Freelancehunt API: {api_status} ({api_reason})
Аналізатор: Швидкий евристичний (без Ollama)
AUTO_CHECK_INTERVAL_SECONDS: {AUTO_CHECK_INTERVAL_SECONDS}
MIN_SCORE: {min_score}
""".strip()

    await reply_text(update, text[:4000])


def setting_bool_from_env(value, default: bool) -> bool:
    if value is None:
        return default

    return str(value).lower() in {"1", "true", "yes", "on", "так"}


async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    stats = get_stats()
    min_score = get_setting("min_score", str(MIN_SCORE))
    ai_enabled = get_setting("AI_ANALYSIS_ENABLED", str(AI_ANALYSIS_ENABLED)).lower()
    interval_min = AUTO_CHECK_INTERVAL_SECONDS // 60 if AUTO_CHECK_INTERVAL_SECONDS >= 60 else AUTO_CHECK_INTERVAL_SECONDS

    text = f"""📊 Статистика роботи бота

⏱ За останні 24 години:
• Оброблено проєктів: {stats.get("recent_24h", 0)}
• Надіслано у Telegram: {stats.get("recent_sent_24h", 0)}

📦 За весь час:
• Усього в базі: {stats["total"]}
• Надіслано користувачу: {stats.get("sent", 0)}

👍 Оцінки та якість:
• 🔥 Дуже підходять: {stats["great"]}
• ✅ Добрі: {stats["good"]}
• 🤔 Можливо: {stats["maybe"]}
• ❌ Погані: {stats["bad"]}
• 🚫 Не моє: {stats["not_mine"]}
• ⏭ Пропущені: {stats["skip"]}
• ⚪ Без оцінки: {stats["unrated"]}

⚙️ Поточні параметри:
• 🎯 Поріг score: {min_score}
• 🤖 AI-аналіз: {ai_enabled}
• 🔄 Інтервал автопошуку: {interval_min} хв"""

    await reply_text(update, text)


async def settings_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        min_score = get_setting("min_score", str(MIN_SCORE))
        await reply_text(
            update,
            f"Поточний мінімальний score: {min_score}\n\n" f"Щоб змінити:\n/settings 35"
        )
        return

    value = context.args[0]

    if not value.isdigit():
        await reply_text(update, "Score має бути числом. Наприклад: /settings 35")
        return

    score = int(value)

    if score < 0 or score > 100:
        await reply_text(update, "Score має бути від 0 до 100.")
        return

    set_setting("min_score", str(score))
    logger.info("Min score changed to %s", score)

    await reply_text(update, f"✅ Мінімальний score змінено на {score}")


async def threshold_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await settings_command(update, context)


async def profile_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    profile = get_setting("user_profile", USER_PROFILE)
    await reply_text(update, f"👤 Поточний профіль:\n\n{profile}")


async def profile_set_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    profile = " ".join(context.args).strip()

    if len(profile) < 20:
        await reply_text(
            update,
            "Профіль занадто короткий. Напиши хоча б 20 символів після /profile_set."
        )
        return

    set_setting("user_profile", profile)
    logger.info("User profile changed")
    await reply_text(update, "✅ Профіль оновлено.")


async def portfolio_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    links = get_portfolio_links()
    if not links:
        await reply_text(
            update,
            "📁 Посилання на портфоліо ще не налаштовані.\n\n"
            "Щоб додати посилання під категорію, використовуйте:\n"
            "<code>/portfolio_set bot https://github.com/...</code>\n"
            "<code>/portfolio_set parsing https://github.com/...</code>\n"
            "<code>/portfolio_set backend https://github.com/...</code>\n"
            "<code>/portfolio_set web https://site.com/...</code>\n"
            "<code>/portfolio_set excel https://docs.google.com/...</code>\n"
            "<code>/portfolio_set general https://github.com/my-profile</code>",
            parse_mode="HTML",
        )
        return

    lines = ["📁 <b>Налаштовані посилання на портфоліо:</b>\n"]
    for cat, url in sorted(links.items()):
        lines.append(f"• <b>{cat}</b>: {url}")

    lines.append("\nЩоб змінити: <code>/portfolio_set &lt;категорія&gt; &lt;посилання&gt;</code>")
    await reply_text(update, "\n".join(lines), parse_mode="HTML")


async def portfolio_set_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args or []
    if len(args) < 2:
        await reply_text(
            update,
            "ℹ️ Формат: /portfolio_set <категорія> <посилання>\n\n"
            "Доступні категорії:\n"
            "• <code>bot</code> — Telegram-боти\n"
            "• <code>parsing</code> — парсинг та скрейпінг\n"
            "• <code>backend</code> — бекенд та API\n"
            "• <code>web</code> — сайти, верстка, WordPress\n"
            "• <code>excel</code> — Excel / Google Таблиці\n"
            "• <code>general</code> — універсальне посилання (за замовчуванням)",
            parse_mode="HTML",
        )
        return

    category = args[0].lower().strip()
    url = args[1].strip()

    valid_categories = {
        "bot",
        "telegram_bot",
        "parsing",
        "backend",
        "api",
        "web",
        "frontend",
        "wordpress",
        "excel",
        "general",
    }
    if category not in valid_categories:
        await reply_text(
            update,
            f"❌ Невідома категорія: <code>{category}</code>.\n"
            "Використовуйте одну з: bot, parsing, backend, web, excel, general.",
            parse_mode="HTML",
        )
        return

    if category == "telegram_bot":
        category = "bot"
    elif category == "api":
        category = "backend"
    elif category in {"frontend", "wordpress"}:
        category = "web"

    set_portfolio_link(category, url)
    logger.info("Portfolio link updated for %s: %s", category, url)
    await reply_text(
        update,
        f"✅ Збережено посилання для категорії <b>{category}</b>:\n{url}",
        parse_mode="HTML",
    )


async def ai_on(update: Update, context: ContextTypes.DEFAULT_TYPE):
    set_setting("AI_ANALYSIS_ENABLED", "true")
    await reply_text(
        update,
        "⚡ Швидкий евристичний аналіз увімкнено (миттєва оцінка без затримок)."
    )


async def ai_off(update: Update, context: ContextTypes.DEFAULT_TYPE):
    set_setting("AI_ANALYSIS_ENABLED", "false")
    await reply_text(
        update,
        "ℹ️ Базовий евристичний фільтр активний за замовчуванням."
    )


async def recent_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_user_access(update, context):
        return

    projects = get_recent_projects(limit=LAST_PROJECTS_LIMIT)

    if not projects:
        await reply_text(update, "Поки немає збережених проєктів.")
        return

    lines = ["🕘 Останні знайдені проєкти:"]

    for project in projects:
        status = project.get("status") or "unknown"
        score = project.get("score")
        score_text = "?" if score is None else str(score)
        reason = project.get("reason") or "reason не збережено"
        lines.append(
            f"\nID: {project['project_id']}\n"
            f"Назва: {project['title']}\n"
            f"Опис: {project_short_description(project)}\n"
            f"Budget: {project.get('budget')}\n"
            f"Bids: {project.get('bids_count')}\n"
            f"Score: {score_text}\n"
            f"Status: {status}\n"
            f"Reason: {reason}\n"
            f"{project.get('url') or ''}"
        )

    await reply_text(update, "\n".join(lines)[:4000])


async def last_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await recent_command(update, context)


async def why_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_user_access(update, context):
        return

    if not context.args:
        await reply_text(update, "Вкажи ID проєкту. Наприклад: /why 123456")
        return

    project_id = context.args[0]
    project = get_project(project_id)

    if not project:
        await reply_text(update, "Проєкт не знайдено в базі.")
        return

    text = f"""
📌 {project.get("title")}

{project.get("analysis") or "Аналіз не збережено."}

🔗 {project.get("url") or ""}
""".strip()

    await reply_text(update, text[:4000])


async def cases_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_user_access(update, context):
        return

    user_id = str(update.effective_user.id) if update.effective_user else None
    cases = get_portfolio_cases(user_id=user_id)
    if not cases:
        await reply_text(
            update,
            "📂 <b>База кейсів порожня.</b>\n\n"
            "Додайте ваші реальні роботи для автоматичної підстановки у ставки:\n"
            "<code>/case_add bot Назва кейсу | https://посилання | Короткий опис</code>\n\n"
            "Категорії: <code>bot</code>, <code>parser</code>, <code>backend</code>, <code>web</code>, <code>mobile</code>, <code>devops</code>, <code>general</code>",
            parse_mode="HTML",
        )
        return

    lines = ["📁 <b>Ваші реальні кейси в портфоліо:</b>\n"]
    for c in cases:
        lines.append(
            f"🔹 <b>[ID {c['id']}]</b> [{c['category'].upper()}] {c['title']}\n"
            f"   🔗 {c['url'] or 'Без посилання'}\n"
            f"   📝 {c['description'] or 'Без опису'}\n"
        )
    lines.append("Видалити: <code>/case_del ID</code>\nДодати: <code>/case_add кат Назва | URL | Опис</code>")
    await reply_text(update, "\n".join(lines)[:4000], parse_mode="HTML", disable_web_page_preview=True)


async def case_add_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_user_access(update, context):
        return

    if not context.args:
        await reply_text(
            update,
            "ℹ️ <b>Формат додавання кейсу:</b>\n"
            "<code>/case_add <категорія> <назва> | <посилання> | <опис></code>\n\n"
            "Приклад:\n"
            "<code>/case_add bot Telegram Shop Bot | https://t.me/example_bot | Бот інтернет-магазину з оплатою LiqPay</code>",
            parse_mode="HTML",
        )
        return

    full_arg = " ".join(context.args)
    first_space = full_arg.find(" ")
    if first_space == -1:
        category = full_arg.lower()
        rest = ""
    else:
        category = full_arg[:first_space].lower()
        rest = full_arg[first_space:].strip()

    parts = [p.strip() for p in rest.split("|")]
    title = parts[0] if parts and parts[0] else f"Кейс {category}"
    url = parts[1] if len(parts) > 1 else ""
    desc = parts[2] if len(parts) > 2 else ""

    user_id = str(update.effective_user.id) if update.effective_user else None
    case_id = add_portfolio_case(category=category, title=title, description=desc, url=url, user_id=user_id)
    await reply_text(
        update,
        f"✅ <b>Кейс успішно додано! [ID {case_id}]</b>\n\n"
        f"🏷 <b>Категорія:</b> {category}\n"
        f"📌 <b>Назва:</b> {title}\n"
        f"🔗 <b>URL:</b> {url or 'не вказано'}\n"
        f"📝 <b>Опис:</b> {desc or 'не вказано'}\n\n"
        "Тепер цей кейс буде автоматично підставлятися у відповідні ставки!",
        parse_mode="HTML",
        disable_web_page_preview=True,
    )


async def case_del_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_user_access(update, context):
        return

    if not context.args or not context.args[0].isdigit():
        await reply_text(update, "Вкажіть числовий ID кейсу для видалення. Наприклад: <code>/case_del 2</code>", parse_mode="HTML")
        return

    case_id = int(context.args[0])
    user_id = str(update.effective_user.id) if update.effective_user else None
    ok = delete_portfolio_case(case_id, user_id=user_id)
    if ok:
        await reply_text(update, f"✅ Кейс [ID {case_id}] видалено з бази.")
    else:
        await reply_text(update, f"❌ Кейс [ID {case_id}] не знайдено.")


async def crm_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await income_command(update, context)


async def income_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_user_access(update, context):
        return

    user_id = str(update.effective_user.id) if update.effective_user else None
    stats = get_crm_stats(user_id=user_id)
    text = (
        f"💼 <b>Freelance CRM & Воронка замовлень</b>\n\n"
        f"📊 <b>Конверсія відгуків:</b>\n"
        f"• Подано заявок: <b>{stats['bids_placed']}</b>\n"
        f"• Замовники відповіли: <b>{stats['replied']}</b> ({stats['reply_rate']:.1f}% відгук)\n"
        f"• В активній роботі: <b>{stats['in_progress']}</b>\n"
        f"• Успішно завершено: <b>{stats['completed']}</b> (Win Rate: <b>{stats['win_rate']:.1f}%</b>)\n\n"
        f"💰 <b>Фінансові результати:</b>\n"
        f"• Дохід за поточний місяць: <b>{stats['income_month']:,.0f} грн</b>\n"
        f"• Загальний заробіток: <b>{stats['income_total']:,.0f} грн</b>\n\n"
        f"💡 <i>Позначайте статус проєктів кнопкою «💼 Я подав ставку» під кожною згенерованою пропозицією.</i>"
    )
    await reply_text(update, text, parse_mode="HTML")


async def quiet_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        current = get_setting("quiet_hours") or "23:00 - 08:00"
        is_active = is_quiet_hours_now()
        status_text = "🟢 Зараз діє (без звуку)" if is_active else "⚪ Зараз день (повідомлення зі звуком)"
        await reply_text(
            update,
            f"🌙 <b>Режим «Тихі години»</b>\n\n"
            f"⏱ Поточний інтервал: <b>{current}</b>\n"
            f"Статус: {status_text}\n\n"
            f"Корисні команди:\n"
            f"• <code>/quiet 23:00-08:00</code> — встановити нічний час\n"
            f"• <code>/quiet off</code> — вимкнути тихий режим\n\n"
            f"<i>Під час тихих годин усі нові проєкти надсилаються тихо (без звукового сигналу), щоб не турбувати сон.</i>",
            parse_mode="HTML",
        )
        return

    arg = context.args[0].lower().strip()
    if arg in {"off", "false", "0", "вимк", "вимкнути"}:
        set_setting("quiet_hours", "off")
        await reply_text(update, "☀️ Тихі години вимкнено. Усі сповіщення надходитимуть зі звуком.")
        return

    if "-" in arg:
        parts = arg.split("-")
        try:
            datetime.strptime(parts[0].strip(), "%H:%M")
            datetime.strptime(parts[1].strip(), "%H:%M")
            formatted = f"{parts[0].strip()} - {parts[1].strip()}"
            set_setting("quiet_hours", formatted)
            await reply_text(
                update,
                f"🌙 <b>Тихі години встановлено: {formatted}</b>\n"
                "У цей період бот надсилатиме нові проєкти без звуку.",
                parse_mode="HTML",
            )
            return
        except ValueError:
            pass

    await reply_text(
        update,
        "❌ Невірний формат. Вкажіть години як <code>HH:MM-HH:MM</code>, наприклад: <code>/quiet 23:00-08:00</code> або <code>/quiet off</code>",
        parse_mode="HTML",
    )


async def digest_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    min_score = safe_setting_int(get_setting("min_score", str(MIN_SCORE)), MIN_SCORE)
    projects = get_night_projects(hours=12, min_score=min_score)

    if not projects:
        await reply_text(
            update,
            "🌅 <b>Ранковий дайджест:</b>\n\n"
            "За останні 12 годин нових високих за score проєктів не надходило.\n"
            "Бот продовжує моніторинг у звичайному режимі!",
            parse_mode="HTML",
        )
        return

    lines = [
        f"🌅 <b>Ранковий дайджест ({len(projects)} найкращих проєктів за ніч):</b>\n"
    ]
    for i, p in enumerate(projects, 1):
        budget_str = p.get("budget") or "За домовленістю"
        score_val = p.get("score") or 0
        lines.append(
            f"{i}. <b>{p.get('title')}</b>\n"
            f"   💰 {budget_str}  •  🎯 Score: {score_val}/100\n"
            f"   🔗 <a href=\"{p.get('url')}\">Відкрити на біржі</a>\n"
        )
    lines.append("<i>Щоб згенерувати ставку, використовуйте кнопку під карткою проєкту в стрічці або /recent.</i>")

    await reply_text(update, "\n".join(lines)[:4000], parse_mode="HTML", disable_web_page_preview=True)


async def auto_morning_digest(context: ContextTypes.DEFAULT_TYPE):
    chat_id = context.job.chat_id if context.job else TELEGRAM_CHAT_ID
    if not chat_id:
        return
    min_score = safe_setting_int(get_setting("min_score", str(MIN_SCORE)), MIN_SCORE)
    projects = get_night_projects(hours=10, min_score=min_score)
    if not projects:
        return
    lines = [
        f"🌅 <b>Ранковий дайджест ({len(projects)} найкращих проєктів за ніч):</b>\n"
    ]
    for i, p in enumerate(projects, 1):
        budget_str = p.get("budget") or "За домовленістю"
        score_val = p.get("score") or 0
        lines.append(
            f"{i}. <b>{p.get('title')}</b>\n"
            f"   💰 {budget_str}  •  🎯 Score: {score_val}/100\n"
            f"   🔗 <a href=\"{p.get('url')}\">Відкрити на біржі</a>\n"
        )
    lines.append("<i>Щоб згенерувати ставку, використовуйте кнопку під карткою проєкту в стрічці або /recent.</i>")
    try:
        await context.bot.send_message(
            chat_id=int(chat_id),
            text="\n".join(lines)[:4000],
            parse_mode="HTML",
            disable_web_page_preview=True,
        )
    except Exception as e:
        logger.warning("Auto morning digest failed: %s", e)


async def backup_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_chat:
        return

    await reply_text(update, "⏳ Створюю резервну копію бази даних...")
    try:
        backup_path = create_database_backup()
        with open(backup_path, "rb") as doc:
            await context.bot.send_document(
                chat_id=update.effective_chat.id,
                document=doc,
                filename=backup_path.name,
                caption=f"📦 <b>Резервна копія бази даних</b>\n\nДата: {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}\nФайл: <code>{backup_path.name}</code>",
                parse_mode="HTML",
            )
    except Exception as exc:
        logger.exception("Backup failed: %s", exc)
        await reply_text(update, f"❌ Помилка створення бекапу: {exc}")


async def webapp_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "📱 <b>Telegram Mini App для Freelance AI Helper</b>\n\n"
        "Інтерактивний мобільний інтерфейс дозволяє:\n"
        "• 📊 Переглядати CRM воронку та заробіток\n"
        "• ⚡️ Копіювати згенеровані ставки в 1 дотик\n"
        "• ⚙️ Перемикати фільтри, тихі години та score прямо з телефону\n\n"
        "Файл інтерфейсу: <code>freelance_helper/web_app/index.html</code>\n"
        "Ви можете відкрити його локально або підключити як WebApp меню в @BotFather через команду <code>/setmenubutton</code>."
    )
    await reply_text(update, text, parse_mode="HTML")





async def reply_safe_markdown(message, text: str, reply_markup=None):
    """
    Sends message with Markdown parse_mode, automatically falling back to plain text
    if Telegram raises a Markdown entity parsing error.
    """
    try:
        return await message.reply_text(
            text,
            parse_mode="Markdown",
            reply_markup=reply_markup,
        )
    except BadRequest as error:
        err_lower = str(error).lower()
        if "entity" in err_lower or "can't find end" in err_lower or "parse" in err_lower:
            logger.warning("Markdown parsing failed, falling back to plain text: %s", error)
            return await message.reply_text(
                text,
                parse_mode=None,
                reply_markup=reply_markup,
            )
        raise


async def handle_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query

    if not query or not query.data:
        return

    user = update.effective_user
    user_id = user.id if user else None
    if user_id and not is_user_subscribed(user_id):
        try:
            await query.answer("⛔️ Термін підписки закінчився. Оформіть підписку: /subscribe", show_alert=True)
        except Exception:
            pass
        return

    if ":" not in query.data:
        logger.warning("Invalid callback data: %s", query.data)
        try:
            await query.answer()
        except Exception:
            pass
        return

    action, project_id = query.data.split(":", 1)
    project = get_project(project_id)
    message = query.message

    if not message:
        logger.warning("Cannot handle callback: query has no message")
        return

    if not project:
        try:
            await query.answer("Проєкт не знайдено в базі.", show_alert=True)
        except Exception:
            pass
        await message.reply_text("Проєкт не знайдено в базі.")
        return

    if not action.startswith("crm_") and action not in {"great", "good", "maybe", "bad", "not_mine", "skip"}:
        try:
            await query.answer()
        except Exception:
            pass

    if action in {"great", "good", "maybe", "bad", "not_mine", "skip"}:
        set_project_rating(project_id, action, user_id=user_id)
        logger.info("Project rated %s: %s (user %s)", action, project_id, user_id)

        labels = {
            "great": "🔥 Збережено: дуже підходить.",
            "good": "✅ Збережено: добрий проєкт.",
            "maybe": "🤔 Збережено: можливо.",
            "bad": "❌ Збережено: поганий проєкт.",
            "not_mine": "🚫 Збережено: не твоє.",
            "skip": "⏭ Проєкт пропущено.",
        }
        try:
            await query.answer(labels[action], show_alert=False)
        except Exception:
            pass

        try:
            await query.edit_message_reply_markup(
                reply_markup=project_keyboard(project_id, current_rating=action)
            )
        except Exception:
            pass

    elif action == "crm_bid":
        update_project_pipeline(project_id, "bid_placed", user_id=user_id)
        try:
            await query.answer("💼 Заявку додано у воронку CRM!", show_alert=False)
        except Exception:
            pass
        try:
            await query.edit_message_reply_markup(
                reply_markup=crm_pipeline_keyboard(project_id, current_status="bid_placed")
            )
        except Exception:
            await message.reply_text(
                f"💼 <b>Статус: Заявку подано!</b>\n\n"
                f"📌 {project.get('title')}\n"
                f"Замовлення додано до воронки активних заявок.\n"
                f"Коли замовник відповість, оновіть статус нижче:",
                parse_mode="HTML",
                reply_markup=crm_pipeline_keyboard(project_id, current_status="bid_placed"),
            )

    elif action == "crm_reply":
        update_project_pipeline(project_id, "replied", user_id=user_id)
        try:
            await query.answer("💬 Статус: Замовник відповів!", show_alert=False)
        except Exception:
            pass
        try:
            await query.edit_message_reply_markup(
                reply_markup=crm_pipeline_keyboard(project_id, current_status="replied")
            )
        except Exception:
            pass

    elif action == "crm_work":
        update_project_pipeline(project_id, "in_progress", user_id=user_id)
        try:
            await query.answer("🤝 Статус: Проєкт у роботі!", show_alert=False)
        except Exception:
            pass
        try:
            await query.edit_message_reply_markup(
                reply_markup=crm_pipeline_keyboard(project_id, current_status="in_progress")
            )
        except Exception:
            pass

    elif action == "crm_done":
        try:
            await query.answer("💰 Вкажіть суму угоди", show_alert=False)
        except Exception:
            pass
        amount, currency, _ = parse_budget_info(project.get("budget"))
        val = float(amount or 0)
        curr = currency or "UAH"
        context.user_data["pending_crm_done"] = {
            "project_id": project_id,
            "default_amount": val,
            "currency": curr,
        }
        confirm_markup = InlineKeyboardMarkup([
            [InlineKeyboardButton(f"💰 Зарахувати бюджет ({val:,.0f} {curr})", callback_data=f"crm_done_def:{project_id}")],
            [InlineKeyboardButton("❌ Скасувати", callback_data=f"crm_cancel:{project_id}")],
        ])
        await message.reply_text(
            f"💰 <b>Фіксація завершення проєкту:</b>\n"
            f"📌 <b>{project.get('title')}</b>\n\n"
            f"Бюджет біржі: <b>{val:,.0f} {curr}</b>\n\n"
            f"👉 <b>Надішліть фактичну суму угоди</b> повідомленням у чат (наприклад: <code>4500</code> або <code>150$</code>),\n"
            f"або натисніть кнопку нижче для зарахування бюджету біржі:",
            parse_mode="HTML",
            reply_markup=confirm_markup,
        )

    elif action == "crm_done_def":
        amount, currency, _ = parse_budget_info(project.get("budget"))
        val = float(amount or 0)
        curr = currency or "UAH"
        update_project_pipeline(project_id, "completed", deal_amount=val, currency=curr, user_id=user_id)
        context.user_data.pop("pending_crm_done", None)
        try:
            await query.answer(f"💰 Зараховано {val:,.0f} {curr}!", show_alert=False)
        except Exception:
            pass
        await message.reply_text(
            f"🏆 <b>Проєкт успішно завершено!</b>\n\n"
            f"📌 {project.get('title')}\n"
            f"💰 Зараховано в дохід: <b>{val:,.0f} {curr}</b>\n"
            f"Статистика оновлена у /income та /crm!",
            parse_mode="HTML",
        )

    elif action == "crm_cancel":
        context.user_data.pop("pending_crm_done", None)
        try:
            await query.answer("Скасовано", show_alert=False)
        except Exception:
            pass
        await message.reply_text("❌ Фіксацію завершення проєкту скасовано.")

    elif action == "crm_declined":
        update_project_pipeline(project_id, "declined", user_id=user_id)
        try:
            await query.answer("❌ Проєкт відхилено", show_alert=False)
        except Exception:
            pass
        await message.reply_text(
            f"❌ <b>Статус: Проєкт відхилено/архівовано.</b>\n📌 {project.get('title')}",
            parse_mode="HTML",
        )

    elif action in ["bid", "rebid"]:
        if not is_technical_project(project):
            await message.reply_text(
                unsuitable_project_text(project),
                reply_markup=unsuitable_project_keyboard(project_id),
            )
            return

        variant = "short"
        if action == "rebid":
            bid_variants = context.user_data.setdefault("bid_variants", {})
            current_index = bid_variants.get(project_id, 0)
            variant = BID_VARIANTS[(current_index + 1) % len(BID_VARIANTS)]
            bid_variants[project_id] = current_index + 1
        else:
            context.user_data.setdefault("bid_variants", {})[project_id] = 0

        variant_labels = {
            "short": "основна",
            "technical": "розгорнута",
            "cautious": "з питаннями",
        }
        variant_name = variant_labels.get(variant, variant)
        bid_text = generate_bid(project, variant=variant)
        context.user_data.setdefault("active_bids", {})[project_id] = bid_text

        # Preformatted code block enables 1-tap/1-click instant copying in Telegram
        escaped_bid = bid_text.replace("```", "'''")
        response_text = (
            f"📝 Пропозиція до проєкту ({variant_name})\n"
            f"👇 Натисніть на текст нижче, щоб скопіювати:\n\n"
            f"```\n{escaped_bid}\n```"
        )

        await reply_safe_markdown(
            message,
            response_text,
            reply_markup=bid_keyboard(project_id, url=project.get("url")),
        )

    elif action == "pitch":
        if not is_technical_project(project):
            await message.reply_text(
                unsuitable_project_text(project),
                reply_markup=unsuitable_project_keyboard(project_id),
            )
            return

        pitch_text = generate_chat_pitch(project)
        escaped_pitch = pitch_text.replace("```", "'''")
        response_text = (
            f"💬 Короткий відгук у чат (для першого контакту)\n"
            f"👇 Натисніть на текст нижче, щоб скопіювати:\n\n"
            f"```\n{escaped_pitch}\n```"
        )

        await reply_safe_markdown(
            message,
            response_text,
            reply_markup=bid_keyboard(project_id, url=project.get("url")),
        )

    elif action == "questions":
        questions = generate_questions(project)
        reply_markup = (
            questions_keyboard(project_id)
            if is_technical_project(project)
            else unsuitable_project_keyboard(project_id)
        )
        await message.reply_text(
            f"❓ Що уточнити:\n\n{questions}",
            reply_markup=reply_markup,
        )

    elif action == "publish_bid":
        if not FREELANCEHUNT_TOKEN:
            await message.reply_text(
                "❌ FREELANCEHUNT_TOKEN не знайдено в налаштуваннях бота.\n"
                "Додайте токен у файл .env для можливості прямої публікації ставок на біржі."
            )
            return

        amount, currency, _ = parse_budget_info(project.get("budget"))
        if not amount or amount <= 0:
            amount = 3000
        currency = currency or "UAH"

        kind = project_type(project)
        days = 2
        try:
            insights = extract_project_insights(project)
            time_est = insights.get("time_estimate", "1-2 дні")
            days_match = re.findall(r"\d+", time_est)
            if days_match:
                days = int(days_match[-1])
        except Exception:
            days = 3 if kind in {"telegram_bot", "backend"} else 2

        # Sweet spot pricing
        bids_cnt = int(project.get("bids_count") or 0)
        rec_amount = amount
        if amount and bids_cnt > 10:
            rec_amount = int(amount * 0.95 / 50) * 50

        active_bids = context.user_data.setdefault("active_bids", {})
        bid_text = active_bids.get(project_id)
        if not bid_text:
            bid_text = generate_bid(project, variant="short")
            active_bids[project_id] = bid_text

        pending = context.user_data.setdefault("pending_publish", {})
        pending[project_id] = {
            "days": days,
            "amount": rec_amount,
            "currency": currency,
            "comment": bid_text,
            "title": project.get("title", "Без назви"),
        }

        preview = bid_text[:280] + ("..." if len(bid_text) > 280 else "")
        prompt = (
            f"🚀 <b>Підтвердження публікації ставки</b>\n\n"
            f"📌 <b>Проєкт:</b> {project.get('title')}\n"
            f"💰 <b>Сума ставки:</b> {rec_amount:,} {currency}\n"
            f"⏱ <b>Термін виконання:</b> {days} дн.\n"
            f"🛡 <b>Тип безпечної угоди:</b> Робота з резервуванням (employer)\n\n"
            f"📝 <b>Текст пропозиції:</b>\n"
            f"<i>{preview}</i>\n\n"
            f"⚠️ <b>Увага:</b> Після підтвердження ставку буде миттєво відправлено на біржу Freelancehunt від вашого облікового запису.\n\n"
            f"Опублікувати ставку зараз?"
        )

        await message.reply_text(
            prompt,
            parse_mode="HTML",
            reply_markup=confirm_publish_keyboard(project_id),
        )

    elif action == "cancel_publish":
        pending = context.user_data.setdefault("pending_publish", {})
        pending.pop(project_id, None)
        await message.reply_text("❌ Публікацію ставки скасовано.")

    elif action == "confirm_publish":
        pending = context.user_data.setdefault("pending_publish", {})
        publish_data = pending.pop(project_id, None)

        if not publish_data:
            amount, currency, _ = parse_budget_info(project.get("budget"))
            if not amount or amount <= 0:
                amount = 3000
            currency = currency or "UAH"
            bid_text = generate_bid(project, variant="short")
            publish_data = {
                "days": 2,
                "amount": amount,
                "currency": currency,
                "comment": bid_text,
            }

        await message.reply_text("⏳ Відправляю ставку на Freelancehunt API...")
        try:
            res = await submit_project_bid(
                project_id=project_id,
                days=publish_data["days"],
                amount=publish_data["amount"],
                currency=publish_data["currency"],
                comment=publish_data["comment"],
            )
            logger.info("Bid posted for project %s: %s", project_id, res)
            update_project_pipeline(project_id, "bid_placed", deal_amount=float(publish_data["amount"]), currency=publish_data["currency"])
            await message.reply_text(
                f"✅ <b>Ставку успішно опубліковано на Freelancehunt!</b>\n\n"
                f"📌 {project.get('title')}\n"
                f"💰 {publish_data['amount']:,} {publish_data['currency']}  •  ⏱ {publish_data['days']} дн.\n"
                f"💼 Проєкт автоматично додано до вашої воронки CRM.\n\n"
                f"🔗 <a href=\"{project.get('url')}\">Переглянути проєкт на біржі</a>",
                parse_mode="HTML",
                disable_web_page_preview=True,
                reply_markup=crm_pipeline_keyboard(project_id, current_status="bid_placed"),
            )
        except FreelancehuntAPIError as err:
            logger.error("Freelancehunt API error submitting bid: %s", err)
            err_text = str(err)
            if "410" in err_text or "deprecation" in err_text.lower():
                escaped_comment = html.escape(publish_data["comment"])
                p_url = project.get("url") or f"https://freelancehunt.com/project/{project_id}.html"
                text_410 = (
                    f"⚠️ <b>Freelancehunt вимкнув подачу ставок через прямий API (HTTP 410).</b>\n"
                    f"Біржа дозволяє робити ставки тільки безпосередньо на сторінці проєкту:\n\n"
                    f"💰 <b>Сума:</b> {publish_data['amount']:,} {publish_data['currency']}  •  ⏱ <b>Термін:</b> {publish_data['days']} дн.\n\n"
                    f"📋 <b>Ваша згенерована ставка:</b>\n\n"
                    f"<code>{escaped_comment}</code>\n\n"
                    f"👉 Торкніться тексту ставки вище, щоб скопіювати його, відкрийте замовлення та вставте у форму:"
                )
                markup_410 = InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔗 Відкрити замовлення на біржі", url=p_url)],
                    [
                        InlineKeyboardButton("💼 Я відправив ставку (в CRM)", callback_data=f"crm_bid:{project_id}"),
                        InlineKeyboardButton("📱 Mini App", web_app=WebAppInfo(url=MINI_APP_URL)),
                    ],
                ])
                await message.reply_text(
                    text_410,
                    parse_mode="HTML",
                    disable_web_page_preview=True,
                    reply_markup=markup_410,
                )
            else:
                await message.reply_text(
                    f"❌ <b>Помилка Freelancehunt API:</b>\n{err}",
                    parse_mode="HTML",
                )
        except Exception as exc:
            logger.exception("Unexpected error submitting bid: %s", exc)
            await message.reply_text(
                f"❌ <b>Непередбачена помилка:</b> {exc}",
                parse_mode="HTML",
            )


async def handle_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.effective_message
    if not message or not message.text:
        return

    pending = context.user_data.get("pending_crm_done")
    if not pending:
        return

    text = message.text.strip()
    if text.lower() in {"/cancel_deal", "відміна", "скасувати", "cancel"}:
        context.user_data.pop("pending_crm_done", None)
        await message.reply_text("❌ Фіксацію завершення проєкту скасовано.")
        return

    import re
    cleaned = text.replace(" ", "")
    match = re.search(r"(\d+(?:[.,]\d+)?)", cleaned)
    if not match:
        await message.reply_text(
            "⚠️ Не вдалося розпізнати суму. Введіть число (наприклад: <code>4500</code> або <code>150$</code>) "
            "або відправте <b>скасувати</b> для виходу.",
            parse_mode="HTML",
        )
        return

    amount_str = match.group(1).replace(",", ".")
    try:
        amount = float(amount_str)
    except ValueError:
        return

    currency = pending.get("currency", "UAH")
    lower_text = text.lower()
    if "$" in text or "usd" in lower_text:
        currency = "USD"
    elif "€" in text or "eur" in lower_text:
        currency = "EUR"
    elif "грн" in lower_text or "uah" in lower_text:
        currency = "UAH"

    project_id = pending["project_id"]
    project = get_project(project_id) or {}
    title = project.get("title", f"ID {project_id}")

    user_id = str(update.effective_user.id) if update.effective_user else None
    update_project_pipeline(project_id, "completed", deal_amount=amount, currency=currency, user_id=user_id)
    context.user_data.pop("pending_crm_done", None)

    await message.reply_text(
        f"🏆 <b>Проєкт успішно завершено!</b>\n\n"
        f"📌 <b>{title}</b>\n"
        f"💰 Фактичний дохід: <b>{amount:,.0f} {currency}</b>\n\n"
        f"Дані зафіксовані у воронці CRM та враховані в /income та /crm!",
        parse_mode="HTML",
    )


async def export_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.effective_message
    if not message:
        return

    try:
        user_id = str(update.effective_user.id) if update.effective_user else None
        csv_data = export_crm_data_csv(user_id=user_id)
        import io
        bio = io.BytesIO(csv_data.encode("utf-8"))
        filename = f"crm_export_{datetime.now().strftime('%Y%m%d_%H%M')}.csv"
        bio.name = filename

        stats = get_crm_stats(user_id=user_id)
        win_rate = stats.get("win_rate", 0.0)
        income_month = stats.get("income_month", 0.0)
        income_total = stats.get("income_total", 0.0)

        caption = (
            f"📊 <b>Експорт CRM та фінансової звітності</b>\n\n"
            f"📈 Win Rate: <b>{win_rate:.1f}%</b>\n"
            f"💰 Загальний заробіток: <b>{income_total:,.0f} грн</b>\n\n"
            f"📁 Файл <code>{filename}</code> готовий для відкриття в Excel або Google Sheets."
        )

        await message.reply_document(
            document=bio,
            filename=filename,
            caption=caption,
            parse_mode="HTML",
        )
    except Exception as e:
        logger.exception("Export command error: %s", e)
        await message.reply_text(f"❌ Помилка експорту даних: {e}")

