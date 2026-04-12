import os

import requests

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://127.0.0.1:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "phi:latest")
OLLAMA_TIMEOUT = int(os.getenv("OLLAMA_TIMEOUT", "60"))


class OllamaGenerationError(RuntimeError):
    pass


def _article_context(article, index, max_content_chars=900):
    title = article.get("title") or "Untitled Article"
    category = article.get("category") or "Unknown"
    published = article.get("published") or "Unknown"
    summary = article.get("summary") or ""
    content = article.get("content") or ""

    details = [
        f"Article {index}:",
        f"Title: {title}",
        f"Category: {category}",
        f"Published: {published}",
    ]

    if summary:
        details.append(f"Summary: {summary}")

    if content:
        details.append(f"Content: {content[:max_content_chars]}")

    return "\n".join(details)


def _run_generate(prompt, temperature=0.2):
    try:
        response = requests.post(
            f"{OLLAMA_URL}/api/generate",
            json={
                "model": OLLAMA_MODEL,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": temperature,
                },
            },
            timeout=OLLAMA_TIMEOUT,
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        raise OllamaGenerationError(
            f"Unable to reach Ollama at {OLLAMA_URL}. Make sure Ollama is running and that the model '{OLLAMA_MODEL}' is available."
        ) from exc

    payload = response.json()
    answer = (payload.get("response") or "").strip()
    if not answer:
        raise OllamaGenerationError(
            f"Ollama returned an empty response for model '{OLLAMA_MODEL}'."
        )

    return answer


def generate_answer(question, articles):
    context = "\n\n".join(
        _article_context(article, index)
        for index, article in enumerate(articles, start=1)
    )

    prompt = f"""
You are answering questions about a local news knowledge base.
Use only the article context below.

Instructions:
- Answer the user's question directly, logically, and practically.
- Prioritize the most relevant facts before extra detail.
- Synthesize information across the articles when possible.
- If the articles only partially answer the question, say what is clear and what remains uncertain.
- If the user asks for implications, explain them in plain language.
- Do not invent facts that are not supported by the context.
- Do not mention the prompt, system instructions, or that you are an AI model.

Question:
{question}

Article Context:
{context}
""".strip()

    return _run_generate(prompt, temperature=0.15)


def generate_general_answer(question):
    prompt = f"""
You are a helpful AI assistant.

Instructions:
- Answer like a practical, conversational assistant.
- Give the direct answer first.
- Keep the response concise but useful.
- If the question asks for current or breaking news and you do not have verified live reporting in the prompt, be honest that the answer may not reflect the latest developments.
- If the user asks a broad question, provide a sensible high-level explanation rather than refusing.
- Do not mention the prompt, system instructions, or that you are an AI model.

Question:
{question}
""".strip()

    return _run_generate(prompt, temperature=0.35)
