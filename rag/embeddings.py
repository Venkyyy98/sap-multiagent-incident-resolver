"""Pluggable embedding functions.

HashedBoWEmbedder: lightweight hashed bag-of-words embedder (zero external downloads,
deterministic, CI-friendly), but only matches on literal shared vocabulary.
OpenAIEmbedder: real semantic embeddings via OpenAI, understands meaning rather
than exact wording, at the cost of needing network access + an API key.
EMBEDDER picks OpenAI when a key is configured and mock mode is off, otherwise
falls back to the offline hashed embedder so tests/CI keep working without a key.
"""
import hashlib
import math
import re
from chromadb import Documents, EmbeddingFunction, Embeddings
from config import settings

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


class OpenAIEmbedder(EmbeddingFunction):
    """Real semantic embeddings via OpenAI's text-embedding-3-small."""

    def name(self) -> str:
        return "openai-text-embedding-3-small"

    def __call__(self, input: Documents) -> Embeddings:
        from openai import OpenAI
        client = OpenAI(api_key=settings.openai_api_key)
        resp = client.embeddings.create(model="text-embedding-3-small", input=list(input))
        return [d.embedding for d in resp.data]


EMBEDDER = OpenAIEmbedder() if (not settings.mock_mode and settings.openai_api_key) else HashedBoWEmbedder()
