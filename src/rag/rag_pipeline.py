import re
from collections import Counter

from embeddings.embedding_generator import generate_embedding
from llm.ollama_client import (
    OllamaGenerationError,
    generate_answer,
    generate_general_answer,
)
from processing.text_cleaner import clean_text
from vector_db.vector_store import search_with_scores

STOP_WORDS = {
    "actually",
    "about",
    "any",
    "after",
    "also",
    "around",
    "because",
    "been",
    "being",
    "between",
    "breaking",
    "current",
    "could",
    "explain",
    "from",
    "have",
    "help",
    "hows",
    "into",
    "just",
    "latest",
    "make",
    "more",
    "most",
    "news",
    "now",
    "please",
    "recent",
    "some",
    "than",
    "that",
    "their",
    "them",
    "then",
    "there",
    "these",
    "they",
    "this",
    "topic",
    "what",
    "when",
    "where",
    "which",
    "while",
    "with",
    "would",
    "your",
}
NEWS_QUERY_TERMS = {
    "breaking",
    "current",
    "headline",
    "headlines",
    "happening",
    "latest",
    "news",
    "recent",
    "today",
    "update",
    "updates",
}


def _article_snippet(article):
    content = (article.get("content") or "").strip()
    if content:
        return content[:220].strip()

    return "No summary is available for this article yet."


def _query_tokens(question):
    return {
        token
        for token in clean_text(question).split()
        if len(token) > 2 and token not in STOP_WORDS
    }


def _humanize_list(items):
    filtered_items = [item for item in items if item]
    if not filtered_items:
        return ""
    if len(filtered_items) == 1:
        return filtered_items[0]
    if len(filtered_items) == 2:
        return f"{filtered_items[0]} and {filtered_items[1]}"
    return f'{", ".join(filtered_items[:-1])}, and {filtered_items[-1]}'


def _sentence_candidates(article):
    candidates = []
    for text in [article.get("summary") or "", article.get("content") or ""]:
        for sentence in re.split(r"(?<=[.!?])\s+", text.strip()):
            cleaned_sentence = sentence.strip()
            if cleaned_sentence:
                candidates.append(cleaned_sentence)
    return candidates


def _best_passage(article, query_tokens):
    candidates = _sentence_candidates(article)
    if not candidates:
        return _article_snippet(article)

    def sentence_score(sentence):
        normalized = clean_text(sentence)
        overlap = sum(token in normalized for token in query_tokens)
        ideal_length_penalty = abs(len(sentence) - 180)
        return (overlap, -ideal_length_penalty)

    best_sentence = max(candidates, key=sentence_score)
    return best_sentence


def _document_score(article, query_tokens):
    haystack = clean_text(
        " ".join(
            [
                article.get("title") or "",
                article.get("summary") or "",
                article.get("content") or "",
            ]
        )
    )
    title_haystack = clean_text(article.get("title") or "")
    title_overlap = sum(token in title_haystack for token in query_tokens)
    body_overlap = sum(token in haystack for token in query_tokens)
    return (title_overlap * 3) + body_overlap


def _semantic_score(distance):
    return 1.0 / (1.0 + max(distance, 0.0))


def _rerank_documents(scored_docs, query_tokens):
    reranked = []

    for index, item in enumerate(scored_docs):
        article = item["document"]
        lexical_score = _document_score(article, query_tokens) if query_tokens else 0
        combined_score = (_semantic_score(item["distance"]) * 5) + lexical_score
        reranked.append(
            {
                "document": article,
                "distance": item["distance"],
                "lexical_score": lexical_score,
                "combined_score": combined_score,
                "original_rank": index,
            }
        )

    reranked.sort(
        key=lambda item: (
            -item["combined_score"],
            item["distance"],
            item["original_rank"],
        )
    )
    return reranked


def _extract_related_topics(docs, query_tokens, limit=5):
    counter = Counter()
    original_labels = {}

    for article in docs:
        category = (article.get("category") or "").strip()
        if category:
            key = clean_text(category)
            counter[key] += 3
            original_labels[key] = category

        for token in clean_text(article.get("title") or "").split():
            if len(token) <= 3 or token in STOP_WORDS or token in query_tokens:
                continue
            counter[token] += 1
            original_labels.setdefault(token, token.title())

    return [original_labels[key] for key, _ in counter.most_common(limit)]


