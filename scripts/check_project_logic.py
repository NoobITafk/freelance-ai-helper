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

    print("=" * 80)
    print(f"Result: {len(CASES) - failed}/{len(CASES)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
