from telegram import InlineKeyboardButton, InlineKeyboardMarkup


def project_keyboard(project_id: str):
    keyboard = [
        [
            InlineKeyboardButton("✅ Добрий", callback_data=f"good:{project_id}"),
            InlineKeyboardButton("❌ Поганий", callback_data=f"bad:{project_id}"),
        ],
        [
            InlineKeyboardButton("📝 Ставка", callback_data=f"bid:{project_id}"),
            InlineKeyboardButton("💬 Відгук у чат", callback_data=f"pitch:{project_id}"),
        ],
        [
            InlineKeyboardButton("❓ Уточнення", callback_data=f"questions:{project_id}"),
            InlineKeyboardButton("⏭ Пропустити", callback_data=f"skip:{project_id}"),
        ],
    ]

    return InlineKeyboardMarkup(keyboard)


def bid_keyboard(project_id: str):
    keyboard = [
        [
            InlineKeyboardButton("🔁 Нова ставка", callback_data=f"rebid:{project_id}"),
            InlineKeyboardButton("💬 Відгук у чат", callback_data=f"pitch:{project_id}"),
        ],
        [
            InlineKeyboardButton("❓ Уточнення", callback_data=f"questions:{project_id}"),
            InlineKeyboardButton("⏭ Пропустити", callback_data=f"skip:{project_id}"),
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
