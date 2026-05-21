import os
from dotenv import load_dotenv

load_dotenv()


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
MAX_BIDS_COUNT = env_int("MAX_BIDS_COUNT", 40)
ANALYZE_MAYBE_PROJECTS = env_bool("ANALYZE_MAYBE_PROJECTS", True)
USER_PROFILE = os.getenv(
    "USER_PROFILE",
    (
        "Я студент 2 курсу інженерії програмного забезпечення. "
        "Вчуся програмувати, можу vibe-code з AI, розбиратися в чужому коді, "
        "робити невеликі Python-скрипти, Telegram-ботів, API, парсинг, "
        "простий frontend і бази даних. Потрібно чесно оцінювати ризики "
        "для junior-рівня і не радити брати задачі, де потрібен сильний senior."
    ),
)
FREELANCEHUNT_TOKEN = os.getenv("FREELANCEHUNT_TOKEN")
