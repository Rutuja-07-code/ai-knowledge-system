import hashlib
import re

# import numpy as np

# MODEL_NAME = "all-MiniLM-L6-v2"
# EMBEDDING_DIMENSION = 384

# try:
#     from sentence_transformers import SentenceTransformer
# except ImportError:
#     SentenceTransformer = None

# _model = None
# _model_load_failed = False


# def _load_model():
#     global _model
#     global _model_load_failed

#     if _model is not None or _model_load_failed or SentenceTransformer is None:
#         return _model

#     try:
#         _model = SentenceTransformer(MODEL_NAME, local_files_only=True)
#     except Exception:
#         _model_load_failed = True
#         _model = None

#     return _model


# def _fallback_embedding(text):
#     vector = np.zeros(EMBEDDING_DIMENSION, dtype="float32")
#     tokens = re.findall(r"\b\w+\b", text.lower())

#     for token in tokens:
#         digest = hashlib.sha256(token.encode("utf-8")).digest()
#         index = int.from_bytes(digest[:4], "big") % EMBEDDING_DIMENSION
#         sign = 1.0 if digest[4] % 2 == 0 else -1.0
#         vector[index] += sign

#     norm = np.linalg.norm(vector)

#     if norm == 0:
#         return vector

#     return vector / norm


# def generate_embedding(text):
#     model = _load_model()

#     if model is None:
#         return _fallback_embedding(text)

#     embedding = model.encode(text, normalize_embeddings=True)

#     return np.asarray(embedding, dtype="float32")

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity


def preprocess(text):
    text = text.lower()
    text = re.sub(r"[^\w\s]", "", text)
    return text


def search(query, articles):
    # Step 1: Prepare text data
    texts = [preprocess(a.get("content", "")) for a in articles]
    query = preprocess(query)

    # Step 2: Vectorize
    vectorizer = TfidfVectorizer(stop_words="english")
    vectors = vectorizer.fit_transform(texts + [query])

    # Step 3: Compute similarity
    similarity = cosine_similarity(vectors[-1], vectors[:-1])

    # Step 4: Get best match
    best_index = similarity.argmax()

    return articles[best_index]

