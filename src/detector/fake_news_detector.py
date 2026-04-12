"""Fake news detection using a pre-trained transformer classifier.

Uses ``hamzab/roberta-fake-news-classification`` from HuggingFace.
The model (~330 MB) is downloaded on first use and cached locally.
"""

from transformers import pipeline

_classifier = None
_classifier_unavailable = False

MODEL_NAME = "hamzab/roberta-fake-news-classification"


def _get_classifier():
    """Lazy-load the fake news classification pipeline."""
    global _classifier, _classifier_unavailable

    if _classifier is None and not _classifier_unavailable:
        try:
            _classifier = pipeline(
                "text-classification",
                model=MODEL_NAME,
                truncation=True,
                max_length=512,
            )
        except Exception:
            _classifier_unavailable = True

    return _classifier


def _truncate_for_model(text, max_words=450):
    """Rough word-level truncation to stay within the 512-token limit."""
    words = text.split()
    if len(words) > max_words:
        words = words[:max_words]
    return " ".join(words)


def detect_fake_news(text):
    """Classify text as real or fake news.

    Returns
    -------
    dict
        ``label`` is one of ``"REAL"``, ``"FAKE"``, or ``"UNKNOWN"``.
        ``confidence`` is a float between 0.0 and 1.0.
    """
    if not text or not text.strip():
        return {"label": "UNKNOWN", "confidence": 0.0}

    classifier = _get_classifier()
    if classifier is None:
        return {"label": "UNKNOWN", "confidence": 0.0}

    truncated = _truncate_for_model(text)

    try:
        results = classifier(truncated)
    except Exception:
        return {"label": "UNKNOWN", "confidence": 0.0}

    if not results:
        return {"label": "UNKNOWN", "confidence": 0.0}

    result = results[0]
    raw_label = (result.get("label") or "").upper().strip()
    confidence = float(result.get("score", 0.0))

    # Normalize label — the model may output various label formats
    if "FAKE" in raw_label or raw_label in ("LABEL_0", "FALSE", "0"):
        label = "FAKE"
    elif "REAL" in raw_label or raw_label in ("LABEL_1", "TRUE", "1"):
        label = "REAL"
    else:
        label = "UNKNOWN"

    return {"label": label, "confidence": round(confidence, 4)}
