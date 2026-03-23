"""
Embedding generation pipeline for AgentDB.

Uses sentence-transformers with the all-MiniLM-L6-v2 model (384 dimensions)
for local embedding generation with no external API calls.
"""

import struct
import numpy as np

_model = None
_model_name = None


def get_model(model_name="all-MiniLM-L6-v2"):
    """
    Lazy-load and cache the sentence-transformers model.

    Args:
        model_name: Name of the sentence-transformers model.

    Returns:
        SentenceTransformer model instance.
    """
    global _model, _model_name
    if _model is None or _model_name != model_name:
        from sentence_transformers import SentenceTransformer
        _model = SentenceTransformer(model_name)
        _model_name = model_name
    return _model


def generate_embedding(text, model_name="all-MiniLM-L6-v2"):
    """
    Generate a 384-dimensional embedding vector for the given text.

    Args:
        text: Input text string.
        model_name: Name of the sentence-transformers model.

    Returns:
        numpy array of shape (384,) with float32 values.
    """
    model = get_model(model_name)
    embedding = model.encode(text, convert_to_numpy=True)
    return embedding.astype(np.float32)


def generate_embeddings_batch(texts, model_name="all-MiniLM-L6-v2", batch_size=32):
    """
    Generate embeddings for multiple texts in batches.

    Args:
        texts: List of input text strings.
        model_name: Name of the sentence-transformers model.
        batch_size: Number of texts to process at once.

    Returns:
        numpy array of shape (len(texts), 384) with float32 values.
    """
    model = get_model(model_name)
    embeddings = model.encode(texts, convert_to_numpy=True, batch_size=batch_size)
    return embeddings.astype(np.float32)


def embedding_to_blob(embedding):
    """
    Convert a numpy embedding array to a bytes blob for SQLite storage.

    Args:
        embedding: numpy array of float32 values.

    Returns:
        bytes object suitable for SQLite BLOB column.
    """
    return embedding.tobytes()


def blob_to_embedding(blob):
    """
    Convert a SQLite BLOB back to a numpy embedding array.

    Args:
        blob: bytes object from SQLite BLOB column.

    Returns:
        numpy array of float32 values.
    """
    return np.frombuffer(blob, dtype=np.float32)


def cosine_similarity(vec_a, vec_b):
    """
    Compute cosine similarity between two embedding vectors.

    Args:
        vec_a: numpy array (or BLOB that will be converted).
        vec_b: numpy array (or BLOB that will be converted).

    Returns:
        float cosine similarity score between -1.0 and 1.0.
    """
    if isinstance(vec_a, (bytes, memoryview)):
        vec_a = blob_to_embedding(vec_a)
    if isinstance(vec_b, (bytes, memoryview)):
        vec_b = blob_to_embedding(vec_b)
    dot = np.dot(vec_a, vec_b)
    norm_a = np.linalg.norm(vec_a)
    norm_b = np.linalg.norm(vec_b)
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return float(dot / (norm_a * norm_b))


def semantic_search(query_embedding, candidates, top_k=10):
    """
    Rank candidate embeddings by cosine similarity to a query embedding.

    Args:
        query_embedding: numpy array or BLOB of the query vector.
        candidates: list of (id, embedding_blob) tuples.
        top_k: Number of top results to return.

    Returns:
        list of (id, similarity_score) tuples, sorted descending.
    """
    if isinstance(query_embedding, (bytes, memoryview)):
        query_embedding = blob_to_embedding(query_embedding)

    results = []
    for cid, blob in candidates:
        if blob is None:
            continue
        emb = blob_to_embedding(blob)
        score = cosine_similarity(query_embedding, emb)
        results.append((cid, score))

    results.sort(key=lambda x: x[1], reverse=True)
    return results[:top_k]
