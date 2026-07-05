"""Pluggable embedding functions.

Default: lightweight hashed bag-of-words embedder (zero external downloads,
deterministic, CI-friendly). Swap to SentenceTransformers/OpenAI in production
by changing EMBEDDER.
"""
import hashlib
import math
import re
from chromadb import Documents, EmbeddingFunction, Embeddings

DIM = 256


class HashedBoWEmbedder(EmbeddingFunction):
    """Deterministic hashed bag-of-words embedding. No model download required."""

    def name(self) -> str:
        return "hashed-bow-v1"

    def __call__(self, input: Documents) -> Embeddings:
        return [self._embed(t) for t in input]

    @staticmethod
    def _embed(text: str) -> list[float]:
        vec = [0.0] * DIM
        tokens = re.findall(r"[a-z0-9_]+", text.lower())
        for tok in tokens:
            h = int(hashlib.md5(tok.encode()).hexdigest(), 16)
            vec[h % DIM] += 1.0
        norm = math.sqrt(sum(v * v for v in vec)) or 1.0
        return [v / norm for v in vec]


EMBEDDER = HashedBoWEmbedder()
