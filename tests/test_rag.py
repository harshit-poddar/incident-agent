from __future__ import annotations

from app.rag.embedder import HashEmbedder
from app.rag.runbooks import RUNBOOKS, seed_runbooks
from app.rag.vectorstore import InMemoryVectorStore
from app.tools.knowledge import KnowledgeTool


def test_hash_embedder_is_deterministic_and_normalized():
    emb = HashEmbedder(dim=128)
    a = emb.embed(["payments-api OOM memory leak"])[0]
    b = emb.embed(["payments-api OOM memory leak"])[0]
    assert a == b  # deterministic
    assert len(a) == 128
    norm = sum(x * x for x in a) ** 0.5
    assert abs(norm - 1.0) < 1e-9  # L2-normalized


def test_in_memory_search_ranks_relevant_runbook_first():
    emb = HashEmbedder(dim=256)
    store = InMemoryVectorStore()
    seed_runbooks(store, emb)
    assert store.count() == len(RUNBOOKS)

    qv = emb.embed(["payments-api out of memory OOM 5xx error rate spike"])[0]
    hits = store.search(qv, top_k=3)
    assert hits[0]["id"] == "RB-114"  # the OOM runbook wins


def test_seed_is_idempotent():
    emb = HashEmbedder(dim=256)
    store = InMemoryVectorStore()
    seed_runbooks(store, emb)
    seed_runbooks(store, emb)  # second call is a no-op
    assert store.count() == len(RUNBOOKS)


def test_knowledge_tool_returns_runbook_strings():
    # Default construction: hash embedder + in-memory store, auto-seeded.
    kt = KnowledgeTool()
    results = kt.search_runbooks("oom payments-api error rate memory")
    assert len(results) == 3
    assert results[0].startswith("RB-114:")
    assert all(isinstance(r, str) for r in results)


def test_knowledge_tool_retrieves_latency_runbook():
    kt = KnowledgeTool(top_k=1)
    results = kt.search_runbooks("p95 latency high cpu saturation under load")
    assert results[0].startswith("RB-201:")
