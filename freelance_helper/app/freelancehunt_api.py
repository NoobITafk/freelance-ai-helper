import requests

from app.config import FREELANCEHUNT_TOKEN


API_URL = "https://api.freelancehunt.com/v2/projects"


def get_projects():
    if not FREELANCEHUNT_TOKEN:
        raise ValueError("FREELANCEHUNT_TOKEN не знайдено в .env")

    headers = {
        "Authorization": f"Bearer {FREELANCEHUNT_TOKEN}",
        "Accept": "application/json",
    }

    response = requests.get(API_URL, headers=headers, timeout=20)
    response.raise_for_status()

    data = response.json()
    return data.get("data", [])