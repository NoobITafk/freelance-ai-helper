import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from .config import MIN_SCORE, PROJECT_ROOT

DB_PATH = PROJECT_ROOT / "data" / "projects.db"
DEFAULT_MIN_SCORE = str(MIN_SCORE)
ALLOWED_RATINGS = {"great", "good", "maybe", "bad", "not_mine", "skip"}


def get_connection() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(exist_ok=True)

    conn = sqlite3.connect(
        DB_PATH,
        timeout=15,
    )

    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA synchronous = NORMAL;")
    return conn


def init_db() -> None:
    with get_connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS projects (
                project_id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                description TEXT,
                budget TEXT,
                bids_count TEXT,
                url TEXT,
                analysis TEXT,
                status TEXT,
                score INTEGER,
                reason TEXT,
                user_rating TEXT,
                created_at TEXT NOT NULL
            )
        """)

        ensure_column(conn, "projects", "status", "TEXT")
        ensure_column(conn, "projects", "score", "INTEGER")
        ensure_column(conn, "projects", "reason", "TEXT")
        ensure_column(conn, "projects", "employer_info", "TEXT")
        ensure_column(conn, "projects", "assets_info", "TEXT")
        ensure_column(conn, "projects", "pipeline_status", "TEXT DEFAULT 'new'")
        ensure_column(conn, "projects", "deal_amount", "REAL")
        ensure_column(conn, "projects", "deal_currency", "TEXT DEFAULT 'UAH'")

        conn.execute("""
            CREATE TABLE IF NOT EXISTS portfolio_cases (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                category TEXT NOT NULL,
                title TEXT NOT NULL,
                description TEXT DEFAULT '',
                url TEXT DEFAULT '',
                created_at TEXT NOT NULL
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_portfolio_cases_cat ON portfolio_cases(category)")

        conn.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
        """)

        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_projects_user_rating
            ON projects(user_rating)
        """)

        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_projects_created_at
            ON projects(created_at)
        """)

        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_projects_status_created
            ON projects(status, created_at)
        """)

        conn.execute(
            """
            INSERT OR IGNORE INTO settings (key, value)
            VALUES ('min_score', ?)
        """,
            (DEFAULT_MIN_SCORE,),
        )


def ensure_column(
    conn: sqlite3.Connection,
    table_name: str,
    column_name: str,
    column_type: str,
) -> None:
    columns = {row["name"] for row in conn.execute(f"PRAGMA table_info({table_name})").fetchall()}

    if column_name not in columns:
        conn.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}")


