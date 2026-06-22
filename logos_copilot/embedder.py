"""Pluggable embedders. Default `HashEmbedder` is deterministic and dependency-free so the whole
pipeline runs locally without ML wheels. Swap to fastembed/voyage via EMBEDDER env (one re-embed).
"""
from __future__ import annotations

import hashlib
import math
from typing import Protocol, Sequence, runtime_checkable

from .config import settings


@runtime_checkable
class Embedder(Protocol):
    model_id: str
    dim: int

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]: ...
    def embed_query(self, text: str) -> list[float]: ...


class HashEmbedder:
    """Deterministic bag-of-hashed-tokens vector, L2-normalized. Not semantic — proves plumbing.
    BM25 (Postgres full-text) supplies real keyword relevance in hybrid retrieval."""

    model_id = "hash-v1"

    def __init__(self, dim: int = 256):
        self.dim = dim

    def _vec(self, text: str) -> list[float]:
        v = [0.0] * self.dim
        for tok in text.lower().split():
            h = int(hashlib.md5(tok.encode("utf-8")).hexdigest(), 16)
            v[h % self.dim] += 1.0
        norm = math.sqrt(sum(x * x for x in v)) or 1.0
        return [x / norm for x in v]

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        return [self._vec(t) for t in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._vec(text)


class FastEmbedEmbedder:
    """Local CPU embeddings via fastembed (optional dep)."""

    def __init__(self, model_id: str, dim: int):
        from fastembed import TextEmbedding  # lazy import

        self.model_id, self.dim = model_id, dim
        self._m = TextEmbedding(model_name=model_id)

    def embed_documents(self, texts):
        return [list(map(float, v)) for v in self._m.embed(list(texts))]

    def embed_query(self, text):
        return list(map(float, next(self._m.query_embed(text))))


class VoyageEmbedder:
    """Managed embeddings via Voyage (optional dep). voyage-3-large prose / voyage-code-3 code."""

    def __init__(self, model_id: str, dim: int, api_key: str | None):
        import voyageai  # lazy import

        self.model_id, self.dim = model_id, dim
        self._c = voyageai.Client(api_key=api_key)

    def embed_documents(self, texts):
        return self._c.embed(list(texts), model=self.model_id, input_type="document").embeddings

    def embed_query(self, text):
        return self._c.embed([text], model=self.model_id, input_type="query").embeddings[0]


def get_embedder() -> Embedder:
    if settings.embedder == "voyage":
        return VoyageEmbedder(settings.voyage_model, settings.embed_dim, settings.voyage_api_key)
    if settings.embedder == "fastembed":
        try:
            return FastEmbedEmbedder(settings.local_model, settings.embed_dim)
        except Exception:                       # fastembed not installed -> deps-free fallback
            return HashEmbedder(settings.embed_dim)
    return HashEmbedder(settings.embed_dim)
