import json
import sqlite3
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path


class ArticleStore:
    def __init__(self, db_path, legacy_json_path=None):
        self.db_path = Path(db_path)
        self.legacy_json_path = Path(legacy_json_path) if legacy_json_path else None
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()
        self._import_legacy_articles()

    def _connect(self):
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self):
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS articles (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    link TEXT NOT NULL UNIQUE,
                    category TEXT,
                    published TEXT,
                    content TEXT,
                    content_source TEXT,
                    summary TEXT,
                    fetched_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS metadata (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS user_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_type TEXT NOT NULL,
                    article_link TEXT,
                    query TEXT,
                    category TEXT,
                    timestamp TEXT NOT NULL
                )
                """
            )
            columns = {
                row["name"]
                for row in connection.execute("PRAGMA table_info(articles)").fetchall()
            }
            if "category" not in columns:
                connection.execute("ALTER TABLE articles ADD COLUMN category TEXT")

    def _import_legacy_articles(self):
        if not self.legacy_json_path or not self.legacy_json_path.exists():
            return

        if self.count_articles() > 0:
            return

        with self.legacy_json_path.open("r", encoding="utf-8") as file:
            articles = json.load(file)

        if not articles:
            return

        fetched_at = datetime.fromtimestamp(
            self.legacy_json_path.stat().st_mtime,
            tz=timezone.utc,
        ).isoformat()
        self.replace_articles(articles, fetched_at=fetched_at)
        self.set_metadata("data_source", "legacy_json")

    def count_articles(self):
        with self._connect() as connection:
            row = connection.execute("SELECT COUNT(*) AS count FROM articles").fetchone()
        return int(row["count"])

    def load_articles(self):
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT
                    title,
                    link,
                    category,
                    published,
                    content,
                    content_source,
                    summary,
                    fetched_at
                FROM articles
                ORDER BY
                    CASE WHEN published IS NULL OR published = '' THEN 1 ELSE 0 END,
                    published DESC,
                    id DESC
                """
            ).fetchall()

        articles = [dict(row) for row in rows]
        articles.sort(key=self._article_sort_key, reverse=True)
        return articles

    def replace_articles(self, articles, fetched_at=None):
        timestamp = fetched_at or datetime.now(timezone.utc).isoformat()
        normalized_articles = []

        for article in articles:
            normalized_articles.append(
                {
                    "title": article.get("title", "Untitled Article"),
                    "link": article.get("link", ""),
                    "category": article.get("category", ""),
                    "published": article.get("published", ""),
                    "content": article.get("content", ""),
                    "content_source": article.get("content_source", ""),
                    "summary": article.get("summary", ""),
                    "fetched_at": article.get("fetched_at", timestamp),
                }
            )

        with self._connect() as connection:
            connection.execute("DELETE FROM articles")
            connection.executemany(
                """
                INSERT INTO articles (
                    title,
                    link,
                    category,
                    published,
                    content,
                    content_source,
                    summary,
                    fetched_at
                )
                VALUES (
                    :title,
                    :link,
                    :category,
                    :published,
                    :content,
                    :content_source,
                    :summary,
                    :fetched_at
                )
                """,
                normalized_articles,
            )
            connection.execute(
                """
                INSERT INTO metadata (key, value)
                VALUES ('last_updated', ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
                """,
                (timestamp,),
            )

    def get_last_updated(self):
        row = self.get_metadata("last_updated")

        if not row:
            return None

        try:
            return datetime.fromisoformat(row)
        except ValueError:
            return None

    def get_metadata(self, key):
        with self._connect() as connection:
            row = connection.execute(
                "SELECT value FROM metadata WHERE key = ?",
                (key,),
            ).fetchone()

        if not row:
            return None

        return row["value"]

    def set_metadata(self, key, value):
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO metadata (key, value)
                VALUES (?, ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
                """,
                (key, value),
            )

    def get_article_by_link(self, link):
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT
                    title,
                    link,
                    category,
                    published,
                    content,
                    content_source,
                    summary,
                    fetched_at
                FROM articles
                WHERE link = ?
                """,
                (link,),
            ).fetchone()

        if not row:
            return None

        return dict(row)

    def update_article_summary(self, link, summary):
        with self._connect() as connection:
            connection.execute(
                "UPDATE articles SET summary = ? WHERE link = ?",
                (summary, link),
            )

    # ---- User Event Tracking ----

    def add_event(self, event_type, article_link=None, query=None, category=None):
        """Record a user click or search event."""
        timestamp = datetime.now(timezone.utc).isoformat()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO user_events (event_type, article_link, query, category, timestamp)
                VALUES (?, ?, ?, ?, ?)
                """,
                (event_type, article_link, query, category, timestamp),
            )

    def get_recent_events(self, event_type=None, limit=50):
        """Fetch recent user events, optionally filtered by type."""
        with self._connect() as connection:
            if event_type:
                rows = connection.execute(
                    """
                    SELECT event_type, article_link, query, category, timestamp
                    FROM user_events
                    WHERE event_type = ?
                    ORDER BY id DESC
                    LIMIT ?
                    """,
                    (event_type, limit),
                ).fetchall()
            else:
                rows = connection.execute(
                    """
                    SELECT event_type, article_link, query, category, timestamp
                    FROM user_events
                    ORDER BY id DESC
                    LIMIT ?
                    """,
                    (limit,),
                ).fetchall()
        return [dict(row) for row in rows]

    def get_click_history(self, limit=20):
        """Return recently clicked article links."""
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT DISTINCT article_link
                FROM user_events
                WHERE event_type = 'click' AND article_link IS NOT NULL
                ORDER BY id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [row["article_link"] for row in rows]

    def get_search_history(self, limit=10):
        """Return recent search queries."""
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT DISTINCT query
                FROM user_events
                WHERE event_type = 'search' AND query IS NOT NULL AND query != ''
                ORDER BY id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [row["query"] for row in rows]

    def get_category_counts(self):
        """Aggregate click counts by category."""
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT LOWER(category) AS cat, COUNT(*) AS cnt
                FROM user_events
                WHERE event_type = 'click'
                  AND category IS NOT NULL
                  AND category != ''
                GROUP BY LOWER(category)
                ORDER BY cnt DESC
                """
            ).fetchall()
        return {row["cat"]: row["cnt"] for row in rows}

    def get_clicked_articles(self, limit=20):
        """Return full article dicts for recently clicked articles."""
        clicked_links = self.get_click_history(limit=limit)
        if not clicked_links:
            return []

        placeholders = ", ".join("?" for _ in clicked_links)
        with self._connect() as connection:
            rows = connection.execute(
                f"""
                SELECT title, link, category, published, content,
                       content_source, summary, fetched_at
                FROM articles
                WHERE link IN ({placeholders})
                """,
                clicked_links,
            ).fetchall()
        return [dict(row) for row in rows]

    def _article_sort_key(self, article):
        return (
            self._parse_datetime(article.get("published")),
            self._parse_datetime(article.get("fetched_at")),
        )

    def _parse_datetime(self, value):
        if not value:
            return datetime.min.replace(tzinfo=timezone.utc)

        try:
            parsed = parsedate_to_datetime(value)
            if parsed.tzinfo is None:
                return parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc)
        except (TypeError, ValueError, IndexError, OverflowError):
            pass

        try:
            parsed = datetime.fromisoformat(value)
            if parsed.tzinfo is None:
                return parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc)
        except ValueError:
            return datetime.min.replace(tzinfo=timezone.utc)
