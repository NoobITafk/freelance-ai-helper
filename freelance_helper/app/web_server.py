import html
import json
import time
from datetime import datetime
from pathlib import Path
from aiohttp import web

from .ai_analyzer import generate_bid, generate_questions, project_type
from .config import (
    MIN_SCORE,
    PAYMENT_PROVIDER_TOKEN,
    PROJECT_ROOT,
    SUBSCRIPTION_MONTH_PRICE,
    SUBSCRIPTION_STARS_PRICE,
    TELEGRAM_CHAT_ID,
)
from .database import (
    ALL_SKILL_CODES,
    SKILL_LABELS,
    add_bonus_days,
    add_feedback,
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
    get_user_skills,
    get_user_subscription,
    init_user_subscription,
    is_user_subscribed,
    set_user_skills,
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
        user_id = request.query.get("user_id")
        stats = get_crm_stats(user_id=user_id)
        return web.json_response({"success": True, "stats": stats})
    except Exception as e:
        logger.error("API stats error: %s", e)
        return web.json_response({"success": False, "error": str(e)}, status=500)


async def handle_projects(request: web.Request) -> web.Response:
    try:
        user_id = request.query.get("user_id")
        tab = request.query.get("tab", "feed").lower()
        limit = int(request.query.get("limit", 50))

        if tab == "crm":
            projects = get_crm_projects(limit=limit, user_id=user_id)
        else:
            projects = get_feed_projects(limit=limit, user_id=user_id)

        for p in projects:
            p["project_type"] = project_type(p)
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
        user_id = str(data.get("user_id") or request.query.get("user_id") or "").strip() or None
        project_id = str(data.get("project_id", "")).strip()
        status = str(data.get("status", "")).strip()
        deal_amount = float(data.get("deal_amount")) if data.get("deal_amount") is not None else None
        currency = str(data.get("currency", "UAH")).strip()

        if not project_id or not status:
            return web.json_response({"success": False, "error": "Missing project_id or status"}, status=400)

        ok = update_project_pipeline(project_id, status, deal_amount=deal_amount, currency=currency, user_id=user_id)
        stats = get_crm_stats(user_id=user_id)
        return web.json_response({"success": ok, "stats": stats})
    except Exception as e:
        logger.error("API pipeline update error: %s", e)
        return web.json_response({"success": False, "error": str(e)}, status=500)


async def handle_cases(request: web.Request) -> web.Response:
    try:
        user_id = request.query.get("user_id")
        cat = request.query.get("category")
        cases = get_portfolio_cases(cat, user_id=user_id)
        return web.json_response({"success": True, "cases": cases})
    except Exception as e:
        logger.error("API cases error: %s", e)
        return web.json_response({"success": False, "error": str(e)}, status=500)


async def handle_add_case(request: web.Request) -> web.Response:
    try:
        data = await request.json()
        user_id = str(data.get("user_id") or request.query.get("user_id") or "").strip() or None
        cat = str(data.get("category", "general")).strip().lower()
        title = str(data.get("title", "")).strip()
        desc = str(data.get("description", "")).strip()
        url = str(data.get("url", "")).strip()

        if not title:
            return web.json_response({"success": False, "error": "Title is required"}, status=400)

        case_id = add_portfolio_case(category=cat, title=title, description=desc, url=url, user_id=user_id)
        return web.json_response({"success": True, "id": case_id})
    except Exception as e:
        logger.error("API add case error: %s", e)
        return web.json_response({"success": False, "error": str(e)}, status=500)


async def handle_delete_case(request: web.Request) -> web.Response:
    try:
        user_id = request.query.get("user_id")
        if not user_id:
            return web.json_response({"success": False, "error": "user_id is required"}, status=400)
        case_id = int(request.match_info.get("id", 0))
        ok = delete_portfolio_case(case_id, user_id=user_id)
        return web.json_response({"success": ok})
    except Exception as e:
        logger.error("API delete case error: %s", e)
        return web.json_response({"success": False, "error": str(e)}, status=500)


async def handle_add_feedback(request: web.Request) -> web.Response:
    try:
        try:
            data = await request.json()
        except Exception:
            try:
                raw_bytes = await request.read()
                data = json.loads(raw_bytes.decode("utf-8")) if raw_bytes else {}
            except Exception:
                data = {}

        text = str(data.get("text", "")).strip()
        user_id = str(data.get("user_id") or request.query.get("user_id") or "").strip()
        username = str(data.get("username", "")).strip()
        full_name = str(data.get("full_name", "")).strip()

        if not text:
            return web.json_response({"success": False, "error": "Текст пропозиції обов'язковий"}, status=400)
        if len(text) > 2000:
            return web.json_response({"success": False, "error": "Текст занадто довгий (макс 2000 симв.)"}, status=400)

        fid = add_feedback(user_id=user_id or "anonymous", text=text, username=username, full_name=full_name)

        bot = request.app.get("bot")
        if bot and TELEGRAM_CHAT_ID:
            try:
                user_label = f"@{username}" if username else (full_name or f"ID: {user_id}")
                admin_msg = (
                    f"💡 <b>Нова пропозиція / відгук від користувача!</b>\n\n"
                    f"👤 Від: <b>{html.escape(user_label)}</b> (<code>{user_id}</code>)\n\n"
                    f"📝 <i>{html.escape(text)}</i>"
                )
                await bot.send_message(chat_id=int(TELEGRAM_CHAT_ID), text=admin_msg, parse_mode="HTML")
            except Exception as notify_err:
                logger.debug("Failed notifying admin about feedback: %s", notify_err)

        return web.json_response({"success": True, "id": fid})
    except Exception as e:
        logger.error("API feedback error: %s", e)
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
        user_id = request.query.get("user_id")
        if not user_id:
            return web.json_response({"success": False, "error": "user_id is required for export"}, status=400)
        csv_text = export_crm_data_csv(user_id=user_id)
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


async def handle_subscription_status(request: web.Request) -> web.Response:
    try:
        user_id = request.query.get("user_id")
        if not user_id:
            user_id = TELEGRAM_CHAT_ID or ""

        sub = get_user_subscription(user_id) if user_id else None
        if not sub and user_id:
            if str(user_id) == str(TELEGRAM_CHAT_ID or ""):
                init_user_subscription(user_id, chat_id=user_id, status="lifetime")
            else:
                init_user_subscription(user_id, chat_id=user_id, status="trial")
            sub = get_user_subscription(user_id)

        price_uah = int(get_setting("sub_price", str(SUBSCRIPTION_MONTH_PRICE)))
        stars_price = int(get_setting("sub_stars_price", str(SUBSCRIPTION_STARS_PRICE)))
        use_stars = not bool(PAYMENT_PROVIDER_TOKEN)
        return web.json_response({
            "success": True,
            "subscription": sub,
            "price": stars_price if use_stars else price_uah,
            "currency": "XTR" if use_stars else "UAH",
            "price_uah": price_uah,
            "price_stars": stars_price,
            "is_stars": use_stars,
        })
    except Exception as e:
        logger.error("API subscription error: %s", e)
        return web.json_response({"success": False, "error": str(e)}, status=500)


async def handle_create_invoice(request: web.Request) -> web.Response:
    try:
        data = await request.json() if request.can_read_body else {}
        user_id = str(data.get("user_id") or request.query.get("user_id") or "").strip()
        if not user_id:
            user_id = str(TELEGRAM_CHAT_ID or "")

        bot = request.app.get("bot")
        if not bot:
            import os
            bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "")
            if bot_token:
                from telegram import Bot
                bot = Bot(token=bot_token)

        if not bot:
            return web.json_response({"success": False, "error": "Bot instance not available"}, status=503)

        from telegram import LabeledPrice
        price_uah = int(get_setting("sub_price", str(SUBSCRIPTION_MONTH_PRICE)))
        stars_price = int(get_setting("sub_stars_price", str(SUBSCRIPTION_STARS_PRICE)))

        if PAYMENT_PROVIDER_TOKEN:
            link = await bot.create_invoice_link(
                title="Підписка Freelance AI Helper (1 місяць)",
                description="30 днів повного доступу до AI-генерації відгуків, моніторингу та CRM.",
                payload=f"sub_month_{user_id}",
                provider_token=PAYMENT_PROVIDER_TOKEN,
                currency="UAH",
                prices=[LabeledPrice(label="Підписка на 1 місяць", amount=price_uah * 100)],
            )
            return web.json_response({
                "success": True,
                "invoice_link": link,
                "currency": "UAH",
                "price": price_uah,
            })
        else:
            link = await bot.create_invoice_link(
                title="Підписка Freelance AI Helper (1 місяць)",
                description="30 днів повного доступу до AI-генерації відгуків, моніторингу та CRM.",
                payload=f"sub_month_{user_id}",
                provider_token="",
                currency="XTR",
                prices=[LabeledPrice(label="Підписка на 1 місяць", amount=stars_price)],
            )
            return web.json_response({
                "success": True,
                "invoice_link": link,
                "currency": "XTR",
                "price": stars_price,
            })
    except Exception as e:
        logger.error("API create invoice error: %s", e)
        return web.json_response({"success": False, "error": str(e)}, status=500)


