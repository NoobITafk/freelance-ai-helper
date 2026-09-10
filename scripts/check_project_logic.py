from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from freelance_helper.app.ai_analyzer import (
    detect_project_language,
    fallback_bid,
    fallback_questions,
    generate_chat_pitch,
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
    calculate_sweet_spot,
    detect_project_assets,
    evaluate_employer,
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
        name="Next.js database improvements",
        project={
            "title": "Доработки в проекте Next.js",
            "description": "Нужно сделать доработки в существующем проекте. Оптимизировать запросы и исправить баги.",
            "skills": [{"name": "Базы данных"}],
            "budget": "4550 грн",
            "bids_count": 5,
            "url": "https://freelancehunt.com/project/next-db",
        },
        expected_type="backend",
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
        name="Voiceover advertising video",
        project={
            "title": "Запис озвучки рекламного відео",
            "description": "Потрібен приємний дикторський голос для озвучення рекламного ролика.",
            "budget": "1000 грн",
            "bids_count": 1,
            "url": "https://freelancehunt.com/project/voiceover",
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
    Case(
        name="Mobile Flutter app",
        project={
            "title": "Мобільний додаток на Flutter для каталогу",
            "description": "Потрібно розробити мобільний додаток на Flutter для iOS та Android з підключенням REST API.",
            "budget": "15000 грн",
            "bids_count": 4,
            "url": "https://example.com/flutter-app",
        },
        expected_type="mobile",
        expected_technical=True,
    ),
    Case(
        name="DevOps Docker Nginx",
        project={
            "title": "Налаштування сервера Ubuntu, Docker та Nginx",
            "description": "Потрібен деплой проекту на VPS сервер, налаштування Docker контейнерів, Nginx та SSL.",
            "budget": "4000 грн",
            "bids_count": 2,
            "url": "https://example.com/devops-docker",
        },
        expected_type="devops",
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
    has_unwanted = any(w in formatted_msg for w in ["Score:", "Бюджет:", "Чому підходить:", "Ризик:"])
    if len(msg_lines) > 6 or len(formatted_msg) > 600 or "Fallback rules" in formatted_msg or has_unwanted:
        failed += 1
        print("=" * 80)
        print("Concise message format: FAIL")
        print(f"Lines count: {len(msg_lines)}, total chars: {len(formatted_msg)}, has_unwanted: {has_unwanted}")
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
    b_pln = parse_budget_info("500 PLN")
    b_high = budget_score_adjustment("20 000 грн")
    b_tiny = budget_score_adjustment("200 грн")
    budget_ok_test = (
        b_dict == (5000, "UAH", 5000)
        and b_usd == (300, "USD", 12300)
        and b_pln == (500, "PLN", 5250)
        and b_high[1] == "yes"  # 20 000 грн is recognized as good budget!
        and b_tiny[0] < 0       # 200 грн is penalized!
    )
    if not budget_ok_test:
        failed += 1
        print("=" * 80)
        print(f"Budget & currency evaluation: FAIL | dict={b_dict} | usd={b_usd} | pln={b_pln} | high={b_high} | tiny={b_tiny}")
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

    # 6. English project detection and bid generation test
    total_checks += 1
    en_proj = {
        "title": "Need a FastAPI backend for an e-commerce platform",
        "description": "Looking for a backend developer to build REST API endpoints with FastAPI and PostgreSQL. Need user auth, product catalog and Stripe integration.",
        "budget": "8000 грн",
        "bids_count": 2,
        "tags": ["FastAPI", "Python", "PostgreSQL", "Backend", "REST API"],
        "url": "https://freelancehunt.com/project/123",
    }
    detected_lang = detect_project_language(en_proj["title"], en_proj["description"])
    en_bid = fallback_bid(en_proj)
    en_questions = fallback_questions(en_proj)
    en_ok = (
        detected_lang == "en"
        and "Hello!" in en_bid
        and "Budget:" in en_bid
        and "Warranty" not in en_bid
        and "Key questions to ask" in en_questions
    )
    if not en_ok:
        failed += 1
        print("=" * 80)
        print("English bid & questions generation: FAIL")
    else:
        print("=" * 80)
        print("English bid & questions generation: OK")

    # 7. Chat pitch test
    total_checks += 1
    pitch_uk = generate_chat_pitch({
        "title": "Telegram-бот для заявок",
        "description": "Потрібен бот на aiogram з базою даних",
        "budget": "3000 грн",
    })
    pitch_en = generate_chat_pitch(en_proj)
    pitch_ok = (
        "Telegram" in pitch_uk
        and "Напишіть у чат" in pitch_uk
        and "backend" in pitch_en.lower()
        and "chat" in pitch_en.lower()
    )
    if not pitch_ok:
        failed += 1
        print("=" * 80)
        print(f"Chat pitch generation: FAIL | uk={pitch_uk} | en={pitch_en}")
    else:
        print("=" * 80)
    # 8. Portfolio link management and dynamic injection into bids
    total_checks += 1
    from freelance_helper.app.database import (
        get_portfolio_link_for_kind,
        get_portfolio_links,
        set_portfolio_link,
    )

    test_bot_link = "https://t.me/MyTestPortfolioBot"
    test_gen_link = "https://github.com/my-test-profile"
    set_portfolio_link("bot", test_bot_link)
    set_portfolio_link("general", test_gen_link)

    links = get_portfolio_links()
    link_for_bot = get_portfolio_link_for_kind("telegram_bot")
    link_for_parsing = get_portfolio_link_for_kind("parsing")  # should fallback to general

    # Test bid injection
    bot_project = CASES[0].project
    bid_with_portfolio = fallback_bid(bot_project)

    portfolio_ok = (
        links.get("bot") == test_bot_link
        and link_for_bot == test_bot_link
        and link_for_parsing == test_gen_link
        and test_bot_link in bid_with_portfolio
    )

    if not portfolio_ok:
        failed += 1
        print("=" * 80)
        print("Portfolio management & bid injection: FAIL")
    else:
        print("=" * 80)
        print("Portfolio management & bid injection: OK")

    # 9. Keyboards and bid submission structure
    total_checks += 1
    from freelance_helper.app.bot.keyboards import bid_keyboard, confirm_publish_keyboard

    b_kb = bid_keyboard("12345")
    c_kb = confirm_publish_keyboard("12345")

    # Verify buttons
    row0 = b_kb.inline_keyboard[0]
    site_btn = row0[0]
    b_callbacks = [btn.callback_data for row in b_kb.inline_keyboard for btn in row]
    c_callbacks = [btn.callback_data for row in c_kb.inline_keyboard for btn in row]

    kb_ok = (
        site_btn.text == "🚀 Зробити ставку"
        and site_btn.url == "https://freelancehunt.com/project/12345.html"
        and "rebid:12345" in b_callbacks
        and "pitch:12345" in b_callbacks
        and "questions:12345" in b_callbacks
        and "skip:12345" in b_callbacks
        and "confirm_publish:12345" in c_callbacks
        and "cancel_publish:12345" in c_callbacks
    )

    if not kb_ok:
        failed += 1
        print("=" * 80)
        print("Bid publish keyboards structure: FAIL")
    else:
        print("=" * 80)
        print("Bid publish keyboards structure: OK")

    # 10. No warranty / support in generated bids
    total_checks += 1
    sample_proj = CASES[0].project
    bids_to_check = [
        fallback_bid(sample_proj, variant="short"),
        fallback_bid(sample_proj, variant="technical"),
        fallback_bid(sample_proj, variant="cautious"),
    ]
    unwanted_phrases = ["14 днів", "Гарантія", "Warranty", "Налаштування:", "Setup:"]
    found_unwanted = [
        phrase for phrase in unwanted_phrases
        if any(phrase in b for b in bids_to_check)
    ]
    if found_unwanted:
        failed += 1
        print("=" * 80)
        print(f"No warranty / support check: FAIL | found: {found_unwanted}")
    else:
        print("=" * 80)
        print("No warranty / support check: OK")

    # 11. POSIX flock concurrency lock test
    total_checks += 1
    from freelance_helper.app.telegram_bot import acquire_single_instance_lock, release_single_instance_lock, LOCK_PATH
    import os, fcntl
    release_single_instance_lock()
    acquire_single_instance_lock()
    # Try to open second lock descriptor
    second_blocked = False
    test_fd = os.open(LOCK_PATH, os.O_RDWR)
    try:
        fcntl.flock(test_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except (BlockingIOError, OSError):
        second_blocked = True
    finally:
        os.close(test_fd)
        release_single_instance_lock()

    if not second_blocked:
        failed += 1
        print("=" * 80)
        print("POSIX flock concurrency lock: FAIL (second process was not blocked)")
    else:
        print("=" * 80)
        print("POSIX flock concurrency lock: OK")

    # 12. Bidirectional learning bonus test
    total_checks += 1
    from freelance_helper.app.rules import learning_bonus
    good_dataset = [("Розробка бота на Python", "Потрібно створити Telegram-бота на Python з базою")]
    bad_dataset = [("Монтаж та озвучка відео", "Потрібен відеомонтаж та диктор")]
    pos_bonus = learning_bonus("Telegram бот", "Потрібен бот", (good_dataset, []))
    neg_bonus = learning_bonus("Монтаж ролика", "Потрібен відеомонтаж", ([], bad_dataset))
    learning_ok = pos_bonus > 0 and neg_bonus < 0
    if not learning_ok:
        failed += 1
        print("=" * 80)
        print(f"Bidirectional learning bonus: FAIL | pos={pos_bonus} | neg={neg_bonus}")
    else:
        print("=" * 80)
        print(f"Bidirectional learning bonus: OK (pos={pos_bonus}, neg={neg_bonus})")

    # 13. Natural grammar & budget negotiation test
    total_checks += 1
    micro_budget_proj = {
        "title": "Створення сайту каталогу",
        "description": "Потрібен простий сайт каталогу продукції",
        "budget": "500 грн",
        "bids_count": 2,
        "url": "https://example.com/site",
    }
    sample_bid = fallback_bid(micro_budget_proj, variant="short")
    no_tautology = "під створення" not in sample_bid and "під розробку" not in sample_bid
    has_smart_budget = "базової версії" in sample_bid or "500 грн" in sample_bid
    grammar_ok = no_tautology and has_smart_budget
    if not grammar_ok:
        failed += 1
        print("=" * 80)
        print(f"Natural grammar & budget negotiation: FAIL | bid:\n{sample_bid}")
    else:
        print("=" * 80)
        print("Natural grammar & budget negotiation: OK")

    # 14. Employer evaluation, asset detection, and sweet spot calculation
    total_checks += 1
    emp_top = evaluate_employer({"completed_projects": 15, "positive_reviews": 15, "negative_reviews": 0})
    emp_risky = evaluate_employer({"completed_projects": 4, "positive_reviews": 2, "negative_reviews": 3})
    emp_new = evaluate_employer({"completed_projects": 0})

    sample_attrs = {
        "name": "Доопрацювання веб-сервісу",
        "description": "Макет у figma.com/file/xyz123, ТЗ у docs.google.com/document/d/abc, також є архів dump.zip",
    }
    detected = detect_project_assets(sample_attrs)
    sweet_spot = calculate_sweet_spot((10000, "UAH", True), 15)

    module1_2_ok = (
        emp_top["status"] == "top"
        and emp_top["score_bonus"] > 0
        and emp_risky["status"] == "risky"
        and emp_risky["score_bonus"] < 0
        and emp_new["status"] == "new"
        and "Figma макет" in detected
        and "Google Docs ТЗ" in detected
        and "Архів з файлами" in detected
        and sweet_spot is not None
        and "sweet spot" in sweet_spot
    )
    if not module1_2_ok:
        failed += 1
        print("=" * 80)
        print(f"Client intelligence & asset detection: FAIL | detected={detected} | sweet_spot={sweet_spot}")
    else:
        print("=" * 80)
        print(f"Client intelligence & asset detection: OK (top bonus={emp_top['score_bonus']}, assets={detected})")

    # 15. Portfolio cases RAG & Freelance CRM Pipeline
    total_checks += 1
    from freelance_helper.app.database import (
        add_portfolio_case,
        delete_portfolio_case,
        get_best_case_for_project,
        get_crm_stats,
        get_portfolio_cases,
        update_project_pipeline,
    )
    case_id = add_portfolio_case(
        category="bot",
        title="Telegram Crypto Payment Bot",
        description="Бот для автоматичного прийому криптовалюти через webhook",
        url="https://t.me/CryptoTestBot",
    )
    all_cases = get_portfolio_cases("bot")
    best_case = get_best_case_for_project("telegram_bot", "Потрібен бот для оплати")

    update_project_pipeline("test_crm_proj_1", "bid_placed")
    update_project_pipeline("test_crm_proj_2", "completed", deal_amount=8500.0, currency="UAH")
    crm_stats = get_crm_stats()

    crm_cases_ok = (
        case_id > 0
        and any(c["id"] == case_id for c in all_cases)
        and best_case is not None
        and best_case["title"] == "Telegram Crypto Payment Bot"
        and crm_stats["bids_placed"] >= 2
        and crm_stats["completed"] >= 1
        and crm_stats["income_total"] >= 8500.0
    )
    delete_portfolio_case(case_id)

    if not crm_cases_ok:
        failed += 1
        print("=" * 80)
        print(f"Portfolio cases RAG & CRM: FAIL | crm_stats={crm_stats} | best_case={best_case}")
    else:
        print("=" * 80)
        print(f"Portfolio cases RAG & CRM: OK (win_rate={crm_stats['win_rate']:.1f}%, income={crm_stats['income_total']} UAH)")

    # 16. Quiet hours evaluation & Database backup
    total_checks += 1
    from datetime import datetime
    from freelance_helper.app.database import create_database_backup, is_quiet_hours_now, set_setting

    set_setting("quiet_hours", "23:00 - 08:00")
    night_time = datetime(2026, 9, 10, 2, 30)
    day_time = datetime(2026, 9, 10, 14, 30)
    is_quiet_night = is_quiet_hours_now(custom_now=night_time)
    is_quiet_day = is_quiet_hours_now(custom_now=day_time)

    backup_file = create_database_backup()
    backup_ok = backup_file.exists() and backup_file.stat().st_size > 0
    if backup_ok:
        try:
            backup_file.unlink()
        except Exception:
            pass

    quiet_backup_ok = is_quiet_night and not is_quiet_day and backup_ok
    if not quiet_backup_ok:
        failed += 1
        print("=" * 80)
        print(f"Quiet hours & Backup check: FAIL | night={is_quiet_night} | day={is_quiet_day} | backup={backup_ok}")
    else:
        print("=" * 80)
        print(f"Quiet hours & Backup check: OK (night={is_quiet_night}, day={is_quiet_day}, backup={backup_ok})")

    # 17. One-click Excel/CSV Export
    total_checks += 1
    from freelance_helper.app.database import export_crm_data_csv
    csv_content = export_crm_data_csv()
    csv_ok = (
        csv_content.startswith("\ufeff")
        and "ID проєкту;Дата створення;Назва проєкту;Статус воронки" in csv_content
        and "Завершено" in csv_content
    )
    if not csv_ok:
        failed += 1
        print("=" * 80)
        print(f"CSV Export check: FAIL | bom={csv_content.startswith(chr(0xFEFF))} | length={len(csv_content)}")
    else:
        print("=" * 80)
        print(f"CSV Export check: OK (UTF-8 BOM present, length={len(csv_content)} chars)")

    # 18. Mini App Feed and CRM Queries
    total_checks += 1
    from freelance_helper.app.database import get_crm_projects, get_feed_projects
    feed = get_feed_projects(limit=10)
    crm = get_crm_projects(limit=10)
    feed_crm_ok = isinstance(feed, list) and isinstance(crm, list) and len(crm) >= 1
    if not feed_crm_ok:
        failed += 1
        print("=" * 80)
        print(f"Feed & CRM queries check: FAIL | feed_len={len(feed)}, crm_len={len(crm)}")
    else:
        print("=" * 80)
        print(f"Feed & CRM queries check: OK (feed={len(feed)}, crm={len(crm)})")

    # 19. Mini App Web Server & CRM API routes check
    total_checks += 1
    from freelance_helper.app.web_server import create_web_app, handle_health, handle_index, handle_subscription_status
    test_app = create_web_app()
    routes = [r.resource.canonical for r in test_app.router.routes() if hasattr(r, "resource") and r.resource]
    expected_routes = ["/", "/api/stats", "/api/projects", "/api/pipeline", "/api/cases", "/api/cases/{id}", "/api/health", "/api/export", "/api/subscription"]
    has_all_routes = all(r in routes for r in expected_routes)

    from aiohttp.test_utils import make_mocked_request
    import asyncio
    import json
    mock_health_req = make_mocked_request("GET", "/api/health", app=test_app)
    loop = asyncio.new_event_loop()
    resp_health = loop.run_until_complete(handle_health(mock_health_req))
    mock_index_req = make_mocked_request("GET", "/", app=test_app)
    resp_index = loop.run_until_complete(handle_index(mock_index_req))
    mock_sub_req = make_mocked_request("GET", "/api/subscription", app=test_app)
    resp_sub = loop.run_until_complete(handle_subscription_status(mock_sub_req))
    loop.close()

    health_data = json.loads(resp_health.text)
    sub_data = json.loads(resp_sub.text)
    api_health_ok = health_data.get("success") is True and health_data.get("status") == "online" and "database" in health_data
    sub_api_ok = sub_data.get("success") is True and "price" in sub_data
    index_ok = resp_index.status == 200

    webapp_ok = has_all_routes and api_health_ok and sub_api_ok and index_ok
    if not webapp_ok:
        failed += 1
        print("=" * 80)
        print(f"Mini App Web Server check: FAIL | routes={has_all_routes} | health={api_health_ok} | sub_api={sub_api_ok} | index={index_ok}")
    else:
        print("=" * 80)
        print(f"Mini App Web Server & CRM API check: OK (routes={len(routes)}, health=ok, sub=ok, index=200)")

    # 20. Subscription, 7-day Trial, Admin Lifetime & Automated Issuance Check
    total_checks += 1
    from freelance_helper.app.database import (
        activate_user_subscription,
        get_active_subscribers,
        get_user_subscription,
        init_user_subscription,
        is_user_subscribed,
    )
    from freelance_helper.app.config import TELEGRAM_CHAT_ID

    # 20a. New user gets 7-day free trial
    test_uid = "test_user_777"
    with get_connection() as conn:
        conn.execute("DELETE FROM subscriptions WHERE user_id = ?", (test_uid,))

    trial_sub = init_user_subscription(test_uid, username="tester", full_name="Test User", trial_days=7)
    trial_ok = (
        trial_sub is not None
        and trial_sub.get("status") == "trial"
        and trial_sub.get("is_active") is True
        and trial_sub.get("days_left", 0) in {7, 8}
        and is_user_subscribed(test_uid) is True
    )

    # 20b. Admin lifetime access
    admin_ok = False
    if TELEGRAM_CHAT_ID:
        admin_sub = get_user_subscription(TELEGRAM_CHAT_ID)
        admin_ok = admin_sub is not None and admin_sub.get("is_active") is True and is_user_subscribed(TELEGRAM_CHAT_ID) is True
    else:
        admin_ok = True

    # 20c. Automated 30-day activation
    paid_sub = activate_user_subscription(test_uid, days=30, amount=99.0, provider="telegram_payment")
    paid_ok = (
        paid_sub is not None
        and paid_sub.get("status") == "active"
        and paid_sub.get("is_active") is True
        and paid_sub.get("days_left", 0) >= 36  # 7 trial + 30 paid
        and is_user_subscribed(test_uid) is True
    )

    # 20d. Active subscribers query contains test_uid
    active_list = get_active_subscribers()
    list_ok = any(s.get("user_id") == test_uid for s in active_list)

    subs_all_ok = trial_ok and admin_ok and paid_ok and list_ok
    if not subs_all_ok:
        failed += 1
        print("=" * 80)
        print(f"Subscription system check: FAIL | trial={trial_ok} | admin={admin_ok} | paid={paid_ok} | list={list_ok}")
    else:
        print("=" * 80)
        print(f"Subscription & Trial check: OK (trial=7d, admin=lifetime, paid=+30d, active_subs={len(active_list)})")

    # 21. Multi-user Database & CRM Isolation Check
    total_checks += 1
    from freelance_helper.app.database import (
        add_portfolio_case,
        delete_portfolio_case,
        get_crm_projects,
        get_crm_stats,
        get_portfolio_cases,
        update_project_pipeline,
    )

    u_alpha = "user_alpha_111"
    u_beta = "user_beta_222"

    c_alpha_id = add_portfolio_case("bot", "Alpha Crypto Bot", "Alpha desc", "https://alpha.com", user_id=u_alpha)
    c_beta_id = add_portfolio_case("parser", "Beta Scraper", "Beta desc", "https://beta.com", user_id=u_beta)

    cases_alpha = get_portfolio_cases(user_id=u_alpha)
    cases_beta = get_portfolio_cases(user_id=u_beta)

    cases_isolated = (
        any(c["id"] == c_alpha_id for c in cases_alpha)
        and not any(c["id"] == c_beta_id for c in cases_alpha)
        and any(c["id"] == c_beta_id for c in cases_beta)
        and not any(c["id"] == c_alpha_id for c in cases_beta)
    )

    update_project_pipeline("p_alpha_deal", "completed", deal_amount=5000.0, user_id=u_alpha)
    update_project_pipeline("p_beta_deal", "completed", deal_amount=12000.0, user_id=u_beta)

    stats_alpha = get_crm_stats(user_id=u_alpha)
    stats_beta = get_crm_stats(user_id=u_beta)

    crm_isolated = (
        stats_alpha["completed"] == 1
        and stats_alpha["income_total"] == 5000.0
        and stats_beta["completed"] == 1
        and stats_beta["income_total"] == 12000.0
    )

    # Cleanup test cases
    delete_portfolio_case(c_alpha_id, user_id=u_alpha)
    delete_portfolio_case(c_beta_id, user_id=u_beta)

    multiuser_ok = cases_isolated and crm_isolated
    if not multiuser_ok:
        failed += 1
        print("=" * 80)
        print(f"Multi-user Isolation check: FAIL | cases={cases_isolated} | crm={crm_isolated}")
    # 22. Referral System Check
    total_checks += 1
    import time
    from freelance_helper.app.database import get_referral_stats, process_referral, get_user_subscription

    ts = int(time.time() * 1000)
    u_ref_host = f"test_referrer_{ts}"
    u_ref_guest = f"test_referred_{ts+1}"

    init_user_subscription(u_ref_host, chat_id=u_ref_host, status="trial")
    sub_before = get_user_subscription(u_ref_host)

    # Self-referral must fail
    self_ok = not process_referral(u_ref_host, u_ref_host)

    # Valid referral gives +3 days
    ref_ok = process_referral(u_ref_host, u_ref_guest, bonus_days=3)
    sub_after = get_user_subscription(u_ref_host)
    stats_ref = get_referral_stats(u_ref_host)

    # Duplicate referral of same guest must fail
    dup_ok = not process_referral(u_ref_host, u_ref_guest)

    referral_passed = (
        self_ok
        and ref_ok
        and dup_ok
        and stats_ref["invited_count"] >= 1
        and sub_after["days_left"] >= sub_before["days_left"] + 2
    )

    if not referral_passed:
        failed += 1
        print("=" * 80)
        print(f"Referral check: FAIL | self={self_ok} | ref={ref_ok} | dup={dup_ok} | stats={stats_ref}")
    else:
        print("=" * 80)
        print(f"Referral check: OK (invited={stats_ref['invited_count']}, bonus=+{stats_ref['bonus_days_earned']}d, days_after={sub_after['days_left']})")

    print("=" * 80)
    print(f"Result: {total_checks - failed}/{total_checks} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
