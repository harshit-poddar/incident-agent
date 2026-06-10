from __future__ import annotations

import hashlib
import math
import re
from typing import Protocol, runtime_checkable


@runtime_checkable
class Embedder(Protocol):
    """Turns text into vectors. The RAG seam, mirroring LLMClient:
    HashEmbedder (offline, deterministic) for dev/tests; OpenAIEmbedder
    (the embedding model served on the pod) for real semantic retrieval."""

    def embed(self, texts: list[str]) -> list[list[float]]:
        ...


_TOKEN = re.compile(r"[a-z0-9]+")


class HashEmbedder:
    """Deterministic, dependency-free embedder via signed feature hashing
    (the 'hashing trick'). It is a hashed bag-of-words, so it captures *lexical*
    overlap -- texts sharing tokens like 'oom'/'memory' land near each other.
    Not semantic, but real, instant, and reproducible -- ideal for CPU dev,
    tests, and exercising the qdrant integration without a GPU embedder."""

    def __init__(self, dim: int = 256) -> None:
        self.dim = dim

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._one(t) for t in texts]

    def _one(self, text: str) -> list[float]:
        vec = [0.0] * self.dim
        for tok in _TOKEN.findall(text.lower()):
            h = int(hashlib.md5(tok.encode("utf-8")).hexdigest(), 16)
            idx = h % self.dim
            sign = 1.0 if (h >> 8) & 1 == 0 else -1.0  # signed -> fewer collisions
            vec[idx] += sign
        norm = math.sqrt(sum(x * x for x in vec)) or 1.0
        return [x / norm for x in vec]  # L2-normalized so dot product == cosine


class OpenAIEmbedder:
    """Live embedder against an OpenAI-compatible embeddings endpoint (the model
    served on the MI300X). The output dimension must match EMBED_DIM / the
    qdrant collection size. Imported lazily so mock mode needs no openai dep."""

    def __init__(
        self, base_url: str | None = None, api_key: str | None = None, model: str | None = None
    ) -> None:
        from openai import OpenAI

        from app.config import settings

        self._model = model or settings.embed_model_name
        self._client = OpenAI(
            base_url=base_url or settings.model_base_url,
            api_key=api_key or settings.model_api_key,
        )

    def embed(self, texts: list[str]) -> list[list[float]]:
        resp = self._client.embeddings.create(model=self._model, input=texts)
        return [d.embedding for d in resp.data]


def get_embedder() -> Embedder:
    from app.config import settings

    if settings.embed_mode == "live":
        return OpenAIEmbedder()
    return HashEmbedder(dim=settings.embed_dim)
