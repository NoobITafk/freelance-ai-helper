import re
from datetime import datetime
from pathlib import Path
from aiohttp import web

from .ai_analyzer import (
    calculate_score,
    extract_project_insights,
    generate_bid,
    generate_questions,
    is_technical_project,
    project_type,
)
from .config import MIN_SCORE, PROJECT_ROOT
from .database import (
    add_portfolio_case,
    check_database,
    delete_portfolio_case,
    export_crm_data_csv,
    get_crm_projects,
    get_crm_stats,
    get_feed_projects,
    get_portfolio_cases,
    get_project,
    get_recent_projects,
    get_setting,
    update_project_pipeline,
)
from .logger import logger
from .rules import classify_project, count_good_keyword_matches, parse_budget_info
from .services.project_service import calculate_sweet_spot

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
        tab = request.query.get("tab", "feed").lower()
        limit = int(request.query.get("limit", 50))

        if tab == "crm":
            projects = get_crm_projects(limit=limit)
        else:
            projects = get_feed_projects(limit=limit)

        for p in projects:
            try:
                p["bid_text"] = generate_bid(p, variant="short")
            except Exception:
                p["bid_text"] = f"Вітаю! Ознайомився із завданням «{p.get('title', '')}» та готовий реалізувати якісно."
            try:
                p["questions"] = generate_questions(p)
            except Exception:
                p["questions"] = ""
            if not p.get("url"):
                p["url"] = f"https://freelancehunt.com/project/{p.get('project_id')}.html"

        return web.json_response({
            "success": True,
            "tab": tab,
            "count": len(projects),
            "projects": projects,
        })
    except Exception as e:
        logger.error("API projects error: %s", e)
        return web.json_response({"success": False, "error": str(e)}, status=500)


async def handle_update_pipeline(request: web.Request) -> web.Response:
    try:
        data = await request.json()
        project_id = str(data.get("project_id", "")).strip()
        status = str(data.get("status", "")).strip()
        deal_amount = float(data.get("deal_amount")) if data.get("deal_amount") is not None else None
        currency = str(data.get("currency", "UAH")).strip()

        if not project_id or not status:
            return web.json_response({"success": False, "error": "Missing project_id or status"}, status=400)

        ok = update_project_pipeline(project_id, status, deal_amount=deal_amount, currency=currency)
        stats = get_crm_stats()
        return web.json_response({"success": ok, "stats": stats})
    except Exception as e:
        logger.error("API pipeline update error: %s", e)
        return web.json_response({"success": False, "error": str(e)}, status=500)


async def handle_cases(request: web.Request) -> web.Response:
    try:
        cat = request.query.get("category")
        cases = get_portfolio_cases(cat)
        return web.json_response({"success": True, "cases": cases})
    except Exception as e:
        logger.error("API cases error: %s", e)
        return web.json_response({"success": False, "error": str(e)}, status=500)


async def handle_add_case(request: web.Request) -> web.Response:
    try:
        data = await request.json()
        cat = str(data.get("category", "general")).strip().lower()
        title = str(data.get("title", "")).strip()
        desc = str(data.get("description", "")).strip()
        url = str(data.get("url", "")).strip()

        if not title:
            return web.json_response({"success": False, "error": "Title is required"}, status=400)

        case_id = add_portfolio_case(category=cat, title=title, description=desc, url=url)
        return web.json_response({"success": True, "id": case_id})
    except Exception as e:
        logger.error("API add case error: %s", e)
        return web.json_response({"success": False, "error": str(e)}, status=500)


async def handle_delete_case(request: web.Request) -> web.Response:
    try:
        case_id = int(request.match_info.get("id", 0))
        ok = delete_portfolio_case(case_id)
        return web.json_response({"success": ok})
    except Exception as e:
        logger.error("API delete case error: %s", e)
        return web.json_response({"success": False, "error": str(e)}, status=500)


async def handle_health(request: web.Request) -> web.Response:
    try:
        db_ok, db_msg = check_database()
        quiet_hours = get_setting("quiet_hours", "23:00 - 08:00")
        min_score = get_setting("min_score", str(MIN_SCORE))
        stats = get_crm_stats()
        return web.json_response({
            "success": True,
            "database": db_msg if db_ok else f"Помилка: {db_msg}",
            "quiet_hours": quiet_hours,
            "min_score": min_score,
            "stats": stats,
            "status": "online",
        })
    except Exception as e:
        logger.error("API health error: %s", e)
        return web.json_response({"success": False, "error": str(e)}, status=500)


async def handle_export_csv(request: web.Request) -> web.Response:
    try:
        csv_text = export_crm_data_csv()
        filename = f"crm_export_{datetime.now().strftime('%Y%m%d_%H%M')}.csv"
        return web.Response(
            text=csv_text,
            content_type="text/csv",
            charset="utf-8",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
                "Access-Control-Allow-Origin": "*",
            },
        )
    except Exception as e:
        logger.error("API export error: %s", e)
        return web.Response(text=f"Export error: {e}", status=500)


