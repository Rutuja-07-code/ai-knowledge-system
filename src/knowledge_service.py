from datetime import datetime, timezone
import json
import os
from pathlib import Path

from collector.rss_collector import (
    collect_news,
    get_available_interests,
    normalize_interest_keys,
)
from database.article_store import ArticleStore
from embeddings.embedding_generator import generate_embedding
from processing.text_cleaner import clean_text
from rag.rag_pipeline import answer_question
from summarizer.summarizer import summarize, summarize_article as _summarize_text
from vector_db.vector_store import add_embedding, document_count, reset_store

BASE_DIR = Path(__file__).resolve().parent.parent
ARTICLES_PATH = Path(
    os.getenv("AI_KNOWLEDGE_LEGACY_ARTICLES_PATH", str(BASE_DIR / "articles.json"))
)
DATABASE_PATH = Path(
    os.getenv("AI_KNOWLEDGE_DB_PATH", str(BASE_DIR / "data" / "knowledge.db"))
)
ENABLE_LEGACY_IMPORT = os.getenv("AI_KNOWLEDGE_ENABLE_LEGACY_IMPORT", "").lower() in {
    "1",
    "true",
    "yes",
    "on",
}
REFRESH_ON_STARTUP = os.getenv("AI_KNOWLEDGE_REFRESH_ON_STARTUP", "false").lower() in {
    "1",
    "true",
    "yes",
    "on",
}
STARTUP_REFRESH_TTL_MINUTES = int(
    os.getenv("AI_KNOWLEDGE_STARTUP_REFRESH_TTL_MINUTES", "30")
)


