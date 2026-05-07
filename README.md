# Freelance AI Helper

AI Telegram-бот для автоматичного аналізу проєктів із Freelancehunt за допомогою локальної LLM-моделі через Ollama.

---

# Можливості

- автоматичний пошук нових проєктів;
- аналіз проєктів через AI;
- система score для оцінки складності та ризику;
- Telegram-сповіщення;
- генерація ставки для клієнта;
- генерація уточнюючих питань;
- система навчання через good/bad;
- SQLite база даних;
- система логів;
- автоматична перевірка кожні 3 хвилини.

---

# Технології

- Python
- python-telegram-bot
- Ollama
- SQLite
- Freelancehunt API

---

# Структура проєкту

```text
app/
├─ bot/
├─ services/
├─ ai_analyzer.py
├─ config.py
├─ database.py
├─ freelancehunt_api.py
├─ logger.py
├─ rules.py
└─ telegram_bot.py
```

---

# Встановлення

## 1. Клонування репозиторію

```bash
git clone https://github.com/NoobITafk/freelance-ai-helper.git
cd freelance-ai-helper
```

---

## 2. Створення virtual environment

```bash
python -m venv venv
source venv/bin/activate
```

---

## 3. Встановлення залежностей

```bash
pip install -r requirements.txt
```

---

## 4. Встановлення Ollama

Встановити Ollama:

[Ollama](https://ollama.com?utm_source=chatgpt.com)

Завантажити модель:

```bash
ollama pull qwen2.5:7b
```

---

## 5. Налаштування `.env`

Створити `.env` на основі `.env.example`

Приклад:

```env
TELEGRAM_BOT_TOKEN=your_token
TELEGRAM_CHAT_ID=your_chat_id

FREELANCEHUNT_API_TOKEN=your_api_token

OLLAMA_URL=http://localhost:11434/api/generate
OLLAMA_MODEL=qwen2.5:7b
```

---

# Запуск

```bash
python -m app.main
```

---

# Команди бота

| Команда | Опис |
|---|---|
| `/check` | перевірити проєкти зараз |
| `/auto_on` | увімкнути автопошук |
| `/auto_off` | вимкнути автопошук |
| `/stats` | статистика |
| `/settings` | показати мінімальний score |
| `/settings 35` | змінити мінімальний score |
| `/help` | список команд |

---

# Як працює система

1. Бот отримує проєкти через Freelancehunt API.
2. AI аналізує:
   - складність;
   - ризики;
   - відповідність навичкам;
   - бюджет;
   - кількість ставок.
3. Система виставляє score.
4. Якщо score проходить мінімальний поріг:
   - бот надсилає проєкт у Telegram;
   - генерує ставку;
   - генерує уточнення для клієнта.

---

# Логи

Логи зберігаються у:

```text
logs/bot.log
```

Перегляд у реальному часі:

```bash
tail -f logs/bot.log
```

---

# Автор

Maks Blyshchyk

GitHub:
[MaksBlyshchyk GitHub](https://github.com/MaksBlyshchyk?utm_source=chatgpt.com)

---

# License

MIT