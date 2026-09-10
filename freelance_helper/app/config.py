import os
from pathlib import Path

from dotenv import load_dotenv

# Корінь репозиторію: freelance_helper/app/config.py -> .. -> ..
PROJECT_ROOT = Path(__file__).resolve().parents[2]

for env_path in (PROJECT_ROOT / ".env", PROJECT_ROOT / "freelance_helper" / ".env"):
    if env_path.is_file():
        load_dotenv(env_path)
        break
else:
    load_dotenv()

# Сумісність: старе ім'я змінної (не використовуй у нових .env)
if not os.getenv("FREELANCEHUNT_TOKEN") and os.getenv("FREELANCEHUNT_API_TOKEN"):
    os.environ["FREELANCEHUNT_TOKEN"] = os.environ["FREELANCEHUNT_API_TOKEN"]


def env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)

    if value is None:
        return default

    return value.lower() in {"1", "true", "yes", "on", "так"}


def env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434/api/generate")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:3b")
AI_ANALYSIS_ENABLED = env_bool("AI_ANALYSIS_ENABLED", True)
AI_TIMEOUT_SECONDS = env_int("AI_TIMEOUT_SECONDS", 40)
AUTO_CHECK_INTERVAL_SECONDS = env_int("AUTO_CHECK_INTERVAL_SECONDS", 180)
AUTO_CHECK_FIRST_RUN_SECONDS = env_int("AUTO_CHECK_FIRST_RUN_SECONDS", 10)
MAX_BIDS_COUNT = env_int("MAX_BIDS_COUNT", 20)
MIN_SCORE = env_int("MIN_SCORE", 45)
HIGH_COMPETITION_BIDS = env_int("HIGH_COMPETITION_BIDS", 40)
ANALYZE_MAYBE_PROJECTS = env_bool("ANALYZE_MAYBE_PROJECTS", True)
USER_PROFILE = os.getenv(
    "USER_PROFILE",
    (
        "Можу виконувати невеликі Python-скрипти, Telegram-ботів, API-інтеграції, "
        "парсинг, HTML/CSS, WordPress-правки, Google Sheets/Excel автоматизацію "
        "і прості задачі з базами даних. Потрібно чесно оцінювати ризики "
        "і не радити брати задачі, де потрібна глибока вузька експертиза."
    ),
)
FREELANCEHUNT_TOKEN = os.getenv("FREELANCEHUNT_TOKEN")
SUBSCRIPTION_REQUIRED = env_bool("SUBSCRIPTION_REQUIRED", True)
SUBSCRIPTION_MONTH_PRICE = env_int("SUBSCRIPTION_MONTH_PRICE", 99)
SUBSCRIPTION_STARS_PRICE = env_int("SUBSCRIPTION_STARS_PRICE", 99)
TRIAL_DAYS = env_int("TRIAL_DAYS", 7)
PAYMENT_PROVIDER_TOKEN = os.getenv("PAYMENT_PROVIDER_TOKEN", "")
