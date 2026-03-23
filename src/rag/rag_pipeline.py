import re
from collections import Counter

from embeddings.embedding_generator import generate_embedding
from llm.ollama_client import OllamaGenerationError, generate_answer
from processing.text_cleaner import clean_text
from vector_db.vector_store import search

STOP_WORDS = {
    "about",
    "after",
    "also",
    "been",
    "being",
    "between",
    "could",
    "from",
    "have",
    "into",
    "just",
    "more",
    "most",
    "news",
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


def _rerank_documents(docs, query_tokens):
    if not query_tokens:
        return docs

    scored = [
        (_document_score(article, query_tokens), index, article)
        for index, article in enumerate(docs)
    ]
    scored.sort(key=lambda item: (-item[0], item[1]))
    return [article for _, _, article in scored]


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


def answer_question(question, k=3):
    query_tokens = _query_tokens(question)
    query_embedding = generate_embedding(question)
    docs = _rerank_documents(search(query_embedding, k=max(k, 5)), query_tokens)[:k]

    if not docs:
        return {
            "answer": "No relevant articles found in the current knowledge base.",
            "sources": [],
            "related_topics": [],
        }

    lead_article = docs[0]
    lead_title = lead_article.get("title", "Untitled Article")
    lead_passage = _best_passage(lead_article, query_tokens)
    related_titles = [f'"{doc.get("title", "Untitled Article")}"' for doc in docs[1:3]]
    related_topics = _extract_related_topics(docs, query_tokens)

    try:
        answer_text = generate_answer(question, docs)
    except OllamaGenerationError:
        answer_lines = [
            "Based on the indexed articles, here is the clearest match for your question.",
            f'The strongest coverage is "{lead_title}".',
            lead_passage,
        ]

        if related_titles:
            answer_lines.append(
                f"Related coverage also includes {_humanize_list(related_titles)}."
            )

        if related_topics:
            answer_lines.append(
                f"Related topics in the current article set include {_humanize_list(related_topics[:3])}."
            )

        answer_text = " ".join(answer_lines)

    return {
        "answer": answer_text,
        "sources": docs,
        "related_topics": related_topics,
    }
