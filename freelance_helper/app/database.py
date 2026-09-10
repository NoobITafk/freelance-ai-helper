import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from .config import (
    MIN_SCORE,
    PROJECT_ROOT,
    SUBSCRIPTION_MONTH_PRICE,
    SUBSCRIPTION_REQUIRED,
    SUBSCRIPTION_STARS_PRICE,
    TELEGRAM_CHAT_ID,
    TRIAL_DAYS,
)

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
        ensure_column(conn, "portfolio_cases", "user_id", "TEXT DEFAULT ''")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_portfolio_cases_cat ON portfolio_cases(category)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_portfolio_cases_uid ON portfolio_cases(user_id)")

        conn.execute("""
            CREATE TABLE IF NOT EXISTS user_projects (
                user_id TEXT NOT NULL,
                project_id TEXT NOT NULL,
                pipeline_status TEXT DEFAULT 'new',
                deal_amount REAL,
                deal_currency TEXT DEFAULT 'UAH',
                user_rating TEXT,
                notes TEXT DEFAULT '',
                updated_at TEXT NOT NULL,
                PRIMARY KEY (user_id, project_id)
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_user_projects_uid_status ON user_projects(user_id, pipeline_status)")

        # Backfill owner's existing CRM projects into user_projects
        owner_id = str(TELEGRAM_CHAT_ID or "6212873712")
        conn.execute("""
            INSERT OR IGNORE INTO user_projects (user_id, project_id, pipeline_status, deal_amount, deal_currency, user_rating, updated_at)
            SELECT ?, project_id, COALESCE(pipeline_status, 'new'), deal_amount, COALESCE(deal_currency, 'UAH'), user_rating, created_at
            FROM projects
            WHERE (pipeline_status IS NOT NULL AND pipeline_status != 'new') OR user_rating IS NOT NULL
        """, (owner_id,))

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

        conn.execute("""
            CREATE TABLE IF NOT EXISTS subscriptions (
                user_id TEXT PRIMARY KEY,
                chat_id TEXT,
                username TEXT,
                full_name TEXT,
                status TEXT DEFAULT 'trial',
                plan TEXT DEFAULT 'month',
                started_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                payment_provider TEXT DEFAULT 'telegram',
                payment_id TEXT,
                amount REAL DEFAULT 0.0,
                currency TEXT DEFAULT 'UAH',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_subs_status_expires ON subscriptions(status, expires_at)")

        conn.execute(
            """
            INSERT OR IGNORE INTO settings (key, value)
            VALUES ('min_score', ?)
        """,
            (DEFAULT_MIN_SCORE,),
        )
        conn.execute(
            """
            INSERT OR IGNORE INTO settings (key, value)
            VALUES ('sub_price', ?)
        """,
            (str(SUBSCRIPTION_MONTH_PRICE),),
        )
        conn.execute(
            """
            INSERT OR IGNORE INTO settings (key, value)
            VALUES ('sub_stars_price', ?)
        """,
            (str(SUBSCRIPTION_STARS_PRICE),),
        )
        conn.execute("""
            CREATE TABLE IF NOT EXISTS referrals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                referrer_id TEXT NOT NULL,
                referred_id TEXT UNIQUE NOT NULL,
                created_at TEXT NOT NULL
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_referrals_referrer ON referrals(referrer_id)")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS channel_posts (
                project_id TEXT PRIMARY KEY,
                channel_id TEXT NOT NULL,
                posted_at TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS feedback (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                username TEXT DEFAULT '',
                full_name TEXT DEFAULT '',
                text TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_feedback_uid ON feedback(user_id)")


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


def set_project_rating(project_id: str, rating: str, user_id: str | None = None) -> None:
    if rating not in ALLOWED_RATINGS:
        raise ValueError(f"Невідомий рейтинг проєкту: {rating}")

    uid = str(user_id if user_id is not None else (TELEGRAM_CHAT_ID or ""))
    with get_connection() as conn:
        conn.execute(
            "UPDATE projects SET user_rating = ? WHERE project_id = ?",
            (rating, str(project_id)),
        )
        if uid:
            now_iso = datetime.now().isoformat(timespec="seconds")
            conn.execute(
                """
                INSERT INTO user_projects (user_id, project_id, user_rating, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(user_id, project_id) DO UPDATE SET
                    user_rating = excluded.user_rating,
                    updated_at = excluded.updated_at
                """,
                (uid, str(project_id), rating, now_iso),
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


def get_feed_projects(limit: int = 50, user_id: str | None = None) -> list[dict]:
    with get_connection() as conn:
        if user_id:
            uid = str(user_id)
            rows = conn.execute(
                """
                SELECT p.project_id, p.title, p.description, p.budget, p.bids_count, p.url, p.analysis,
                       p.status, p.score, p.reason, p.employer_info, p.assets_info,
                       COALESCE(up.user_rating, p.user_rating) as user_rating,
                       COALESCE(up.pipeline_status, p.pipeline_status, 'new') as pipeline_status,
                       COALESCE(up.deal_amount, p.deal_amount) as deal_amount,
                       COALESCE(up.deal_currency, p.deal_currency, 'UAH') as deal_currency,
                       p.created_at
                FROM projects p
                LEFT JOIN user_projects up ON p.project_id = up.project_id AND up.user_id = ?
                WHERE p.status = 'sent' OR p.score >= 35 OR (up.pipeline_status IS NOT NULL AND up.pipeline_status != 'new')
                ORDER BY p.created_at DESC
                LIMIT ?
                """,
                (uid, limit),
            ).fetchall()
        else:
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


def get_crm_projects(limit: int = 50, user_id: str | None = None) -> list[dict]:
    with get_connection() as conn:
        if user_id:
            uid = str(user_id)
            rows = conn.execute(
                """
                SELECT p.project_id, p.title, p.description, p.budget, p.bids_count, p.url, p.analysis,
                       p.score, up.pipeline_status, up.deal_amount, up.deal_currency,
                       COALESCE(up.user_rating, p.user_rating) as user_rating,
                       up.updated_at as created_at
                FROM user_projects up
                JOIN projects p ON up.project_id = p.project_id
                WHERE up.user_id = ? AND up.pipeline_status IS NOT NULL AND up.pipeline_status != 'new'
                ORDER BY up.updated_at DESC
                LIMIT ?
                """,
                (uid, limit),
            ).fetchall()
        else:
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


def add_portfolio_case(category: str, title: str, description: str = "", url: str = "", user_id: str | None = None) -> int:
    uid = str(user_id if user_id is not None else (TELEGRAM_CHAT_ID or ""))
    with get_connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO portfolio_cases (category, title, description, url, user_id, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                category.strip().lower(),
                title.strip(),
                description.strip(),
                url.strip(),
                uid,
                datetime.now().isoformat(timespec="seconds"),
            ),
        )
        return cursor.lastrowid


def delete_portfolio_case(case_id: int, user_id: str | None = None) -> bool:
    with get_connection() as conn:
        if user_id:
            uid = str(user_id)
            cursor = conn.execute(
                "DELETE FROM portfolio_cases WHERE id = ? AND (user_id = ? OR ? = ?)",
                (case_id, uid, uid, str(TELEGRAM_CHAT_ID or "")),
            )
        else:
            cursor = conn.execute("DELETE FROM portfolio_cases WHERE id = ?", (case_id,))
        return cursor.rowcount > 0


def get_portfolio_cases(category: str | None = None, user_id: str | None = None) -> list[dict]:
    with get_connection() as conn:
        clauses = []
        params = []
        if category and category.strip().lower() != "all":
            clauses.append("category = ?")
            params.append(category.strip().lower())
        if user_id:
            uid = str(user_id)
            if uid == str(TELEGRAM_CHAT_ID or ""):
                clauses.append("(user_id = ? OR user_id = '' OR user_id IS NULL)")
                params.append(uid)
            else:
                clauses.append("user_id = ?")
                params.append(uid)
        where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        rows = conn.execute(f"SELECT * FROM portfolio_cases {where_sql} ORDER BY id DESC", params).fetchall()
        return [dict(row) for row in rows]


def get_best_case_for_project(kind: str, project_text: str = "", user_id: str | None = None) -> dict | None:
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
    user_id: str | None = None,
) -> bool:
    now_iso = datetime.now().isoformat(timespec="seconds")
    uid = str(user_id if user_id is not None else (TELEGRAM_CHAT_ID or ""))
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
                    now_iso,
                ),
            )
        else:
            if deal_amount is not None:
                conn.execute(
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
                conn.execute(
                    """
                    UPDATE projects
                    SET pipeline_status = ?
                    WHERE project_id = ?
                    """,
                    (status, str(project_id)),
                )

        if uid:
            conn.execute(
                """
                INSERT INTO user_projects (user_id, project_id, pipeline_status, deal_amount, deal_currency, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(user_id, project_id) DO UPDATE SET
                    pipeline_status = excluded.pipeline_status,
                    deal_amount = COALESCE(excluded.deal_amount, user_projects.deal_amount),
                    deal_currency = excluded.deal_currency,
                    updated_at = excluded.updated_at
                """,
                (uid, str(project_id), status, deal_amount, currency, now_iso),
            )
        return True


def get_crm_stats(user_id: str | None = None) -> dict:
    with get_connection() as conn:
        if user_id:
            uid = str(user_id)
            rows = conn.execute(
                """
                SELECT pipeline_status, COUNT(*) as cnt
                FROM user_projects
                WHERE user_id = ? AND pipeline_status IS NOT NULL AND pipeline_status != 'new'
                GROUP BY pipeline_status
                """,
                (uid,),
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
                FROM user_projects
                WHERE user_id = ? AND pipeline_status = 'completed' AND updated_at >= ?
                """,
                (uid, month_start),
            ).fetchone()
            income_month = float(row_month["total"]) if row_month else 0.0

            row_total = conn.execute(
                """
                SELECT COALESCE(SUM(deal_amount), 0) as total
                FROM user_projects
                WHERE user_id = ? AND pipeline_status = 'completed'
                """,
                (uid,),
            ).fetchone()
            income_total = float(row_total["total"]) if row_total else 0.0
        else:
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


def export_crm_data_csv(user_id: str | None = None) -> str:
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
        if user_id:
            uid = str(user_id)
            rows = conn.execute(
                """
                SELECT p.project_id, COALESCE(up.updated_at, p.created_at) as created_at, p.title,
                       up.pipeline_status, up.deal_amount, up.deal_currency,
                       p.budget, p.score, p.employer_info, p.url
                FROM user_projects up
                JOIN projects p ON up.project_id = p.project_id
                WHERE up.user_id = ? AND up.pipeline_status IS NOT NULL AND up.pipeline_status != 'new'
                ORDER BY up.updated_at DESC
                """,
                (uid,),
            ).fetchall()
        else:
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


def init_user_subscription(
    user_id: str | int,
    chat_id: str | int | None = None,
    username: str | None = None,
    full_name: str | None = None,
    trial_days: int = TRIAL_DAYS,
    status: str | None = None,
) -> dict:
    user_id_str = str(user_id)
    chat_id_str = str(chat_id or user_id)
    now_iso = datetime.now().isoformat(timespec="seconds")

    with get_connection() as conn:
        row = conn.execute("SELECT * FROM subscriptions WHERE user_id = ?", (user_id_str,)).fetchone()
        if row:
            conn.execute(
                """
                UPDATE subscriptions
                SET chat_id = COALESCE(?, chat_id),
                    username = COALESCE(?, username),
                    full_name = COALESCE(?, full_name),
                    updated_at = ?
                WHERE user_id = ?
                """,
                (chat_id_str, username, full_name, now_iso, user_id_str),
            )
            return get_user_subscription(user_id_str)

        is_owner = TELEGRAM_CHAT_ID and user_id_str == str(TELEGRAM_CHAT_ID)
        if status:
            chosen_status = status
            expires_at = "2099-12-31T23:59:59" if status == "lifetime" else (datetime.now() + timedelta(days=trial_days)).isoformat(timespec="seconds")
            plan = "admin_lifetime" if status == "lifetime" else f"trial_{trial_days}d"
        elif is_owner:
            chosen_status = "lifetime"
            expires_at = "2099-12-31T23:59:59"
            plan = "admin_lifetime"
        else:
            chosen_status = "trial"
            expires_at = (datetime.now() + timedelta(days=trial_days)).isoformat(timespec="seconds")
            plan = f"trial_{trial_days}d"

        conn.execute(
            """
            INSERT INTO subscriptions (
                user_id, chat_id, username, full_name, status, plan,
                started_at, expires_at, payment_provider, amount, currency,
                created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                user_id_str,
                chat_id_str,
                username or "",
                full_name or "",
                chosen_status,
                plan,
                now_iso,
                expires_at,
                "system",
                0.0,
                "UAH",
                now_iso,
                now_iso,
            ),
        )
    return get_user_subscription(user_id_str)


def get_user_subscription(user_id: str | int) -> dict | None:
    user_id_str = str(user_id)
    is_owner = TELEGRAM_CHAT_ID and user_id_str == str(TELEGRAM_CHAT_ID)

    with get_connection() as conn:
        row = conn.execute("SELECT * FROM subscriptions WHERE user_id = ?", (user_id_str,)).fetchone()
        if not row:
            if is_owner:
                return {
                    "user_id": user_id_str,
                    "chat_id": user_id_str,
                    "username": "admin",
                    "full_name": "Administrator",
                    "status": "lifetime",
                    "plan": "admin_lifetime",
                    "is_active": True,
                    "days_left": 9999,
                    "expires_at": "2099-12-31T23:59:59",
                }
            return None

        sub = dict(row)
        now = datetime.now()
        days_left = 0

        if is_owner or sub.get("status") == "lifetime":
            sub["status"] = "lifetime"
            sub["is_active"] = True
            sub["days_left"] = 9999
            return sub

        try:
            exp_dt = datetime.fromisoformat(sub["expires_at"])
            diff = exp_dt - now
            days_left = max(0, diff.days + (1 if diff.seconds > 0 else 0))
            is_active = diff.total_seconds() > 0
        except Exception:
            is_active = False
            days_left = 0

        if not is_active and sub.get("status") in {"trial", "active"}:
            sub["status"] = "expired"
            conn.execute(
                "UPDATE subscriptions SET status = 'expired', updated_at = ? WHERE user_id = ?",
                (now.isoformat(timespec="seconds"), user_id_str),
            )

        sub["is_active"] = is_active
        sub["days_left"] = days_left
        return sub


def is_user_subscribed(user_id: str | int) -> bool:
    if not SUBSCRIPTION_REQUIRED:
        return True
    user_id_str = str(user_id)
    if TELEGRAM_CHAT_ID and user_id_str == str(TELEGRAM_CHAT_ID):
        return True
    sub = get_user_subscription(user_id_str)
    return bool(sub and sub.get("is_active"))


def activate_user_subscription(
    user_id: str | int,
    days: int = 30,
    amount: float = 99.0,
    provider: str = "telegram",
    payment_id: str | None = None,
    currency: str = "UAH",
    chat_id: str | int | None = None,
    username: str | None = None,
    full_name: str | None = None,
) -> dict:
    user_id_str = str(user_id)
    chat_id_str = str(chat_id or user_id)
    now = datetime.now()
    now_iso = now.isoformat(timespec="seconds")

    with get_connection() as conn:
        row = conn.execute("SELECT * FROM subscriptions WHERE user_id = ?", (user_id_str,)).fetchone()

        base_date = now
        if row:
            try:
                curr_exp = datetime.fromisoformat(row["expires_at"])
                if curr_exp > now:
                    base_date = curr_exp
            except Exception:
                base_date = now

        new_expires_dt = base_date + timedelta(days=days)
        new_expires_iso = new_expires_dt.isoformat(timespec="seconds")

        conn.execute(
            """
            INSERT INTO subscriptions (
                user_id, chat_id, username, full_name, status, plan,
                started_at, expires_at, payment_provider, payment_id, amount, currency,
                created_at, updated_at
            )
            VALUES (?, ?, ?, ?, 'active', 'month', ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                chat_id = COALESCE(excluded.chat_id, subscriptions.chat_id),
                username = COALESCE(excluded.username, subscriptions.username),
                full_name = COALESCE(excluded.full_name, subscriptions.full_name),
                status = 'active',
                plan = 'month',
                expires_at = excluded.expires_at,
                payment_provider = excluded.payment_provider,
                payment_id = excluded.payment_id,
                amount = excluded.amount,
                currency = excluded.currency,
                updated_at = excluded.updated_at
            """,
            (
                user_id_str,
                chat_id_str,
                username or "",
                full_name or "",
                now_iso,
                new_expires_iso,
                provider,
                payment_id or "",
                amount,
                currency,
                now_iso,
                now_iso,
            ),
        )

    return get_user_subscription(user_id_str)


def grant_user_subscription(user_id: str | int, days: int = 30, admin_note: str = "admin_grant") -> dict:
    return activate_user_subscription(
        user_id=user_id,
        days=days,
        amount=0.0,
        provider="admin_grant",
        payment_id=admin_note,
    )


def get_all_subscriptions() -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute("SELECT user_id FROM subscriptions ORDER BY expires_at DESC").fetchall()
        results = []
        for r in rows:
            sub = get_user_subscription(r["user_id"])
            if sub:
                results.append(sub)
        return results


def get_active_subscribers() -> list[dict]:
    all_subs = get_all_subscriptions()
    return [s for s in all_subs if s.get("is_active")]


def process_referral(referrer_id: str | int, new_user_id: str | int, bonus_days: int = 7) -> bool:
    ref_id = str(referrer_id).strip()
    new_id = str(new_user_id).strip()
    if not ref_id or not new_id or ref_id == new_id:
        return False

    with get_connection() as conn:
        existing = conn.execute("SELECT id FROM referrals WHERE referred_id = ?", (new_id,)).fetchone()
        if existing:
            return False

        now_iso = datetime.now().isoformat(timespec="seconds")
        try:
            conn.execute(
                "INSERT INTO referrals (referrer_id, referred_id, created_at) VALUES (?, ?, ?)",
                (ref_id, new_id, now_iso),
            )
        except Exception:
            return False

    try:
        activate_user_subscription(
            user_id=ref_id,
            days=bonus_days,
            amount=0.0,
            provider="referral",
            payment_id=f"ref_{new_id}",
            currency="UAH",
        )
        return True
    except Exception:
        return False


def get_referral_stats(user_id: str | int) -> dict:
    uid = str(user_id).strip()
    with get_connection() as conn:
        row = conn.execute("SELECT COUNT(*) AS c FROM referrals WHERE referrer_id = ?", (uid,)).fetchone()
        count = row["c"] if row else 0
    return {"invited_count": count, "bonus_days_earned": count * 7}


def is_project_broadcast(project_id: str | int) -> bool:
    pid = str(project_id).strip()
    with get_connection() as conn:
        row = conn.execute("SELECT project_id FROM channel_posts WHERE project_id = ?", (pid,)).fetchone()
        return bool(row)


def record_channel_broadcast(project_id: str | int, channel_id: str) -> None:
    pid = str(project_id).strip()
    now_iso = datetime.now().isoformat(timespec="seconds")
    with get_connection() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO channel_posts (project_id, channel_id, posted_at) VALUES (?, ?, ?)",
            (pid, str(channel_id), now_iso),
        )


def add_feedback(user_id: str | int, text: str, username: str = "", full_name: str = "") -> int:
    uid = str(user_id).strip()
    clean_text = str(text).strip()
    if not uid or not clean_text:
        return 0
    now_iso = datetime.now().isoformat(timespec="seconds")
    with get_connection() as conn:
        cursor = conn.execute(
            "INSERT INTO feedback (user_id, username, full_name, text, created_at) VALUES (?, ?, ?, ?, ?)",
            (uid, str(username or ""), str(full_name or ""), clean_text, now_iso),
        )
        return cursor.lastrowid or 0


def add_bonus_days(user_id: str | int, days: int = 3, reason: str = "feedback") -> dict:
    return activate_user_subscription(
        user_id=user_id,
        days=days,
        amount=0.0,
        provider=reason,
        payment_id=f"{reason}_{datetime.now().strftime('%Y%m%d%H%M%S')}",
        currency="UAH",
    )


def get_market_digest_stats() -> dict:
    with get_connection() as conn:
        total_projects = conn.execute("SELECT COUNT(*) AS c FROM projects").fetchone()["c"]
        sent_projects = conn.execute("SELECT COUNT(*) AS c FROM projects WHERE status = 'sent'").fetchone()["c"]
        completed_deals = conn.execute(
            "SELECT COUNT(*) AS c, COALESCE(SUM(deal_amount), 0) AS total_sum FROM projects WHERE pipeline_status = 'completed'"
        ).fetchone()

        recent_it = conn.execute(
            "SELECT title, budget, score FROM projects WHERE status = 'sent' ORDER BY created_at DESC LIMIT 5"
        ).fetchall()

        return {
            "total_projects": total_projects,
            "sent_projects": sent_projects,
            "completed_deals_count": completed_deals["c"] if completed_deals else 0,
            "completed_deals_sum": completed_deals["total_sum"] if completed_deals else 0.0,
            "recent_top": [dict(r) for r in recent_it],
        }


def get_recent_feedback(limit: int = 20) -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM feedback ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]





