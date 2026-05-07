import sqlite3
from pathlib import Path
from datetime import datetime

DB_PATH = Path("data/projects.db")


def get_connection():
    DB_PATH.parent.mkdir(exist_ok=True)
    return sqlite3.connect(DB_PATH)


def init_db():
    with get_connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS projects (
                project_id TEXT PRIMARY KEY,
                title TEXT,
                description TEXT,
                budget TEXT,
                bids_count TEXT,
                url TEXT,
                analysis TEXT,
                user_rating TEXT,
                created_at TEXT
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)

        conn.execute("""
            INSERT OR IGNORE INTO settings (key, value)
            VALUES ('min_score', '45')
        """)


def save_project(project_id, title, description, budget, bids_count, url, analysis):
    with get_connection() as conn:
        conn.execute("""
            INSERT OR IGNORE INTO projects (
                project_id, title, description, budget, bids_count, url, analysis, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            project_id,
            title,
            description,
            str(budget),
            str(bids_count),
            url,
            analysis,
            datetime.now().isoformat(timespec="seconds")
        ))


def is_seen(project_id: str) -> bool:
    with get_connection() as conn:
        cursor = conn.execute(
            "SELECT 1 FROM projects WHERE project_id = ?",
            (project_id,)
        )
        return cursor.fetchone() is not None


def get_project(project_id: str):
    with get_connection() as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.execute(
            "SELECT * FROM projects WHERE project_id = ?",
            (project_id,)
        )
        row = cursor.fetchone()
        return dict(row) if row else None


def set_project_rating(project_id: str, rating: str):
    with get_connection() as conn:
        conn.execute(
            "UPDATE projects SET user_rating = ? WHERE project_id = ?",
            (rating, project_id)
        )


def get_stats():
    with get_connection() as conn:
        cursor = conn.execute("SELECT COUNT(*) FROM projects")
        total = cursor.fetchone()[0]

        cursor = conn.execute("""
            SELECT user_rating, COUNT(*)
            FROM projects
            GROUP BY user_rating
        """)

        ratings = dict(cursor.fetchall())

        return {
            "total": total,
            "good": ratings.get("good", 0),
            "bad": ratings.get("bad", 0),
            "skip": ratings.get("skip", 0),
            "unrated": ratings.get(None, 0),
        }


def get_setting(key: str, default=None):
    with get_connection() as conn:
        cursor = conn.execute(
            "SELECT value FROM settings WHERE key = ?",
            (key,)
        )
        row = cursor.fetchone()
        return row[0] if row else default


def set_setting(key: str, value: str):
    with get_connection() as conn:
        conn.execute("""
            INSERT INTO settings (key, value)
            VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
        """, (key, value))


def get_good_bad_keywords():
    with get_connection() as conn:
        good_rows = conn.execute("""
            SELECT title, description FROM projects
            WHERE user_rating = 'good'
        """).fetchall()

        bad_rows = conn.execute("""
            SELECT title, description FROM projects
            WHERE user_rating = 'bad'
        """).fetchall()

    return good_rows, bad_rows