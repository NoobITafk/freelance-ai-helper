import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional

DB_PATH = Path("data/projects.db")
DEFAULT_MIN_SCORE = "45"
ALLOWED_RATINGS = {"great", "good", "maybe", "bad", "not_mine", "skip"}


def get_connection() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(exist_ok=True)

    conn = sqlite3.connect(
        DB_PATH,
        timeout=10,
    )

    conn.row_factory = sqlite3.Row
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
                user_rating TEXT,
                created_at TEXT NOT NULL
            )
        """)

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
            INSERT OR IGNORE INTO settings (key, value)
            VALUES ('min_score', ?)
        """, (DEFAULT_MIN_SCORE,))


def save_project(
    project_id: str,
    title: str,
    description: str,
    budget,
    bids_count,
    url: str,
    analysis: str,
) -> None:
    with get_connection() as conn:
        conn.execute("""
            INSERT OR IGNORE INTO projects (
                project_id,
                title,
                description,
                budget,
                bids_count,
                url,
                analysis,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            str(project_id),
            title or "Без назви",
            description or "",
            str(budget),
            str(bids_count),
            url or "",
            analysis or "",
            datetime.now().isoformat(timespec="seconds"),
        ))


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
        total = conn.execute(
            "SELECT COUNT(*) FROM projects"
        ).fetchone()[0]

        rows = conn.execute("""
            SELECT user_rating, COUNT(*) AS count
            FROM projects
            GROUP BY user_rating
        """).fetchall()

        ratings = {
            row["user_rating"]: row["count"]
            for row in rows
        }

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
        conn.execute("""
            INSERT INTO settings (key, value)
            VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
        """, (key, str(value)))


def get_recent_projects(limit: int = 5) -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute("""
            SELECT *
            FROM projects
            ORDER BY created_at DESC
            LIMIT ?
        """, (limit,)).fetchall()

        return [dict(row) for row in rows]


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

        good = [
            (row["title"], row["description"])
            for row in good_rows
        ]

        bad = [
            (row["title"], row["description"])
            for row in bad_rows
        ]

        return good, bad
