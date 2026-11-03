"""
Dense Vector Embedder for pgvector
Produces consistent L2-normalized dense vector embeddings (128-dim) for pgvector storage and cosine similarity (<=>).
"""

import hashlib
import numpy as np
from typing import List
from sklearn.feature_extraction.text import HashingVectorizer

EMBEDDING_DIM = 128

class TextEmbedder:
    def __init__(self, dim: int = EMBEDDING_DIM):
        self.dim = dim
        self.vectorizer = HashingVectorizer(
            n_features=dim,
            norm='l2',
            ngram_range=(1, 2),
            alternate_sign=False
        )

    def embed_text(self, text: str) -> np.ndarray:
        """Returns a 1D L2-normalized float32 numpy array of length `dim`."""
        if not text or not text.strip():
            return np.zeros(self.dim, dtype=np.float32)
        sparse_vec = self.vectorizer.transform([text])
        dense_vec = sparse_vec.toarray()[0].astype(np.float32)
        norm = np.linalg.norm(dense_vec)
        if norm > 0:
            dense_vec = dense_vec / norm
        return dense_vec

    def embed_batch(self, texts: List[str]) -> List[np.ndarray]:
        """Batch generates normalized embeddings."""
        if not texts:
            return []
        sparse_mat = self.vectorizer.transform(texts)
        dense_mat = sparse_mat.toarray().astype(np.float32)
        results = []
        for vec in dense_mat:
            norm = np.linalg.norm(vec)
            if norm > 0:
                vec = vec / norm
            results.append(vec)
        return results

embedder = TextEmbedder()
