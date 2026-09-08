import httpx

from .config import FREELANCEHUNT_TOKEN
from .logger import logger

API_URL = "https://api.freelancehunt.com/v2/projects"


class FreelancehuntAPIError(RuntimeError):
    pass


_client: httpx.AsyncClient | None = None


async def get_http_client(timeout: float = 20.0) -> httpx.AsyncClient:
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(timeout=timeout)
    return _client


async def close_http_client() -> None:
    global _client
    if _client is not None and not _client.is_closed:
        await _client.aclose()
        _client = None


async def get_projects(timeout: float = 20.0) -> list[dict]:
    if not FREELANCEHUNT_TOKEN:
        logger.error("Freelancehunt API: FREELANCEHUNT_TOKEN missing in .env")
        raise FreelancehuntAPIError(
            "FREELANCEHUNT_TOKEN не знайдено в .env (перевір назву змінної)"
        )

    headers = {
        "Authorization": f"Bearer {FREELANCEHUNT_TOKEN}",
        "Accept": "application/json",
    }
    params = {"page[size]": 50}

    client = await get_http_client(timeout=timeout)
    try:
        response = await client.get(API_URL, headers=headers, params=params)
    except httpx.RequestError as error:
        await close_http_client()
        logger.exception("Freelancehunt API request failed")
        raise FreelancehuntAPIError(
            f"Не вдалося підключитися до Freelancehunt API: {error}"
        ) from error

    if response.status_code == 429:
        logger.warning("Freelancehunt API rate limit exceeded (HTTP 429)")
        raise FreelancehuntAPIError("Freelancehunt API ліміт запитів вичерпано (HTTP 429). Зачекайте хвилину.")

    if not response.is_success:
        error_text = response.text[:300].replace("\n", " ").strip()
        logger.error(
            "Freelancehunt API HTTP error | status=%s | body=%s",
            response.status_code,
            error_text,
        )
        raise FreelancehuntAPIError(
            f"Freelancehunt API HTTP {response.status_code}: "
            f"{error_text or 'без тексту помилки'}"
        )

    try:
        data = response.json()
    except ValueError as error:
        logger.error(
            "Freelancehunt API invalid JSON | status=%s | body=%s",
            response.status_code,
            response.text[:300].replace("\n", " ").strip(),
        )
        raise FreelancehuntAPIError("Freelancehunt API повернув невалідний JSON") from error

    if "data" not in data:
        logger.error(
            "Freelancehunt API JSON has no data field | keys=%s",
            sorted(data.keys()),
        )
        raise FreelancehuntAPIError("Freelancehunt API повернув JSON без поля data")

    if not isinstance(data["data"], list):
        logger.error("Freelancehunt API data field is not a list")
        raise FreelancehuntAPIError("Freelancehunt API повернув поле data не як список")

    projects = data["data"]
    logger.info("Freelancehunt API: received %s projects", len(projects))
    return projects