def save_project(
    project_id: str,
    title: str,
    description: str,
    budget,
    bids_count,
    url: str,
    analysis: str,
    status: str = "skipped",
    score: int | None = None,
    reason: str = "",
    employer_info: str | None = None,
    assets_info: str | None = None,
) -> None:
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO projects (
                project_id,
                title,
                description,
                budget,
                bids_count,
                url,
                analysis,
                status,
                score,
                reason,
                employer_info,
                assets_info,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(project_id) DO UPDATE SET
                title = excluded.title,
                description = excluded.description,
                budget = excluded.budget,
                bids_count = excluded.bids_count,
                url = excluded.url,
                analysis = excluded.analysis,
                status = excluded.status,
                score = excluded.score,
                reason = excluded.reason,
                employer_info = COALESCE(excluded.employer_info, projects.employer_info),
                assets_info = COALESCE(excluded.assets_info, projects.assets_info)
        """,
            (
                str(project_id),
                title or "Без назви",
                description or "",
                str(budget),
                str(bids_count),
                url or "",
                analysis or "",
                status,
                score,
                reason or "",
                employer_info,
                assets_info,
                datetime.now().isoformat(timespec="seconds"),
            ),
        )


def is_seen(project_id: str) -> bool:
    with get_connection() as conn:
        cursor = conn.execute(
            "SELECT 1 FROM projects WHERE project_id = ? LIMIT 1",
            (str(project_id),),
        )

        return cursor.fetchone() is not None


def get_project(project_id: str) -> Optional[dict]:
    with get_connection() as conn:
        cursor = conn.execute(
            "SELECT * FROM projects WHERE project_id = ?",
            (str(project_id),),
        )

        row = cursor.fetchone()
        return dict(row) if row else None


def set_project_rating(project_id: str, rating: str) -> None:
    if rating not in ALLOWED_RATINGS:
        raise ValueError(f"Невідомий рейтинг проєкту: {rating}")

    with get_connection() as conn:
        conn.execute(
            "UPDATE projects SET user_rating = ? WHERE project_id = ?",
            (rating, str(project_id)),
        )


def get_stats() -> dict:
    with get_connection() as conn:
        total = conn.execute("SELECT COUNT(*) FROM projects").fetchone()[0]

        sent = conn.execute(
            "SELECT COUNT(*) FROM projects WHERE status = 'sent'"
        ).fetchone()[0]

        recent_24h = conn.execute(
            "SELECT COUNT(*) FROM projects WHERE created_at >= datetime('now', '-1 day')"
        ).fetchone()[0]

        recent_sent_24h = conn.execute(
            "SELECT COUNT(*) FROM projects WHERE status = 'sent' AND created_at >= datetime('now', '-1 day')"
        ).fetchone()[0]

        rows = conn.execute("""
            SELECT user_rating, COUNT(*) AS count
            FROM projects
            GROUP BY user_rating
        """).fetchall()

        ratings = {row["user_rating"]: row["count"] for row in rows}

        return {
            "total": total,
            "sent": sent,
            "recent_24h": recent_24h,
            "recent_sent_24h": recent_sent_24h,
            "great": ratings.get("great", 0),
            "good": ratings.get("good", 0),
            "maybe": ratings.get("maybe", 0),
            "bad": ratings.get("bad", 0),
            "not_mine": ratings.get("not_mine", 0),
            "skip": ratings.get("skip", 0),
            "unrated": ratings.get(None, 0),
        }


def get_setting(key: str, default=None):
    with get_connection() as conn:
        cursor = conn.execute(
            "SELECT value FROM settings WHERE key = ?",
            (key,),
        )

        row = cursor.fetchone()
        return row["value"] if row else default


def set_setting(key: str, value: str) -> None:
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO settings (key, value)
            VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
        """,
            (key, str(value)),
        )


def set_portfolio_link(category: str, url: str) -> None:
    category = category.lower().strip()
    key = f"portfolio_{category}"
    set_setting(key, url.strip())


def get_portfolio_links() -> dict[str, str]:
    with get_connection() as conn:
        rows = conn.execute("SELECT key, value FROM settings WHERE key LIKE 'portfolio_%'").fetchall()
        return {row["key"].replace("portfolio_", ""): row["value"] for row in rows}


def get_portfolio_link_for_kind(kind: str) -> str | None:
    mapping = {
        "telegram_bot": "bot",
        "parsing": "parsing",
        "backend": "backend",
        "api": "backend",
        "frontend": "web",
        "html_css": "web",
        "wordpress": "web",
        "excel": "excel",
        "ai_integration": "bot",
        "mobile": "mobile",
        "devops": "devops",
    }
    cat = mapping.get(kind, kind)
    specific = get_setting(f"portfolio_{cat}")
    if specific:
        return specific
    return get_setting("portfolio_general")


