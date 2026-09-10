# Freelance AI Helper

**Freelance AI Helper** — це легкий та швидкий Telegram-бот для пошуку, фільтрації та аналізу фриланс-проєктів із Freelancehunt.

Бот отримує нові замовлення через Freelancehunt API, аналізує їх через оптимізований евристичний рушій (визначає стек, складність, ризики та бюджет), виставляє score і миттєво надсилає релевантні проєкти у стислому та зрозумілому форматі в Telegram. Працює автономно на будь-якому VPS без важких локальних нейромереж.

---

## Можливості

- отримання проєктів із Freelancehunt API (асинхронно через `httpx`);
- автоматична перевірка нових проєктів у фоні;
- швидкий аналіз стеку (Python, FastAPI, Telegram, React, Supabase, Parsing тощо);
- score-система оцінки релевантності та ризиків;
- захист сильних технічних збігів від пропуску;
- короткі та зрозумілі сповіщення в Telegram (читаються за 3 секунди);
- інтерактивні кнопки: генерація ставок (коротка, технічна, обережна), уточнюючі питання;
- збереження проєктів у SQLite з ротацією старих даних;
- ротація логів (`RotatingFileHandler`);
- ready-to-deploy systemd сервіс для VPS.

---

## Технології

- Python 3.10+
- python-telegram-bot (async)
- Freelancehunt API
- httpx
- SQLite
- python-dotenv

---

## Структура проєкту

```text
freelance-ai-helper/
├─ .env.example
├─ .gitignore
├─ requirements.txt
├─ data/
├─ logs/
├─ deploy/
│  ├─ freelance-helper.service
│  └─ setup_vps.sh
├─ freelance_helper/
│  └─ app/
│     ├─ bot/
│     │  ├─ handlers.py
│     │  └─ keyboards.py
│     ├─ services/
│     │  └─ project_service.py
│     ├─ ai_analyzer.py
│     ├─ config.py
│     ├─ database.py
│     ├─ freelancehunt_api.py
│     ├─ logger.py
│     ├─ main.py
│     ├─ rules.py
│     └─ telegram_bot.py
├─ scripts/
│  └─ check_project_logic.py
└─ README.md
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
   - `📝 Ставка`;
   - `💬 Відгук у чат`;
   - `🚀 Зробити ставку`;
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

Command Prompt:

```bash
venv\Scripts\activate
```

PowerShell:

```powershell
.\venv\Scripts\Activate.ps1
```

---

### 4. Встановлення залежностей

```bash
python -m pip install -r requirements.txt
```

У `requirements.txt` вже є `python-telegram-bot[job-queue]` для автоперевірки.

---

## Формат сповіщень

Сповіщення про нові замовлення оптимізовані для швидкого читання зі смартфона (5-7 рядків, максимум користі):

```text
🚀 FastAPI backend для особистого кабінету

💰 Бюджет: 9000 грн  •  👥 Ставок: 7  •  🎯 Score: 80/100
🛠 Стек: Backend / API (FastAPI, PostgreSQL, API)
💡 Чому підходить: Збіг за ключовими словами: fastapi, postgresql, api
⚠️ Ризик: помірний (4/10)

