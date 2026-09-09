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
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(project_id) DO UPDATE SET
                title = excluded.title,
                description = excluded.description,
                budget = excluded.budget,
                bids_count = excluded.bids_count,
                url = excluded.url,
                analysis = excluded.analysis,
                status = excluded.status,
                score = excluded.score,
                reason = excluded.reason
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

        rows = conn.execute("""
            SELECT user_rating, COUNT(*) AS count
            FROM projects
            GROUP BY user_rating
        """).fetchall()

        ratings = {row["user_rating"]: row["count"] for row in rows}

        return {
            "total": total,
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