def get_recent_projects(limit: int = 5) -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT *
            FROM projects
            ORDER BY created_at DESC
            LIMIT ?
        """,
            (limit,),
        ).fetchall()

        return [dict(row) for row in rows]


def get_feed_projects(limit: int = 50) -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT *
            FROM projects
            WHERE status = 'sent' OR score >= 35 OR (pipeline_status IS NOT NULL AND pipeline_status != 'new')
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        results = [dict(row) for row in rows]
        if not results:
            fallback = conn.execute(
                "SELECT * FROM projects ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
            results = [dict(row) for row in fallback]
        return results


def get_crm_projects(limit: int = 50) -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT *
            FROM projects
            WHERE pipeline_status IS NOT NULL AND pipeline_status != 'new'
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [dict(row) for row in rows]


def check_database() -> tuple[bool, str]:
    try:
        with get_connection() as conn:
            conn.execute("SELECT 1").fetchone()
        return True, "OK"

    except Exception as error:
        return False, str(error)


def get_good_bad_keywords() -> tuple[list[tuple[str, str]], list[tuple[str, str]]]:
    with get_connection() as conn:
        good_rows = conn.execute("""
            SELECT title, description
            FROM projects
            WHERE user_rating IN ('great', 'good')
        """).fetchall()

        bad_rows = conn.execute("""
            SELECT title, description
            FROM projects
            WHERE user_rating IN ('bad', 'not_mine')
        """).fetchall()

        good = [(row["title"], row["description"]) for row in good_rows]

        bad = [(row["title"], row["description"]) for row in bad_rows]

        return good, bad


def cleanup_old_projects(days: int = 30) -> int:
    cutoff_date = (datetime.now() - timedelta(days=days)).isoformat(timespec="seconds")
    with get_connection() as conn:
        cursor = conn.execute(
            """
            DELETE FROM projects
            WHERE created_at < ?
              AND user_rating IS NULL
              AND status = 'skipped'
            """,
            (cutoff_date,),
        )
        rowcount = cursor.rowcount
        try:
            conn.execute("PRAGMA optimize;")
            conn.execute("PRAGMA wal_checkpoint(PASSIVE);")
        except Exception:
            pass
        return rowcount


def add_portfolio_case(category: str, title: str, description: str = "", url: str = "") -> int:
    with get_connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO portfolio_cases (category, title, description, url, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                category.strip().lower(),
                title.strip(),
                description.strip(),
                url.strip(),
                datetime.now().isoformat(timespec="seconds"),
            ),
        )
        return cursor.lastrowid


def delete_portfolio_case(case_id: int) -> bool:
    with get_connection() as conn:
        cursor = conn.execute("DELETE FROM portfolio_cases WHERE id = ?", (case_id,))
        return cursor.rowcount > 0


def get_portfolio_cases(category: str | None = None) -> list[dict]:
    with get_connection() as conn:
        if category:
            rows = conn.execute(
                "SELECT * FROM portfolio_cases WHERE category = ? ORDER BY id DESC",
                (category.strip().lower(),),
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM portfolio_cases ORDER BY id DESC").fetchall()
        return [dict(row) for row in rows]


def get_best_case_for_project(kind: str, project_text: str = "") -> dict | None:
    cat_map = {
        "telegram_bot": "bot",
        "parsing": "parser",
        "backend": "backend",
        "api": "backend",
        "frontend": "web",
        "html_css": "web",
        "wordpress": "web",
        "excel": "excel",
        "ai_integration": "ai",
        "mobile": "mobile",
        "devops": "devops",
    }
    target_cat = cat_map.get(kind, "general")
    cases = get_portfolio_cases()
    if not cases:
        return None

    cat_matches = [c for c in cases if c["category"] == target_cat]
    if cat_matches:
        if project_text:
            text_lower = project_text.lower()
            scored = []
            for c in cat_matches:
                score = sum(1 for word in c["title"].lower().split() if len(word) > 3 and word in text_lower)
                scored.append((score, c))
            scored.sort(key=lambda x: x[0], reverse=True)
            return scored[0][1]
        return cat_matches[0]

    general_matches = [c for c in cases if c["category"] in {"general", "all"}]
    if general_matches:
        return general_matches[0]

    return cases[0]


def update_project_pipeline(
    project_id: str,
    status: str,
    deal_amount: float | None = None,
    currency: str = "UAH",
) -> bool:
    with get_connection() as conn:
        existing = conn.execute("SELECT project_id FROM projects WHERE project_id = ?", (str(project_id),)).fetchone()
        if not existing:
            conn.execute(
                """
                INSERT INTO projects (project_id, title, pipeline_status, deal_amount, deal_currency, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    str(project_id),
                    f"Проєкт #{project_id}",
                    status,
                    deal_amount,
                    currency,
                    datetime.now().isoformat(timespec="seconds"),
                ),
            )
            return True

        if deal_amount is not None:
            cursor = conn.execute(
                """
                UPDATE projects
                SET pipeline_status = ?,
                    deal_amount = ?,
                    deal_currency = ?
                WHERE project_id = ?
                """,
                (status, deal_amount, currency, str(project_id)),
            )
        else:
            cursor = conn.execute(
                """
                UPDATE projects
                SET pipeline_status = ?
                WHERE project_id = ?
                """,
                (status, str(project_id)),
            )
        return cursor.rowcount > 0


