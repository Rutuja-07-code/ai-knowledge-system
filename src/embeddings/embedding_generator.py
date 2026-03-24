import hashlib
import re

import numpy as np

MODEL_NAME = "all-MiniLM-L6-v2"
EMBEDDING_DIMENSION = 384

try:
    from sentence_transformers import SentenceTransformer
except ImportError:
    SentenceTransformer = None

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

def search(query, articles):
    texts = [a["content"] for a in articles]

    vectorizer = TfidfVectorizer()
    vectors = vectorizer.fit_transform(texts + [query])

    similarity = cosine_similarity(vectors[-1], vectors[:-1])
    best_index = similarity.argmax()

    return articles[best_index]

_model = None
_model_load_failed = False


def _load_model():
    global _model
    global _model_load_failed

    if _model is not None or _model_load_failed or SentenceTransformer is None:
        return _model

    try:
        _model = SentenceTransformer(MODEL_NAME, local_files_only=True)
    except Exception:
        _model_load_failed = True
        _model = None

    return _model


def _fallback_embedding(text):
    vector = np.zeros(EMBEDDING_DIMENSION, dtype="float32")
    tokens = re.findall(r"\b\w+\b", text.lower())

    for token in tokens:
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        index = int.from_bytes(digest[:4], "big") % EMBEDDING_DIMENSION
        sign = 1.0 if digest[4] % 2 == 0 else -1.0
        vector[index] += sign

    norm = np.linalg.norm(vector)

    if norm == 0:
        return vector

    return vector / norm


def generate_embedding(text):
    model = _load_model()

    if model is None:
        return _fallback_embedding(text)

    embedding = model.encode(text, normalize_embeddings=True)

    return np.asarray(embedding, dtype="float32")
