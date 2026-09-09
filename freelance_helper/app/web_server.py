import asyncio
from pathlib import Path
from aiohttp import web

from .config import MIN_SCORE, PROJECT_ROOT
from .database import (
    get_crm_stats,
    get_recent_projects,
    get_setting,
    update_project_pipeline,
)
from .logger import logger

WEB_APP_DIR = PROJECT_ROOT / "freelance_helper" / "web_app"


async def handle_index(request: web.Request) -> web.Response:
    index_file = WEB_APP_DIR / "index.html"
    if not index_file.is_file():
        return web.Response(text="Mini App index.html not found", status=404)
    return web.FileResponse(index_file)


async def handle_stats(request: web.Request) -> web.Response:
    try:
        stats = get_crm_stats()
        return web.json_response({"success": True, "stats": stats})
    except Exception as e:
        logger.error("API stats error: %s", e)
        return web.json_response({"success": False, "error": str(e)}, status=500)


async def handle_projects(request: web.Request) -> web.Response:
    try:
        projects = get_recent_projects(limit=25)
        # Filter for sent/relevant projects
        sent_projects = [p for p in projects if p.get("status") == "sent" or p.get("pipeline_status") not in (None, "new")]
        return web.json_response({
            "success": True,
            "projects": sent_projects or projects[:10],
        })
    except Exception as e:
        logger.error("API projects error: %s", e)
        return web.json_response({"success": False, "error": str(e)}, status=500)


async def handle_update_pipeline(request: web.Request) -> web.Response:
    try:
        data = await request.json()
        project_id = str(data.get("project_id", ""))
        status = str(data.get("status", ""))
        deal_amount = float(data.get("deal_amount")) if data.get("deal_amount") is not None else None
        currency = str(data.get("currency", "UAH"))

        if not project_id or not status:
            return web.json_response({"success": False, "error": "Missing project_id or status"}, status=400)

        ok = update_project_pipeline(project_id, status, deal_amount=deal_amount, currency=currency)
        return web.json_response({"success": ok})
    except Exception as e:
        logger.error("API pipeline update error: %s", e)
        return web.json_response({"success": False, "error": str(e)}, status=500)


def create_web_app() -> web.Application:
    app = web.Application()
    app.router.add_get("/", handle_index)
    app.router.add_get("/api/stats", handle_stats)
    app.router.add_get("/api/projects", handle_projects)
    app.router.add_post("/api/pipeline", handle_update_pipeline)

    # Allow CORS so Mini App can call API from any client
    @web.middleware
    async def cors_middleware(request, handler):
        if request.method == "OPTIONS":
            response = web.Response(status=204)
        else:
            response = await handler(request)
        response.headers["Access-Control-Allow-Origin"] = "*"
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type"
        return response

    app.middlewares.append(cors_middleware)
    return app


async def start_background_web_server(host: str = "0.0.0.0", port: int = 8080) -> web.AppRunner | None:
    try:
        app = create_web_app()
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, host, port)
        await site.start()
        logger.info("Mini App Web Server started on http://%s:%s", host, port)
        return runner
    except Exception as exc:
        logger.warning("Could not start background web server on %s:%s: %s", host, port, exc)
        return None
