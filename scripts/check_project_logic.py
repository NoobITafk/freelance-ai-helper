from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from freelance_helper.app.ai_analyzer import (
    fallback_bid,
    fallback_questions,
    is_technical_project,
    project_type,
)
from freelance_helper.app.rules import (
    budget_score_adjustment,
    build_rules_fallback_analysis,
    classify_project,
    count_good_keyword_matches,
    format_budget_display,
    keyword_in_text,
    parse_budget_info,
)
from freelance_helper.app.services.project_service import (
    format_project_message,
    protect_strong_technical_match,
)
from freelance_helper.app.database import get_connection, init_db
from freelance_helper.app.freelancehunt_api import close_http_client, get_http_client


@dataclass(frozen=True)
class Case:
    name: str
    project: dict
    expected_type: str
    expected_technical: bool


CASES = [
    Case(
        name="Telegram bot",
        project={
            "title": "Telegram-бот для прийому заявок",
            "description": "Потрібен Telegram-бот з командами, формою заявки, SQLite і адмін-командами.",
            "budget": "3000 грн",
            "bids_count": 5,
            "url": "https://example.com/telegram-bot",
        },
        expected_type="telegram_bot",
        expected_technical=True,
    ),
    Case(
        name="Parsing",
        project={
            "title": "Парсинг товарів з сайту в Excel",
            "description": "Потрібно зібрати назву, ціну, опис і посилання та зберегти результат в Excel.",
            "budget": "2500 грн",
            "bids_count": 8,
            "url": "https://example.com/parser",
        },
        expected_type="parsing",
        expected_technical=True,
    ),
    Case(
        name="WordPress",
        project={
            "title": "Правки WordPress-сайту",
            "description": "Потрібно виправити блоки на сторінці, адаптивність і форму зворотного зв'язку.",
            "budget": "2000 грн",
            "bids_count": 12,
            "url": "https://example.com/wordpress",
        },
        expected_type="wordpress",
        expected_technical=True,
    ),
    Case(
        name="Backend API",
        project={
            "title": "FastAPI backend для особистого кабінету",
            "description": "Потрібно зробити API, авторизацію, ролі користувачів, PostgreSQL і деплой.",
            "budget": "9000 грн",
            "bids_count": 7,
            "url": "https://example.com/backend-api",
        },
        expected_type="backend",
        expected_technical=True,
    ),
    Case(
        name="AI integration",
        project={
            "title": "Інтеграція ChatGPT в Telegram-бота",
            "description": "Потрібно підключити OpenAI API, налаштувати промпт і зберігати історію відповідей.",
            "budget": "7000 грн",
            "bids_count": 5,
            "url": "https://example.com/ai-bot",
        },
        expected_type="telegram_bot",
        expected_technical=True,
    ),
    Case(
        name="Frontend React",
        project={
            "title": "React dashboard по Figma",
            "description": "Потрібно зверстати dashboard, підключити API, зробити стани loading/error і адаптив.",
            "budget": "8000 грн",
            "bids_count": 9,
            "url": "https://example.com/react-dashboard",
        },
        expected_type="frontend",
        expected_technical=True,
    ),
    Case(
        name="Short React Django",
        project={
            "title": "Допрацювання проєкту react + django",
            "description": (
                "Допрацювання сайту для онлайн-школи, завдання на пару годин. "
                "Шукаю розробника зі стеком react + django"
            ),
            "budget": "1500 грн",
            "bids_count": 3,
            "url": "https://example.com/react-django",
        },
        expected_type="backend",
        expected_technical=True,
    ),
    Case(
        name="Next Supabase AI CRM",
        project={
            "title": "Доработка существующего Next.js/Supabase проекта: офферы, CRM, аналитика, AI-чат",
            "description": (
                "Стек проекта: Next.js / React, Supabase / PostgreSQL, Vercel, "
                "API integrations, CSV/JSON import, AI-чат / OpenAI API. "
                "Нужно доработать офферы, CRM-слой, аналитику и работать с существующим кодом."
            ),
            "budget": "Не вказано",
            "bids_count": 3,
            "url": "https://example.com/next-supabase-ai-crm",
        },
        expected_type="ai_integration",
        expected_technical=True,
    ),
    Case(
        name="HTML/CSS",
        project={
            "title": "Зверстати лендинг по Figma",
            "description": "Є макет у Figma, потрібно зробити HTML/CSS верстку з адаптивом і формою.",
            "budget": "4000 грн",
            "bids_count": 6,
            "url": "https://example.com/html-css",
        },
        expected_type="html_css",
        expected_technical=True,
    ),
    Case(
        name="Figma design only",
        project={
            "title": "Дизайн головної сторінки у Figma",
            "description": "Потрібно намалювати дизайн лендингу без верстки та програмування.",
            "budget": "2500 грн",
            "bids_count": 11,
            "url": "https://example.com/figma-design",
        },
        expected_type="non_technical",
        expected_technical=False,
    ),
    Case(
        name="Google Sheets",
        project={
            "title": "Автоматизація Google Sheets",
            "description": "Потрібно автоматично обробляти дані в таблиці і формувати звіт.",
            "budget": "1800 грн",
            "bids_count": 4,
            "url": "https://example.com/sheets",
        },
        expected_type="excel",
        expected_technical=True,
    ),
    Case(
        name="Excel data entry",
        project={
            "title": "Data entry в Excel",
            "description": "Потрібно вручну перенести дані з PDF у таблицю Excel.",
            "budget": "900 грн",
            "bids_count": 20,
            "url": "https://example.com/data-entry",
        },
        expected_type="non_technical",
        expected_technical=False,
    ),
    Case(
        name="Logo vectorization",
        project={
            "title": "Векторизація логотипу для друку на одязі",
            "description": "Потрібно перевести логотип у векторний формат для друку на футболках.",
            "budget": "1000 грн",
            "bids_count": 10,
            "url": "https://example.com/vector-logo",
        },
        expected_type="non_technical",
        expected_technical=False,
    ),
    Case(
        name="Translation",
        project={
            "title": "Переклад тексту українською",
            "description": "Потрібно перекласти документ з англійської на українську.",
            "budget": "700 грн",
            "bids_count": 15,
            "url": "https://example.com/translation",
        },
        expected_type="non_technical",
        expected_technical=False,
    ),
    Case(
        name="SEO without programming",
        project={
            "title": "SEO-просування WordPress-сайту",
            "description": "Потрібно підібрати ключові слова і зробити SEO-оптимізацію без зміни коду.",
            "budget": "3500 грн",
            "bids_count": 9,
            "url": "https://example.com/seo",
        },
        expected_type="non_technical",
        expected_technical=False,
    ),
    Case(
        name="SEO with code fixes",
        project={
            "title": "Технічні SEO-правки HTML",
            "description": "Потрібно виправити HTML-заголовки, schema markup і дрібні CSS-проблеми на сайті.",
            "budget": "3000 грн",
            "bids_count": 6,
            "url": "https://example.com/technical-seo",
        },
        expected_type="html_css",
        expected_technical=True,
    ),
]


