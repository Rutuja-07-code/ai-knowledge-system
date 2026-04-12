import faiss
import numpy as np

DIMENSION = 384

index = faiss.IndexFlatL2(DIMENSION)
documents = []


def reset_store():
    global index

    index = faiss.IndexFlatL2(DIMENSION)
    documents.clear()


def add_embedding(embedding, document):
    vector = np.asarray([embedding], dtype="float32")
    index.add(vector)
    documents.append(document)


def build_store(items):
    reset_store()

    for embedding, document in items:
        add_embedding(embedding, document)


def search(query_embedding, k=3):
    return [item["document"] for item in search_with_scores(query_embedding, k=k)]


def search_with_scores(query_embedding, k=3):
    if not documents or index.ntotal == 0:
        return []

    result_count = min(k, len(documents))
    query_vector = np.asarray([query_embedding], dtype="float32")
    distances, indices = index.search(query_vector, result_count)

    results = []
    for rank, idx in enumerate(indices[0]):
        if idx == -1:
            continue
        if idx < len(documents):
            results.append(
                {
                    "document": documents[idx],
                    "distance": float(distances[0][rank]),
                }
            )

    return results


def document_count():
    return len(documents)
