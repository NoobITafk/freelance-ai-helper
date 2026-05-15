# Freelance AI Helper

**Freelance AI Helper** — це Telegram-бот для пошуку, фільтрації та AI-аналізу фриланс-проєктів із Freelancehunt.

Бот отримує нові замовлення через Freelancehunt API, аналізує їх локально через Ollama, виставляє score, надсилає відповідні проєкти в Telegram і допомагає згенерувати ставку для клієнта.

---

## Можливості

- отримання проєктів із Freelancehunt API;
- автоматична перевірка нових проєктів;
- AI-аналіз через локальну LLM-модель Ollama;
- score-система для оцінки проєкту;
- фільтрація неактуальних або ризикованих задач;
- Telegram-сповіщення;
- кнопки для взаємодії з проєктом;
- генерація ставки для клієнта;
- генерація уточнюючих питань;
- збереження проєктів у SQLite;
- good/bad/skip система для простого навчання бота;
- логування роботи в `logs/bot.log`.

---

## Технології

- Python
- python-telegram-bot
- Freelancehunt API
- Ollama
- SQLite
- requests
- python-dotenv

---

## Структура проєкту

```text
freelance_helper/
├─ app/
│  ├─ bot/
│  │  ├─ handlers.py
│  │  └─ keyboards.py
│  ├─ services/
│  │  └─ project_service.py
│  ├─ ai_analyzer.py
│  ├─ config.py
│  ├─ database.py
│  ├─ freelancehunt_api.py
│  ├─ logger.py
│  ├─ main.py
│  ├─ rules.py
│  └─ telegram_bot.py
├─ data/
├─ logs/
├─ .env.example
├─ .gitignore
├─ README.md
└─ requirements.txt
```

---

## Як працює бот

1. Бот отримує список проєктів через Freelancehunt API.
2. Спочатку застосовується швидкий keyword-фільтр.
3. Якщо проєкт підходить за базовими словами, він передається в Ollama.
4. AI оцінює:
   - відповідність навичкам;
   - складність;
   - ризик;
   - шанс виконання;
   - конкуренцію;
   - бюджет.
5. Система рахує фінальний score.
6. Якщо score достатній, бот надсилає проєкт у Telegram.
7. Користувач може натиснути кнопки:
   - `✅ Добрий`;
   - `❌ Поганий`;
   - `💬 Ставка`;
   - `❓ Уточнення`;
   - `🔁 Нова ставка`;
   - `⏭ Пропустити`.

---

## Встановлення

### 1. Клонування репозиторію

```bash
git clone https://github.com/NoobITafk/freelance-ai-helper.git
cd freelance-ai-helper
```

---

### 2. Створення virtual environment

```bash
python -m venv venv
```

---

### 3. Активація virtual environment

#### Linux / Arch Linux

```bash
source venv/bin/activate
```

#### Windows

```bash
venv\Scripts\activate
```

---

### 4. Встановлення залежностей

```bash
pip install -r requirements.txt
```

Якщо використовується автоперевірка через `job_queue`, встанови також:

```bash
pip install "python-telegram-bot[job-queue]"
```

---

## Ollama

Бот використовує локальну LLM-модель через Ollama.

### Встановлення Ollama

Офіційний сайт:

```text
https://ollama.com
```

### Завантаження моделі

```bash
ollama pull qwen2.5:7b
```

Для слабшого ноутбука можна використати легшу модель:

```bash
ollama pull qwen2.5:3b
```

---

## Налаштування `.env`

Створи файл `.env` у корені проєкту на основі `.env.example`.

Приклад:

```env
TELEGRAM_BOT_TOKEN=your_telegram_bot_token
TELEGRAM_CHAT_ID=your_telegram_chat_id

FREELANCEHUNT_TOKEN=your_freelancehunt_api_token

OLLAMA_URL=http://localhost:11434/api/generate
OLLAMA_MODEL=qwen2.5:3b
AI_ANALYSIS_ENABLED=true
AI_TIMEOUT_SECONDS=40
AUTO_CHECK_INTERVAL_SECONDS=180
AUTO_CHECK_FIRST_RUN_SECONDS=10
MAX_BIDS_COUNT=40
ANALYZE_MAYBE_PROJECTS=true
USER_PROFILE="Я студент 2 курсу інженерії програмного забезпечення, вчуся програмувати, можу vibe-code з AI, робити невеликі Python-скрипти, Telegram-ботів, API, парсинг, простий frontend і бази даних."
```

---

## Де взяти токени

### Telegram Bot Token

1. Відкрити Telegram.
2. Знайти `@BotFather`.
3. Виконати команду:

```text
/newbot
```

4. Скопіювати токен у `.env`.

### Telegram Chat ID

1. Запусти бота.
2. Напиши йому:

```text
/start
```

3. Бот покаже твій `chat_id`.
4. Встав його в `.env`.

### Freelancehunt API Token

Токен потрібно створити в особистому кабінеті Freelancehunt у розділі API / Apps.

---

## Запуск

```bash
python -m freelance_helper.app.main
```

Після запуску бот автоматично почне перевіряти проєкти, якщо в `.env` вказаний `TELEGRAM_CHAT_ID`.

---

## Команди бота

| Команда | Опис |
|---|---|
| `/start` | запуск бота і показ chat_id |
| `/help` | список команд |
| `/check` | перевірити проєкти вручну |
| `/auto_on` | увімкнути автопошук |
| `/auto_off` | вимкнути автопошук |
| `/stats` | показати статистику |
| `/settings` | показати мінімальний score |
| `/settings 35` | змінити мінімальний score |
| `/threshold 35` | швидко змінити мінімальний score |
| `/profile` | показати профіль виконавця для AI |
| `/profile_set текст` | змінити профіль виконавця |
| `/ai_on` | увімкнути AI-аналіз |
| `/ai_off` | вимкнути AI-аналіз і лишити fallback |
| `/recent` | показати останні 5 збережених проєктів |
| `/why project_id` | показати збережений аналіз проєкту |

---

## Логи

Логи зберігаються у файлі:

```text
logs/bot.log
```

Сирі відповіді AI для дебагу зберігаються у файлі:

```text
logs/ai_raw.log
```

Перегляд логів у реальному часі:

```bash
tail -f logs/bot.log
```

У логах можна побачити:

- коли бот стартував;
- коли почалась автоперевірка;
- скільки проєктів отримано;
- які проєкти відфільтровані;
- причину відсіювання;
- помилки API;
- помилки AI-аналізу.

---

## Score-система

Бот рахує score на основі:

- шансу виконання;
- складності;
- ризику;
- відповідності навичкам;
- бюджету;
- конкуренції;
- good/bad оцінок користувача.

Мінімальний score можна змінити командою:

```text
/settings 35
```

---

## Безпека

У репозиторій не можна додавати:

- `.env`;
- API токени;
- Telegram token;
- базу даних;
- логи;
- virtual environment.

Для цього використовується `.gitignore`.

---

## GitHub

Після змін:

```bash
git status
git add .
git commit -m "Update project"
git push
```

---

## Автор

NoobITafk

GitHub:

```text
https://github.com/NoobITafk
```

---

## Статус проєкту

Проєкт є pet-project для практики:

- API integration;
- Telegram bot development;
- local AI;
- async Python;
- SQLite;
- logging;
- project architecture.

---

## License

MIT
