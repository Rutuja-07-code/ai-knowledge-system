"""Recommendation engine — personalized article suggestions.

Uses the user's click/search history to build a profile vector,
then finds the most similar unread articles via FAISS.
"""

import numpy as np

from embeddings.embedding_generator import generate_embedding, EMBEDDING_DIMENSION
from processing.text_cleaner import clean_text
from vector_db.vector_store import search_with_scores


def _article_text(article):
    """Combine article fields into a single searchable string."""
    return " ".join(
        [
            article.get("title", ""),
            article.get("summary", ""),
            article.get("content", ""),
        ]
    ).strip()


def _build_profile_vector(clicked_articles):
    """Average the embeddings of clicked articles into a user profile vector."""
    if not clicked_articles:
        return None

    vectors = []
    for article in clicked_articles:
        text = _article_text(article)
        if not text:
            continue
        embedding = generate_embedding(text)
        vectors.append(embedding)

    if not vectors:
        return None

    profile = np.mean(vectors, axis=0).astype("float32")
    norm = np.linalg.norm(profile)
    if norm > 0:
        profile = profile / norm
    return profile


def _boost_by_categories(results, category_counts):
    """Boost scores for articles in the user's most-clicked categories."""
    if not category_counts:
        return results

    max_count = max(category_counts.values()) if category_counts else 1

    boosted = []
    for item in results:
        article = item["document"]
        category = clean_text(article.get("category", "")).strip().lower()
        boost = 0.0
        if category in category_counts:
            # Normalize boost to 0–0.3 range
            boost = 0.3 * (category_counts[category] / max_count)

        semantic_score = 1.0 / (1.0 + max(item["distance"], 0.0))
        combined = semantic_score + boost

        boosted.append(
            {
                "article": article,
                "score": round(combined, 4),
                "match_pct": min(int(combined * 100), 99),
            }
        )

    boosted.sort(key=lambda x: -x["score"])
    return boosted


def get_recommendations(
    clicked_articles,
    clicked_links,
    category_counts,
    limit=8,
):
    """Generate personalized article recommendations.

    Parameters
    ----------
    clicked_articles : list[dict]
        Recently clicked articles (full article dicts).
    clicked_links : set[str]
        Links the user has already clicked (to exclude from results).
    category_counts : dict[str, int]
        Category → click count mapping for boosting.
    limit : int
        Maximum number of recommendations to return.

    Returns
    -------
    list[dict]
        Each dict has ``article``, ``score``, and ``match_pct`` keys.
    """
    profile_vector = _build_profile_vector(clicked_articles)
    if profile_vector is None:
        return []

    # Fetch more than needed so we can filter out already-clicked articles
    results = search_with_scores(profile_vector, k=limit + len(clicked_links) + 5)
    if not results:
        return []

    # Remove articles the user already clicked
    filtered = [
        item
        for item in results
        if item["document"].get("link") not in clicked_links
    ]

    boosted = _boost_by_categories(filtered, category_counts)
    return boosted[:limit]
