from telegram import CopyTextButton, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo

from ..database import ALL_SKILL_CODES, SKILL_LABELS

MINI_APP_URL = "https://freelans.duckdns.org"


def project_keyboard(project_id: str, current_rating: str | None = None):
    good_label = "✅ Добрий" + (" ✔️" if current_rating == "good" else "")
    bad_label = "❌ Поганий" + (" ✔️" if current_rating == "bad" else "")
    keyboard = [
        [
            InlineKeyboardButton(good_label, callback_data=f"good:{project_id}"),
            InlineKeyboardButton(bad_label, callback_data=f"bad:{project_id}"),
        ],
        [
            InlineKeyboardButton("📝 Ставка", callback_data=f"bid:{project_id}"),
            InlineKeyboardButton("🚀 Подати через бота", callback_data=f"publish_bid:{project_id}"),
        ],
        [
            InlineKeyboardButton("💬 Відгук у чат", callback_data=f"pitch:{project_id}"),
            InlineKeyboardButton("❓ Уточнення", callback_data=f"questions:{project_id}"),
        ],
        [
            InlineKeyboardButton("📱 Mini App", web_app=WebAppInfo(url=MINI_APP_URL)),
            InlineKeyboardButton("⏭ Пропустити", callback_data=f"skip:{project_id}"),
        ],
    ]

    return InlineKeyboardMarkup(keyboard)


def bid_keyboard(project_id: str, url: str | None = None):
    project_url = url or f"https://freelancehunt.com/project/{project_id}.html"
    keyboard = [
        [
            InlineKeyboardButton("🚀 Зробити ставку", url=project_url),
            InlineKeyboardButton("⚡️ Подати через бота", callback_data=f"publish_bid:{project_id}"),
        ],
        [
            InlineKeyboardButton("🔁 Нова ставка", callback_data=f"rebid:{project_id}"),
            InlineKeyboardButton("💬 Відгук у чат", callback_data=f"pitch:{project_id}"),
        ],
        [
            InlineKeyboardButton("❓ Уточнення", callback_data=f"questions:{project_id}"),
            InlineKeyboardButton("⏭ Пропустити", callback_data=f"skip:{project_id}"),
        ],
        [
            InlineKeyboardButton("💼 Я подав ставку", callback_data=f"crm_bid:{project_id}"),
            InlineKeyboardButton("📱 Mini App", web_app=WebAppInfo(url=MINI_APP_URL)),
        ],
    ]

    return InlineKeyboardMarkup(keyboard)


def crm_pipeline_keyboard(project_id: str, current_status: str | None = None):
    keyboard = [
        [
            InlineKeyboardButton("💬 Відповіли" + (" ✔️" if current_status == "replied" else ""), callback_data=f"crm_reply:{project_id}"),
            InlineKeyboardButton("🤝 В роботі" + (" ✔️" if current_status == "in_progress" else ""), callback_data=f"crm_work:{project_id}"),
        ],
        [
            InlineKeyboardButton("💰 Завершено" + (" ✔️" if current_status == "completed" else ""), callback_data=f"crm_done:{project_id}"),
            InlineKeyboardButton("❌ Відхилено", callback_data=f"crm_declined:{project_id}"),
        ],
    ]
    return InlineKeyboardMarkup(keyboard)


def confirm_publish_keyboard(project_id: str):
    keyboard = [
        [
            InlineKeyboardButton("✅ Підтвердити та відправити", callback_data=f"confirm_publish:{project_id}"),
        ],
        [
            InlineKeyboardButton("❌ Скасувати", callback_data=f"cancel_publish:{project_id}"),
        ],
    ]

    return InlineKeyboardMarkup(keyboard)


def questions_keyboard(project_id: str):
    keyboard = [
        [
            InlineKeyboardButton("📝 Згенерувати ставку", callback_data=f"bid:{project_id}"),
            InlineKeyboardButton("🔁 Інші питання", callback_data=f"questions:{project_id}"),
        ],
        [
            InlineKeyboardButton("⏭ Пропустити", callback_data=f"skip:{project_id}"),
        ],
    ]

    return InlineKeyboardMarkup(keyboard)


def unsuitable_project_keyboard(project_id: str):
    keyboard = [
        [
            InlineKeyboardButton("⏭ Пропустити", callback_data=f"skip:{project_id}"),
            InlineKeyboardButton("❓ Уточнення", callback_data=f"questions:{project_id}"),
        ],
    ]

    return InlineKeyboardMarkup(keyboard)


def skills_keyboard(user_skills: list[str]) -> InlineKeyboardMarkup:
    keyboard = []
    # Build 2-column grid of skills
    current_row = []
    for code in ALL_SKILL_CODES:
        is_active = code in user_skills
        label = f"{'✅' if is_active else '▫️'} {SKILL_LABELS.get(code, code)}"
        current_row.append(InlineKeyboardButton(label, callback_data=f"toggle_skill:{code}"))
        if len(current_row) == 2:
            keyboard.append(current_row)
            current_row = []
    if current_row:
        keyboard.append(current_row)

    keyboard.append([
        InlineKeyboardButton("🔄 Обрати всі напрямки", callback_data="reset_skills"),
    ])
    keyboard.append([
        InlineKeyboardButton("📱 Відкрити Mini App", web_app=WebAppInfo(url=MINI_APP_URL)),
    ])
    return InlineKeyboardMarkup(keyboard)