async def handle_get_skills(request: web.Request) -> web.Response:
    try:
        user_id = request.query.get("user_id") or TELEGRAM_CHAT_ID or "default"
        skills = get_user_skills(user_id)
        available = [{"code": code, "label": SKILL_LABELS.get(code, code)} for code in ALL_SKILL_CODES]
        return web.json_response({
            "success": True,
            "skills": skills,
            "available": available,
        })
    except Exception as e:
        logger.error("API get skills error: %s", e)
        return web.json_response({"success": False, "error": str(e)}, status=500)


async def handle_update_skills(request: web.Request) -> web.Response:
    try:
        data = await request.json()
        user_id = str(data.get("user_id") or request.query.get("user_id") or TELEGRAM_CHAT_ID or "").strip()
        skills = data.get("skills", [])
        if not isinstance(skills, list):
            return web.json_response({"success": False, "error": "skills must be an array"}, status=400)
        set_user_skills(user_id, skills)
        return web.json_response({
            "success": True,
            "skills": get_user_skills(user_id),
        })
    except Exception as e:
        logger.error("API update skills error: %s", e)
        return web.json_response({"success": False, "error": str(e)}, status=500)


def create_web_app(bot=None) -> web.Application:
    app = web.Application()
    app["bot"] = bot
    app.router.add_get("/", handle_index)
    app.router.add_get("/api/stats", handle_stats)
    app.router.add_get("/api/projects", handle_projects)
    app.router.add_get("/api/skills", handle_get_skills)
    app.router.add_post("/api/skills", handle_update_skills)
    app.router.add_post("/api/pipeline", handle_update_pipeline)
    app.router.add_get("/api/cases", handle_cases)
    app.router.add_post("/api/cases", handle_add_case)
    app.router.add_delete("/api/cases/{id}", handle_delete_case)
    app.router.add_get("/api/health", handle_health)
    app.router.add_get("/api/export", handle_export_csv)
    app.router.add_get("/api/subscription", handle_subscription_status)
    app.router.add_post("/api/create_invoice", handle_create_invoice)
    app.router.add_post("/api/feedback", handle_add_feedback)

    ip_request_counts = {}

    @web.middleware
    async def security_and_rate_limit_middleware(request, handler):
        if request.method == "OPTIONS":
            response = web.Response(status=204)
            response.headers["Access-Control-Allow-Origin"] = "*"
            response.headers["Access-Control-Allow-Methods"] = "GET, POST, DELETE, OPTIONS"
            response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization, X-Requested-With"
            return response

        # Anti-DDoS Rate limiting for API requests (max 120 req / 60s per IP)
        if request.path.startswith("/api/"):
            peername = request.transport.get_extra_info("peername") if request.transport else None
            client_ip = request.headers.get("X-Forwarded-For", "").split(",")[0].strip() or (peername[0] if peername else "127.0.0.1")

            now = time.time()
            if len(ip_request_counts) > 2000:
                expired = [ip for ip, timestamps in ip_request_counts.items() if not timestamps or now - timestamps[-1] > 120]
                for exp_ip in expired:
                    ip_request_counts.pop(exp_ip, None)

            records = ip_request_counts.get(client_ip, [])
            records = [ts for ts in records if now - ts < 60.0]

            if len(records) >= 120:
                logger.warning("API rate limit exceeded for IP %s on %s", client_ip, request.path)
                return web.json_response(
                    {"success": False, "error": "Забагато запитів. Спробуйте пізніше."},
                    status=429,
                    headers={"Retry-After": "60"},
                )

            records.append(now)
            ip_request_counts[client_ip] = records

        response = await handler(request)

        # Security Headers & CORS
        response.headers["Access-Control-Allow-Origin"] = "*"
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, DELETE, OPTIONS"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization, X-Requested-With"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        return response

    app.middlewares.append(security_and_rate_limit_middleware)
    return app


async def start_background_web_server(host: str = "0.0.0.0", port: int = 8088, bot=None) -> web.AppRunner | None:
    try:
        app = create_web_app(bot=bot)
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, host, port)
        await site.start()
        logger.info("Mini App Web Server started on http://%s:%s", host, port)
        return runner
    except Exception as exc:
        logger.warning("Could not start background web server on %s:%s: %s", host, port, exc)
        return None