🔗 https://freelancehunt.com/project/...
```

---

## Налаштування `.env`

Створи файл `.env` у **корені репозиторію** (або скопіюй `.env.example`):

```bash
cp .env.example .env
```

Приклад змінних (див. також `.env.example`):

```env
TELEGRAM_BOT_TOKEN=your_telegram_bot_token
TELEGRAM_CHAT_ID=your_telegram_chat_id
FREELANCEHUNT_TOKEN=your_freelancehunt_api_token
OLLAMA_MODEL=qwen2.5:3b
OLLAMA_URL=http://localhost:11434/api/generate
AI_ANALYSIS_ENABLED=true
AI_TIMEOUT_SECONDS=40
AUTO_CHECK_INTERVAL_SECONDS=180
AUTO_CHECK_FIRST_RUN_SECONDS=10
MAX_BIDS_COUNT=40
MIN_SCORE=45
ANALYZE_MAYBE_PROJECTS=true
USER_PROFILE="Можу виконувати невеликі Python-скрипти, Telegram-ботів, API-інтеграції, парсинг, HTML/CSS, WordPress-правки, Google Sheets/Excel автоматизацію і прості задачі з базами даних."
```

Важливо: використовуй саме `FREELANCEHUNT_TOKEN`. Якщо в старому `.env` було `FREELANCEHUNT_API_TOKEN`, перейменуй змінну вручну (файл `.env` не комітиться в Git).

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

## Запуск локально

```bash
python -m freelance_helper.app.main
```

Після запуску бот автоматично почне перевіряти проєкти, якщо в `.env` вказаний `TELEGRAM_CHAT_ID`.

---

## Деплой на VPS (systemd)

### 1. Клонування репозиторію та запуск скрипту встановлення

```bash
git clone https://github.com/NoobITafk/freelance-ai-helper.git /opt/freelance-ai-helper
cd /opt/freelance-ai-helper
chmod +x deploy/setup_vps.sh
./deploy/setup_vps.sh
```

### 2. Заповнення `.env`
Переконайся, що файл `/opt/freelance-ai-helper/.env` містить валідні токени:
```bash
nano /opt/freelance-ai-helper/.env
```

### 3. Налаштування та запуск системної служби

```bash
# Скопіювати systemd unit-файл
sudo cp deploy/freelance-helper.service /etc/systemd/system/

# Перезавантажити конфігурацію systemd
sudo systemctl daemon-reload

# Увімкнути автозапуск при завантаженні сервера і запустити бота
sudo systemctl enable --now freelance-helper

# Перевірити статус
sudo systemctl status freelance-helper

# Перегляд логів у реальному часі
journalctl -u freelance-helper -f
```

### 4. Налаштування Telegram Mini App з власним доменом (Nginx + SSL)

Вбудований веб-сервер Mini App автоматично запускається разом із ботом на порту `8088` (налаштовується через `WEB_APP_PORT`, ендпоінти: `/`, `/api/stats`, `/api/projects`, `/api/pipeline`).
Для роботи як Telegram Mini App потрібен HTTPS-домен:

1. Створіть DNS **A-запис** для вашого домену або субдомену (наприклад, `app.yourdomain.com`), спрямований на IP вашого VPS.
2. Скопіюйте конфігурацію Nginx:
   ```bash
   sudo cp deploy/nginx-webapp.conf /etc/nginx/sites-available/webapp.conf
   sudo sed -i 's/webapp.yourdomain.com/app.yourdomain.com/g' /etc/nginx/sites-available/webapp.conf
   sudo ln -s /etc/nginx/sites-available/webapp.conf /etc/nginx/sites-enabled/
   sudo nginx -t && sudo systemctl reload nginx
   ```
3. Отримайте безкоштовний SSL-сертифікат Let's Encrypt:
   ```bash
   sudo certbot --nginx -d app.yourdomain.com
   ```
4. Увімкніть кнопку Web App в `@BotFather`:
   `/setmenubutton` -> оберіть вашого бота -> вкажіть назву кнопки (наприклад, `🚀 CRM App`) та URL: `https://app.yourdomain.com`.

---

## Як перевірити, що бот працює

### Локально

```bash
python -m compileall freelance_helper
./venv/bin/python scripts/check_project_logic.py
```

Команда `python -m freelance_helper.app.main` запускає реального polling-бота. Використовуй її тільки коли готовий перевіряти Telegram вручну.

### У Telegram

| Команда | Що перевіряє |
|---|---|
| `/start` | бот відповідає і показує `chat_id` |
| `/health` | токени, база, Freelancehunt API, Ollama, MIN_SCORE |
| `/check` | ручний пошук + статистика фільтрів |
| `/recent` | останні проєкти з бази |
| `/last` | те саме, що `/recent` |
| `/test_ai` | тест Ollama |
| `/settings` | мінімальний score |
| `/stats` | статистика оцінок |

---

## Команди бота

