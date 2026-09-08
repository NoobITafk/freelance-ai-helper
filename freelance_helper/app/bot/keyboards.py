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


def bid_keyboard(project_id: str, url: str | None = None):
    keyboard = []
    if url:
        keyboard.append([
            InlineKeyboardButton("🔗 Відкрити на Freelancehunt", url=url),
        ])
    else:
        keyboard.append([
            InlineKeyboardButton("🚀 Опублікувати на Freelancehunt", callback_data=f"publish_bid:{project_id}"),
        ])

    keyboard.extend([
        [
            InlineKeyboardButton("🔁 Нова ставка", callback_data=f"rebid:{project_id}"),
            InlineKeyboardButton("💬 Відгук у чат", callback_data=f"pitch:{project_id}"),
        ],
        [
            InlineKeyboardButton("❓ Уточнення", callback_data=f"questions:{project_id}"),
            InlineKeyboardButton("⏭ Пропустити", callback_data=f"skip:{project_id}"),
        ],
    ])

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
