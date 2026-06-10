from __future__ import annotations


class QdrantVectorStore:
    """Durable VectorStore backed by qdrant. Creates the collection on first use
    (cosine distance, EMBED_DIM size). Point ids are integers (qdrant requires
    int/UUID), with the runbook id carried in the payload. qdrant_client is
    imported lazily so 'memory' mode needs no extra dep."""

    def __init__(self, url: str, collection: str, dim: int) -> None:
        from qdrant_client import QdrantClient
        from qdrant_client.models import Distance, VectorParams

        self._client = QdrantClient(url=url)
        self._collection = collection
        self._dim = dim
        if not self._client.collection_exists(collection):
            self._client.create_collection(
                collection_name=collection,
                vectors_config=VectorParams(size=dim, distance=Distance.COSINE),
            )

    def upsert(self, records: list[dict]) -> None:
        from qdrant_client.models import PointStruct

        points = [
            PointStruct(id=i, vector=r["vector"], payload=r["payload"])
            for i, r in enumerate(records)
        ]
        self._client.upsert(collection_name=self._collection, points=points)

    def count(self) -> int:
        return self._client.count(collection_name=self._collection).count

    def search(self, vector: list[float], top_k: int) -> list[dict]:
        res = self._client.query_points(
            collection_name=self._collection, query=vector, limit=top_k, with_payload=True
        ).points
        return [{"score": p.score, **(p.payload or {})} for p in res]