| Команда | Опис |
|---|---|
| `/start` | запуск бота і показ chat_id |
| `/help` | список команд |
| `/health` | діагностика: токени, SQLite, Freelancehunt API, MIN_SCORE |
| `/check` | перевірити проєкти вручну + статистика |
| `/auto_on` | увімкнути автопошук у поточному чаті |
| `/auto_off` | вимкнути автопошук у поточному чаті |
| `/stats` | статистика оцінок і налаштувань |
| `/settings` | показати мінімальний score |
| `/settings 35` | змінити мінімальний score |
| `/threshold 35` | те саме, що `/settings 35` |
| `/skills` (або `/filter`) | налаштувати спеціалізацію та фільтр категорій замовлень (Боти, Парсинг, Web, Backend, Mobile, DevOps) |
| `/profile` | показати профіль виконавця |
| `/profile_set текст` | змінити профіль виконавця |
| `/portfolio` | показати налаштовані посилання на портфоліо за категоріями |
| `/portfolio_set <категорія> <посилання>` | встановити посилання під категорію (bot, parsing, backend, web, mobile, devops, excel, general) |
| `/cases` | перегляд бази реальних кейсів для ставок |
| `/case_add <кат> <назва> \| <url> \| <опис>` | додати кейс у портфоліо |
| `/case_del <id>` | видалити кейс із бази |
| `/income` (або `/crm`) | воронка заявок, конверсія (Win Rate) та фінансова аналітика |
| `/export` | експорт усієї CRM-воронки та фінансової історії у файл CSV для Excel |
| `/quiet` | налаштування тихих годин для нічного режиму без звуку |
| `/digest` | ранковий звіт найкращих нічних проєктів |
| `/backup` | миттєве створення та відправка бекапу бази SQLite у чат |
| `/webapp` | інформація про інтерактивний Telegram Mini App інтерфейс |
| `/test_ai` | швидкий тест аналізатора на тестовому проєкті |
| `/recent` | останні проєкти з бази (sent/skipped) |
| `/last` | alias для `/recent` |
| `/why project_id` | збережений аналіз проєкту за ID |
| `/ref` (або `/referral`) | партнерська програма (+3 дні підписки за кожного запрошеного) |
| `/hot` | топ-3 гарячих замовлення прямо в чат (антиспам кулдаун у групах: 10 хв) |
| `/share` | поділитися рекомендацією бота в чатах фрілансерів зі своїм реферальним посиланням |
| `/market` | пульс біржі Freelancehunt (аналітика активності, угод та Score) з кнопкою репосту |
| `/feedback` (або `/idea`, `/suggest`) | надіслати ідею/побажання або повідомити про помилку розробнику |
| `/subscribe` (або `/sub`) | оформити місячну підписку на бота (30 днів) |
| `/subscription` | перевірити поточний статус своєї підписки та дні |
| `/grant_sub <user_id> [днів]` | *(тільки адмін)* вручну видати підписку користувачу |
| `/subscribers` | *(тільки адмін)* список усіх активних підписників |
| `/set_price <сума>` | *(тільки адмін)* змінити щомісячну вартість підписки (у грн) |
| `/set_channel <@channel>` | *(тільки адмін)* налаштувати трансляцію гарячих замовлень у публічний Telegram-канал |
| `/channel_off` | *(тільки адмін)* вимкнути трансляцію в публічний Telegram-канал |

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

Після змін додавай у коміт лише потрібні файли (без `.env`, `data/`, `logs/`, `venv/`):

```bash
git status
git add README.md requirements.txt .env.example .gitignore Dockerfile docker-compose.yml
git add freelance_helper/app/main.py
git add freelance_helper/app/telegram_bot.py
git add freelance_helper/app/bot/handlers.py
git add freelance_helper/app/bot/keyboards.py
git add freelance_helper/app/ai_analyzer.py
git add freelance_helper/app/config.py
git add freelance_helper/app/database.py
git add freelance_helper/app/freelancehunt_api.py
git add freelance_helper/app/services/project_service.py
git add freelance_helper/app/rules.py
git add freelance_helper/app/web_server.py
git add freelance_helper/web_app/index.html
git add scripts/check_project_logic.py
git commit -m "Implement full upgrade suite"
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
