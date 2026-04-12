from transformers import pipeline

_summarization_pipeline = None
_summarization_unavailable = False


def _get_pipeline():
    """Lazy-load the BART-large-CNN summarization pipeline.

    The model (~1.6 GB) is downloaded on first call and cached locally
    by HuggingFace for all subsequent runs.
    """
    global _summarization_pipeline, _summarization_unavailable

    if _summarization_pipeline is None and not _summarization_unavailable:
        try:
            _summarization_pipeline = pipeline(
                "summarization",
                model="facebook/bart-large-cnn",
            )
        except Exception:
            _summarization_unavailable = True

    return _summarization_pipeline


def _fallback_summary(text, word_limit):
    words = text.split()
    if len(words) <= word_limit:
        return " ".join(words)
    return " ".join(words[:word_limit]) + "..."


def _truncate_for_model(text, max_tokens=1024):
    """Rough truncation to stay within the BART 1024-token input limit.

    A simple word split is used instead of the real tokenizer to keep
    this fast — BART's BPE tokens are roughly 0.75 words on average,
    so capping at ~900 words is a safe approximation.
    """
    words = text.split()
    if len(words) > 900:
        words = words[:900]
    return " ".join(words)


def summarize(text):
    """Generate a concise summary used during bulk article refresh.

    Returns the first 25 words as a lightweight preview when the text
    is too short for the transformer, or a full model-generated summary
    otherwise.
    """
    if not text or not text.strip():
        return ""

    words = text.split()
    if len(words) < 30:
        return " ".join(words)

    truncated = _truncate_for_model(text)
    pipe = _get_pipeline()
    if pipe is None:
        return _fallback_summary(truncated, 40)

    try:
        result = pipe(
            truncated,
            max_length=150,
            min_length=40,
            do_sample=False,
        )
    except Exception:
        return _fallback_summary(truncated, 40)
    return result[0]["summary_text"]


def summarize_article(text):
    """Generate a detailed on-demand summary for a single article.

    Called when a user explicitly requests a summary through the UI.
    Uses a slightly longer max_length for richer output.
    """
    if not text or not text.strip():
        return "No content available to summarize."

    words = text.split()
    if len(words) < 30:
        return text.strip()

    truncated = _truncate_for_model(text)
    pipe = _get_pipeline()
    if pipe is None:
        return _fallback_summary(truncated, 80)

    try:
        result = pipe(
            truncated,
            max_length=200,
            min_length=50,
            do_sample=False,
        )
    except Exception:
        return _fallback_summary(truncated, 80)
    return result[0]["summary_text"]