def _combine_key_points(docs, query_tokens, limit=3):
    passages = []
    seen = set()

    for article in docs:
        passage = _best_passage(article, query_tokens)
        normalized = clean_text(passage)
        if not normalized or normalized in seen:
            continue

        passages.append(passage)
        seen.add(normalized)
        if len(passages) >= limit:
            break

    return passages


def _is_news_question(question, query_tokens):
    normalized_question = clean_text(question)
    return bool(NEWS_QUERY_TERMS.intersection(query_tokens)) or any(
        phrase in normalized_question
        for phrase in [
            "what happened",
            "what's happening",
            "whats happening",
            "what is happening",
            "in the news",
        ]
    )


def _has_grounded_support(reranked_docs, query_tokens):
    if not reranked_docs:
        return False

    best = reranked_docs[0]
    if not query_tokens:
        return best["distance"] <= 1.05

    if best["lexical_score"] >= 3:
        return True

    if best["distance"] <= 0.95:
        return True

    combined_overlap = sum(item["lexical_score"] for item in reranked_docs[:3])
    return combined_overlap >= 4


def _fallback_answer(question, docs, query_tokens):
    lead_title = docs[0].get("title", "an article in the knowledge base")
    key_points = _combine_key_points(docs, query_tokens)
    related_topics = _extract_related_topics(docs, query_tokens)

    answer_lines = [
        f"Here’s the clearest answer I can build from the current news coverage about {question.strip() or 'your question'}.",
    ]

    if key_points:
        answer_lines.append("The strongest reporting suggests: " + " ".join(key_points[:2]))

    if len(docs) > 1:
        answer_lines.append(
            f'I also checked related coverage beyond "{lead_title}" to keep the answer grounded in multiple articles.'
        )

    if related_topics:
        answer_lines.append(
            f"Related themes in the same coverage include {_humanize_list(related_topics[:3])}."
        )

    return " ".join(answer_lines)


def _general_fallback_answer(question, news_mode=False):
    if news_mode:
        return (
            "I could not verify a closely matching article in the current indexed news, "
            "so I cannot give a reliable latest-news answer from this knowledge base right now."
        )

    return (
        "I could not ground that question in the indexed articles, and the local language model "
        "is unavailable right now for a broader assistant-style answer."
    )


def _prefix_general_answer(answer_text, news_mode=False):
    if not news_mode:
        return answer_text

    return (
        "I could not verify this in the current indexed news feed, so this is a general answer "
        "and may miss the latest developments. "
        + answer_text
    )


def answer_question(question, k=3):
    query_tokens = _query_tokens(question)
    news_mode = _is_news_question(question, query_tokens)
    query_embedding = generate_embedding(question)
    scored_docs = search_with_scores(query_embedding, k=max(k, 5))
    if not scored_docs:
        try:
            answer_text = _prefix_general_answer(
                generate_general_answer(question),
                news_mode=news_mode,
            )
        except OllamaGenerationError:
            answer_text = _general_fallback_answer(question, news_mode=news_mode)

        return {
            "answer": answer_text,
            "sources": [],
            "related_topics": [],
        }

    reranked_docs = _rerank_documents(scored_docs, query_tokens)
    docs = [item["document"] for item in reranked_docs[:k]]

    related_topics = _extract_related_topics(docs, query_tokens)

    if _has_grounded_support(reranked_docs, query_tokens):
        try:
            answer_text = generate_answer(question, docs)
        except OllamaGenerationError:
            answer_text = _fallback_answer(question, docs, query_tokens)

        return {
            "answer": answer_text,
            "sources": docs,
            "related_topics": related_topics,
        }

    try:
        answer_text = _prefix_general_answer(
            generate_general_answer(question),
            news_mode=news_mode,
        )
    except OllamaGenerationError:
        if docs and news_mode:
            answer_text = _fallback_answer(question, docs, query_tokens)
        else:
            answer_text = _general_fallback_answer(question, news_mode=news_mode)

    return {
        "answer": answer_text,
        "sources": docs if news_mode else [],
        "related_topics": related_topics,
    }
