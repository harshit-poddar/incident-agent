from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class VectorStore(Protocol):
    """Vector index seam. InMemoryVectorStore (no deps, for dev/tests) or
    QdrantVectorStore (durable, for real). Records are dicts:
    {"id": str, "vector": list[float], "payload": dict}.
    search() returns payloads merged with a "score" key, best first."""

    def upsert(self, records: list[dict]) -> None:
        ...

    def search(self, vector: list[float], top_k: int) -> list[dict]:
        ...

    def count(self) -> int:
        ...


class InMemoryVectorStore:
    """Brute-force cosine search over an in-process list. Fine for a handful of
    runbooks; O(n) per query. Vectors are assumed L2-normalized (HashEmbedder
    does this), so the dot product is the cosine similarity."""

    def __init__(self) -> None:
        self._records: list[dict] = []

    def upsert(self, records: list[dict]) -> None:
        for r in records:
            self._records = [x for x in self._records if x["id"] != r["id"]]
            self._records.append(r)

    def count(self) -> int:
        return len(self._records)

    def search(self, vector: list[float], top_k: int) -> list[dict]:
        scored = [
            {"score": _dot(vector, r["vector"]), **r["payload"]} for r in self._records
        ]
        scored.sort(key=lambda h: h["score"], reverse=True)
        return scored[:top_k]


def _dot(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


def get_vector_store() -> VectorStore:
    from app.config import settings

    if settings.rag_mode == "qdrant":
        from app.rag.vectorstore_qdrant import QdrantVectorStore

        return QdrantVectorStore(
            url=settings.qdrant_url,
            collection=settings.qdrant_collection,
            dim=settings.embed_dim,
        )
    return InMemoryVectorStore()