def main() -> int:
    failed = 0
    total_checks = len(CASES) + 2

    for case in CASES:
        actual_type = project_type(case.project)
        actual_technical = is_technical_project(case.project)
        ok = (
            actual_type == case.expected_type
            and actual_technical == case.expected_technical
        )

        if not ok:
            failed += 1

        print("=" * 80)
        print(f"{case.name}: {'OK' if ok else 'FAIL'}")
        print(f"type: {actual_type} | expected: {case.expected_type}")
        print(f"technical: {actual_technical} | expected: {case.expected_technical}")
        print()
        print("fallback bid:")
        print(fallback_bid(case.project))
        print()
        print("questions:")
        print(fallback_questions(case.project))

    filter_result = classify_project(
        "Допрацювання проєкту react + django",
        "Шукаю розробника зі стеком react + django",
        "Python, django, javascript, React",
    )
    good_matches = count_good_keyword_matches(
        "Допрацювання проєкту react + django",
        "Шукаю розробника зі стеком react + django",
        "Python, django, javascript, React",
    )
    protected = protect_strong_technical_match(
        {
            "fit": "no",
            "summary": "Помилково відхилено",
            "difficulty": 3,
            "risk": 5,
            "success_chance": 60,
            "competition": "medium",
            "budget_ok": "yes",
            "should_apply": False,
            "reason": "AI помилився",
            "questions": [],
        },
        filter_result,
        good_matches,
    )
    if protected["fit"] != "partial" or not protected["should_apply"]:
        failed += 1
        print("=" * 80)
        print("Strong technical protection: FAIL")
        print(protected)
    else:
        print("=" * 80)
        print("Strong technical protection: OK")

    protected_fullstack = protect_strong_technical_match(
        {
            "fit": "no",
            "summary": "Складний full-stack проєкт",
            "difficulty": 7,
            "risk": 6,
            "success_chance": 40,
            "competition": "medium",
            "budget_ok": "unknown",
            "should_apply": False,
            "reason": "AI вважає ризик високим",
            "questions": [],
        },
        classify_project(
            "Next.js/Supabase CRM AI-чат",
            "Next.js React Supabase PostgreSQL OpenAI API CRM",
            "supabase react next.js postgresql",
        ),
        count_good_keyword_matches(
            "Next.js/Supabase CRM AI-чат",
            "Next.js React Supabase PostgreSQL OpenAI API CRM",
            "supabase react next.js postgresql",
        ),
    )
    if not protected_fullstack.get("manual_review"):
        failed += 1
        print("=" * 80)
        print("Full-stack technical protection: FAIL")
        print(protected_fullstack)
    else:
        print("=" * 80)
    total_checks += 1
    msg_project = {
        "title": "FastAPI backend для особистого кабінету",
        "description": "Потрібно зробити API, авторизацію, ролі користувачів, PostgreSQL і деплой.",
        "budget": "9000 грн",
        "bids_count": 7,
        "url": "https://example.com/backend-api",
    }
    msg_filter = classify_project(msg_project["title"], msg_project["description"])
    msg_matches = count_good_keyword_matches(msg_project["title"], msg_project["description"])
    msg_analysis = build_rules_fallback_analysis(
        msg_filter,
        msg_project["title"],
        msg_project["description"],
        7,
        msg_project["budget"],
    )
    formatted_msg = format_project_message(
        title=msg_project["title"],
        budget=msg_project["budget"],
        bids_count=msg_project["bids_count"],
        url=msg_project["url"],
        score=80,
        analysis_data=msg_analysis,
        filter_result=msg_filter,
        numeric_bids_count=7,
        good_matches=msg_matches,
        project_dict=msg_project,
    )
    msg_lines = [line for line in formatted_msg.split("\n") if line.strip()]
    if len(msg_lines) > 8 or len(formatted_msg) > 600 or "Fallback rules" in formatted_msg:
        failed += 1
        print("=" * 80)
        print("Concise message format: FAIL")
        print(f"Lines count: {len(msg_lines)}, total chars: {len(formatted_msg)}")
        print(formatted_msg)
    else:
        print("=" * 80)
        print("Concise message format: OK")
        print("Sample message output:")
        print(formatted_msg)

    # 1. Regex boundary precision test
    total_checks += 1
    regex_ok = (
        not keyword_in_text("скрипт", "дескриптор")
        and not keyword_in_text("текст", "контекстний аналіз")
        and keyword_in_text("скрипт", "потрібен python скрипт")
        and keyword_in_text("bot", "telegram-bot")
    )
    if not regex_ok:
        failed += 1
        print("=" * 80)
        print("Regex boundary precision: FAIL")
    else:
        print("=" * 80)
        print("Regex boundary precision: OK")

    # 2. Budget and currency evaluation test
    total_checks += 1
    b_dict = parse_budget_info({"amount": 5000, "currency": "UAH"})
    b_usd = parse_budget_info("$300")
    b_high = budget_score_adjustment("20 000 грн")
    b_tiny = budget_score_adjustment("200 грн")
    budget_ok_test = (
        b_dict == (5000, "UAH", 5000)
        and b_usd == (300, "USD", 12300)
        and b_high[1] == "yes"  # 20 000 грн is recognized as good budget!
        and b_tiny[0] < 0       # 200 грн is penalized!
    )
    if not budget_ok_test:
        failed += 1
        print("=" * 80)
        print(f"Budget & currency evaluation: FAIL | dict={b_dict} | usd={b_usd} | high={b_high} | tiny={b_tiny}")
    else:
        print("=" * 80)
        print("Budget & currency evaluation: OK")

    # 3. Format budget display test
    total_checks += 1
    fmt_dict = format_budget_display({"amount": 3000, "currency": "UAH"})
    fmt_str = format_budget_display("3000 грн")
    fmt_none = format_budget_display(None)
    fmt_ok = (
        fmt_dict == "3 000 UAH"
        and fmt_str == "3000 грн"
        and fmt_none == "Не вказано"
    )
    if not fmt_ok:
        failed += 1
        print("=" * 80)
        print(f"Format budget display: FAIL | dict={fmt_dict} | str={fmt_str} | none={fmt_none}")
    else:
        print("=" * 80)
        print("Format budget display: OK")

    # 4. SQLite WAL mode & index test
    total_checks += 1
    init_db()
    with get_connection() as conn:
        journal_mode = conn.execute("PRAGMA journal_mode;").fetchone()[0]
        indexes = [r[1] for r in conn.execute("PRAGMA index_list('projects');").fetchall()]
    wal_ok = (
        journal_mode.lower() == "wal"
        and "idx_projects_status_created" in indexes
    )
    if not wal_ok:
        failed += 1
        print("=" * 80)
        print(f"SQLite WAL mode & index: FAIL | journal_mode={journal_mode} | indexes={indexes}")
    else:
        print("=" * 80)
        print(f"SQLite WAL mode & index: OK (journal_mode={journal_mode})")

    # 5. Reusable HTTP Client test
    total_checks += 1
    import asyncio
    async def test_client_reuse():
        c1 = await get_http_client()
        c2 = await get_http_client()
        is_same = c1 is c2 and not c1.is_closed
        await close_http_client()
        is_closed = c1.is_closed
        return is_same and is_closed

    http_reuse_ok = asyncio.run(test_client_reuse())
    if not http_reuse_ok:
        failed += 1
        print("=" * 80)
        print("HTTP Client reuse: FAIL")
    else:
        print("=" * 80)
        print("HTTP Client reuse: OK")

    print("=" * 80)
    print(f"Result: {total_checks - failed}/{total_checks} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