class KnowledgeService:
    def __init__(self, db_path=DATABASE_PATH, legacy_articles_path=ARTICLES_PATH):
        self.store = ArticleStore(
            db_path=db_path,
            legacy_json_path=legacy_articles_path if ENABLE_LEGACY_IMPORT else None,
        )
        self.available_interests = get_available_interests()
        self.articles = []
        self.last_updated = None
        self.selected_interests = self._load_selected_interests()
        self.interest_keywords = self._load_interest_keywords()
        self.load_articles()
        self._bootstrap_live_articles()

    def load_articles(self):
        self.articles = self.store.load_articles()
        self.last_updated = self.store.get_last_updated()
        self.selected_interests = self._load_selected_interests()
        self.interest_keywords = self._load_interest_keywords()
        self._rebuild_index()
        return self.articles

    def refresh_articles(self, selected_interests=None, interest_keywords=None):
        interest_keys = self._normalize_selected_interests(selected_interests)
        keywords = self._normalize_interest_keywords(interest_keywords)
        # Always collect every configured feed so each category can populate
        # the dashboard. Selected interests are still saved and used by the UI
        # to prioritize relevant stories rather than hiding other categories.
        articles = collect_news()

        if not articles:
            raise RuntimeError(
                "Unable to refresh articles right now. The RSS feeds may be unavailable."
            )

        filtered_articles = self._filter_articles_by_keywords(articles, keywords)
        if filtered_articles:
            articles_to_process = filtered_articles
        else:
            articles_to_process = articles

        enriched_articles = []
        for article in articles_to_process:
            cleaned_text = clean_text(
                " ".join(
                    [
                        article.get("title", ""),
                        article.get("content", ""),
                    ]
                )
            )
            summary = summarize(cleaned_text)
            article_copy = dict(article)
            article_copy["summary"] = summary
            enriched_articles.append(article_copy)

        now = datetime.now(timezone.utc)
        self.store.replace_articles(enriched_articles, fetched_at=now.isoformat())
        self.store.set_metadata("selected_interests", json.dumps(interest_keys))
        self.store.set_metadata("interest_keywords", json.dumps(keywords))
        self.store.set_metadata("data_source", "live_rss")
        self.articles = self.store.load_articles()
        self.last_updated = now
        self.selected_interests = interest_keys
        self.interest_keywords = keywords
        self._rebuild_index()
        return {
            "articles": self.articles,
            "keywords_applied": bool(keywords and filtered_articles),
            "keywords_fallback": bool(keywords and not filtered_articles),
        }

    def _rebuild_index(self):
        reset_store()

        for article in self.articles:
            searchable_text = " ".join(
                [
                    article.get("title", ""),
                    article.get("summary", ""),
                    article.get("content", ""),
                ]
            ).strip()

            if not searchable_text:
                continue

            embedding = generate_embedding(searchable_text)
            add_embedding(embedding, article)

    def ask(self, question):
        return answer_question(question)

    def summarize_article(self, link):
        """Generate an on-demand transformer summary for a single article."""
        article = self.store.get_article_by_link(link)
        if not article:
            return None

        # Return cached summary if it looks like a real transformer summary
        # (more than 30 words means it was already generated, not just a preview)
        existing_summary = (article.get("summary") or "").strip()
        if existing_summary and len(existing_summary.split()) > 30:
            return existing_summary

        # Build input text from title + content
        text = clean_text(
            " ".join(
                [
                    article.get("title", ""),
                    article.get("content", ""),
                ]
            )
        )

        summary = _summarize_text(text)

        # Persist so future requests are instant
        self.store.update_article_summary(link, summary)

        # Update the in-memory article list too
        for cached_article in self.articles:
            if cached_article.get("link") == link:
                cached_article["summary"] = summary
                break

        return summary

    def _related_topics_from_sources(self, sources, limit=5):
        topics = []
        seen = set()

        for article in sources:
            category = (article.get("category") or "").strip()
            if category and category.lower() not in seen:
                topics.append(category)
                seen.add(category.lower())
                if len(topics) >= limit:
                    return topics

            for token in clean_text(article.get("title") or "").split():
                if len(token) <= 3 or token in seen:
                    continue

                topics.append(token.title())
                seen.add(token)
                if len(topics) >= limit:
                    return topics

        return topics

    def get_status(self):
        return {
            "article_count": len(self.articles),
            "indexed_count": document_count(),
            "last_updated": self.last_updated.isoformat() if self.last_updated else None,
            "database_path": str(self.store.db_path),
            "data_source": self.store.get_metadata("data_source") or "unknown",
            "available_interests": self.available_interests,
            "selected_interests": self.selected_interests,
            "interest_keywords": self.interest_keywords,
        }

    def _bootstrap_live_articles(self):
        if not self._should_refresh_on_startup():
            return

        try:
            self.refresh_articles(
                selected_interests=self.selected_interests,
                interest_keywords=self.interest_keywords,
            )
        except Exception:
            # Keep cached data if live refresh is unavailable during startup.
            return

    def _should_refresh_on_startup(self):
        if not REFRESH_ON_STARTUP:
            return False

        if not self.articles:
            return True

        if (self.store.get_metadata("data_source") or "").strip().lower() != "live_rss":
            return True

        if not self.last_updated:
            return True

        refresh_age = datetime.now(timezone.utc) - self.last_updated.astimezone(
            timezone.utc
        )
        return refresh_age.total_seconds() >= STARTUP_REFRESH_TTL_MINUTES * 60

    def _load_selected_interests(self):
        raw_value = self.store.get_metadata("selected_interests")
        if not raw_value:
            return [interest["key"] for interest in self.available_interests]

        try:
            saved_value = json.loads(raw_value)
        except json.JSONDecodeError:
            return [interest["key"] for interest in self.available_interests]

        normalized = normalize_interest_keys(saved_value)
        if not normalized:
            return [interest["key"] for interest in self.available_interests]

        return normalized

    def _normalize_selected_interests(self, selected_interests):
        if selected_interests is None:
            return [interest["key"] for interest in self.available_interests]

        normalized = normalize_interest_keys(selected_interests)
        if not normalized:
            raise ValueError("Please select at least one area of interest.")

        return normalized

    def _load_interest_keywords(self):
        raw_value = self.store.get_metadata("interest_keywords")
        if not raw_value:
            return []

        try:
            saved_value = json.loads(raw_value)
        except json.JSONDecodeError:
            return []

        return self._normalize_interest_keywords(saved_value)

    def _normalize_interest_keywords(self, interest_keywords):
        if interest_keywords is None:
            return self.interest_keywords if hasattr(self, "interest_keywords") else []

        if isinstance(interest_keywords, str):
            values = interest_keywords.split(",")
        else:
            values = interest_keywords

        normalized = []
        seen = set()

        for keyword in values:
            value = clean_text(str(keyword)).strip()
            if not value or value in seen:
                continue

            normalized.append(value)
            seen.add(value)

        return normalized

    def _filter_articles_by_keywords(self, articles, keywords):
        if not keywords:
            return articles

        matched_articles = []
        for article in articles:
            haystack = clean_text(
                " ".join(
                    [
                        article.get("title", ""),
                        article.get("content", ""),
                    ]
                )
            )
            if any(keyword in haystack for keyword in keywords):
                matched_articles.append(article)

        return matched_articles
