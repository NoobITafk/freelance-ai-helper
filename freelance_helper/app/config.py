import os
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:7b")
FREELANCEHUNT_TOKEN = os.getenv("FREELANCEHUNT_TOKEN")