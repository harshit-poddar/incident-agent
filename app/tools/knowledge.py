from __future__ import annotations

from app.rag.embedder import Embedder, get_embedder
from app.rag.runbooks import seed_runbooks
from app.rag.vectorstore import VectorStore, get_vector_store


class KnowledgeTool:
    """RAG over the runbook corpus: embed the query, search the vector store,
    return the closest runbooks. The embedder and store are injected via the
    seam factories (hash+in-memory by default; live embedder + qdrant in prod),
    so this tool's interface is unchanged from the original dict stub."""

    def __init__(
        self,
        embedder: Embedder | None = None,
        store: VectorStore | None = None,
        top_k: int = 3,
    ) -> None:
        self._embedder = embedder or get_embedder()
        self._store = store or get_vector_store()
        self._top_k = top_k
        seed_runbooks(self._store, self._embedder)

    def search_runbooks(self, query: str) -> list[str]:
        from app.obs.tracer import span

        with span("rag.search_runbooks", kind="tool", top_k=self._top_k) as sp:
            if self._store.count() == 0:
                return ["No matching runbook; proceed with standard triage."]
            query_vec = self._embedder.embed([query])[0]
            hits = self._store.search(query_vec, self._top_k)
            sp.attributes["hits"] = len(hits)
            return [f"{h['id']}: {h['text']}" for h in hits]