def get_crm_stats() -> dict:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT pipeline_status, COUNT(*) as cnt
            FROM projects
            WHERE pipeline_status IS NOT NULL AND pipeline_status != 'new'
            GROUP BY pipeline_status
            """
        ).fetchall()
        counts = {row["pipeline_status"]: row["cnt"] for row in rows}

        bids_placed = (
            counts.get("bid_placed", 0)
            + counts.get("replied", 0)
            + counts.get("in_progress", 0)
            + counts.get("completed", 0)
        )
        replied = counts.get("replied", 0)
        in_progress = counts.get("in_progress", 0)
        completed = counts.get("completed", 0)

        win_rate = (completed / bids_placed * 100) if bids_placed > 0 else 0.0
        reply_rate = ((replied + in_progress + completed) / bids_placed * 100) if bids_placed > 0 else 0.0

        month_start = datetime.now().strftime("%Y-%m-01")
        row_month = conn.execute(
            """
            SELECT COALESCE(SUM(deal_amount), 0) as total
            FROM projects
            WHERE pipeline_status = 'completed' AND created_at >= ?
            """,
            (month_start,),
        ).fetchone()
        income_month = float(row_month["total"]) if row_month else 0.0

        row_total = conn.execute(
            """
            SELECT COALESCE(SUM(deal_amount), 0) as total
            FROM projects
            WHERE pipeline_status = 'completed'
            """
        ).fetchone()
        income_total = float(row_total["total"]) if row_total else 0.0

        return {
            "bids_placed": bids_placed,
            "replied": replied,
            "in_progress": in_progress,
            "completed": completed,
            "win_rate": win_rate,
            "reply_rate": reply_rate,
            "income_month": income_month,
            "income_total": income_total,
        }


def is_quiet_hours_now(custom_now: datetime | None = None) -> bool:
    setting = get_setting("quiet_hours")
    if not setting or setting.lower() in {"off", "false", "0", "disabled", "none"}:
        return False

    try:
        parts = setting.replace(" ", "").split("-")
        if len(parts) != 2:
            return False

        now_time = (custom_now or datetime.now()).time()
        start = datetime.strptime(parts[0], "%H:%M").time()
        end = datetime.strptime(parts[1], "%H:%M").time()

        if start <= end:
            return start <= now_time <= end
        else:
            return now_time >= start or now_time <= end
    except Exception:
        return False


def get_night_projects(hours: int = 12, min_score: int = 35) -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT * FROM projects
            WHERE created_at >= datetime('now', ?)
              AND status = 'sent'
              AND (score IS NULL OR score >= ?)
            ORDER BY score DESC, created_at DESC
            LIMIT 10
            """,
            (f"-{hours} hours", min_score),
        ).fetchall()
        return [dict(row) for row in rows]


def create_database_backup(backup_dir: Path | None = None) -> Path:
    target_dir = backup_dir or (DB_PATH.parent / "backups")
    target_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_file = target_dir / f"projects_backup_{timestamp}.db"

    with get_connection() as src:
        with sqlite3.connect(backup_file) as dst:
            src.backup(dst)

    return backup_file


def export_crm_data_csv() -> str:
    import csv
    import io

    output = io.StringIO()
    output.write("\ufeff")  # UTF-8 BOM for Microsoft Excel
    writer = csv.writer(output, delimiter=";")
    writer.writerow([
        "ID проєкту",
        "Дата створення",
        "Назва проєкту",
        "Статус воронки",
        "Сума угоди",
        "Валюта",
        "Бюджет біржі",
        "Score",
        "Замовник",
        "Посилання",
    ])

    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT project_id, created_at, title, pipeline_status, deal_amount,
                   deal_currency, budget, score, employer_info, url
            FROM projects
            WHERE (pipeline_status IS NOT NULL AND pipeline_status != 'new')
               OR status = 'sent'
            ORDER BY created_at DESC
            """
        ).fetchall()

        status_labels = {
            "bid_placed": "Ставку подано",
            "replied": "Замовник відповів",
            "in_progress": "В роботі",
            "completed": "Завершено",
            "declined": "Відхилено",
            "sent": "Отримано в стрічку",
        }

        for r in rows:
            p_status = r["pipeline_status"] or "sent"
            deal_val = f"{r['deal_amount']:.2f}" if r["deal_amount"] is not None else ""
            writer.writerow([
                r["project_id"],
                r["created_at"] or "",
                r["title"] or "",
                status_labels.get(p_status, p_status),
                deal_val,
                r["deal_currency"] or "UAH",
                r["budget"] or "",
                r["score"] if r["score"] is not None else "",
                r["employer_info"] or "",
                r["url"] or "",
            ])

    return output.getvalue()