async def handle_userscript(request: web.Request) -> web.Response:
    script_file = WEB_APP_DIR / "freelancehunt_helper.user.js"
    if not script_file.is_file():
        return web.Response(text="// Userscript not found", status=404, content_type="application/javascript")
    content = script_file.read_text(encoding="utf-8")
    headers = {
        "Cache-Control": "no-cache, must-revalidate",
        "Access-Control-Allow-Origin": "*",
    }
    if request.query.get("download") in ("1", "true"):
        headers["Content-Disposition"] = 'attachment; filename="freelancehunt_helper.user.js"'
    return web.Response(
        text=content,
        content_type="application/javascript",
        charset="utf-8",
        headers=headers,
    )


async def handle_bid_draft(request: web.Request) -> web.Response:
    try:
        data = {}
        if request.method == "POST":
            try:
                data = await request.json()
            except Exception:
                data = {}

        project_id = request.query.get("project_id") or data.get("project_id", "")
        project_id = str(project_id).strip()

        project = None
        if project_id:
            project = get_project(project_id)

        if not project:
            title = request.query.get("title") or data.get("title", "")
            description = request.query.get("description") or data.get("description", "")
            budget = request.query.get("budget") or data.get("budget", "")
            bids_count = request.query.get("bids_count") or data.get("bids_count", 0)
            url = request.query.get("url") or data.get("url", "")
            try:
                bids_count = int(bids_count)
            except (ValueError, TypeError):
                bids_count = 0

            project = {
                "project_id": project_id or "temp",
                "title": title,
                "description": description,
                "budget": budget,
                "bids_count": bids_count,
                "url": url,
            }
            full_text = f"{title} {description}"
            filter_res = classify_project(title, description)
            is_tech = is_technical_project(project)
            good_matches = count_good_keyword_matches(title, description)
            score = 65 if is_tech else 20
            if filter_res.category == "good":
                score += 10
            if good_matches:
                score += min(len(good_matches) * 5, 20)
            project["score"] = min(score, 99)
            project["reason"] = filter_res.reason or (f"Категорія: {filter_res.category}" if is_tech else "Не відповідає профілю")
            project["pipeline_status"] = "new"

        try:
            bid_short = generate_bid(project, variant="short")
        except Exception:
            bid_short = f"Вітаю! Ознайомився із завданням «{project.get('title', '')}» та готовий якісно реалізувати."

        try:
            bid_full = generate_bid(project, variant="full")
        except Exception:
            bid_full = bid_short

        try:
            questions = generate_questions(project)
        except Exception:
            questions = ""

        budget_info = parse_budget_info(project.get("budget"))
        amount, currency, _ = budget_info
        bids_cnt = int(project.get("bids_count") or 0)
        sweet_spot = calculate_sweet_spot(budget_info, bids_cnt)

        rec_days = 2
        try:
            insights = extract_project_insights(project)
            time_est = insights.get("time_estimate", "1-2 дні")
            days_match = re.findall(r"\d+", time_est)
            if days_match:
                rec_days = int(days_match[-1])
        except Exception:
            rec_days = 2

        rec_amount = amount if amount else None
        if amount and bids_cnt > 10:
            rec_amount = int(amount * 0.95 / 50) * 50

        return web.json_response({
            "success": True,
            "project_id": project.get("project_id"),
            "title": project.get("title"),
            "score": project.get("score", 70),
            "reason": project.get("reason", ""),
            "pipeline_status": project.get("pipeline_status", "new"),
            "recommended_amount": rec_amount,
            "recommended_currency": currency or "UAH",
            "recommended_days": rec_days,
            "sweet_spot": sweet_spot or (f"{amount} {currency}" if amount else "За домовленістю"),
            "bid_short": bid_short,
            "bid_full": bid_full,
            "questions": questions,
        })
    except Exception as e:
        logger.error("API bid draft error: %s", e)
        return web.json_response({"success": False, "error": str(e)}, status=500)


def create_web_app() -> web.Application:
    app = web.Application()
    app.router.add_get("/", handle_index)
    app.router.add_get("/freelancehunt_helper.user.js", handle_userscript)
    app.router.add_get("/api/bid_draft", handle_bid_draft)
    app.router.add_post("/api/bid_draft", handle_bid_draft)
    app.router.add_get("/api/stats", handle_stats)
    app.router.add_get("/api/projects", handle_projects)
    app.router.add_post("/api/pipeline", handle_update_pipeline)
    app.router.add_get("/api/cases", handle_cases)
    app.router.add_post("/api/cases", handle_add_case)
    app.router.add_delete("/api/cases/{id}", handle_delete_case)
    app.router.add_get("/api/health", handle_health)
    app.router.add_get("/api/export", handle_export_csv)

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


async def start_background_web_server(host: str = "0.0.0.0", port: int = 8088) -> web.AppRunner | None:
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
