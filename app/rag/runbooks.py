from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.rag.embedder import Embedder
    from app.rag.vectorstore import VectorStore

# The runbook corpus the diagnoser retrieves over. In production this would be a
# living knowledge base (markdown runbooks + resolved past incidents) re-indexed
# on change; here it's a small static set that drives the RAG pipeline end-to-end.
RUNBOOKS: list[dict] = [
    {
        "id": "RB-114",
        "title": "payments-api out-of-memory / memory leak",
        "text": (
            "payments-api OOM: pods hit the memory limit and get OOM-killed, "
            "causing a 5xx error-rate spike. Restart the affected pods to clear "
            "the leaked memory. If the OOM recurs within one hour, roll back to "
            "the last stable image."
        ),
        "tags": ["oom", "memory", "payments-api", "5xx", "restart"],
    },
    {
        "id": "RB-203",
        "title": "SQL injection flagged by SAST (CWE-89)",
        "text": (
            "A security scan flags CWE-89 SQL injection when untrusted input is "
            "concatenated into a SQL query string. Remediate by parameterising "
            "the query: use a PreparedStatement with bind parameters instead of "
            "string concatenation. Open a fix PR and have it reviewed before merge."
        ),
        "tags": ["security", "cwe-89", "sql", "injection", "open_pr", "sast"],
    },
    {
        "id": "RB-201",
        "title": "high latency from CPU saturation",
        "text": (
            "Elevated p95 latency with CPU near 100%: the service is "
            "compute-saturated under load. Scale up the replica count to shed "
            "per-pod CPU pressure and bring latency back under SLO."
        ),
        "tags": ["latency", "cpu", "saturation", "scale_up", "throughput"],
    },
    {
        "id": "RB-305",
        "title": "Redis cache stampede",
        "text": (
            "Cache stampede after a Redis flush or mass key expiry: a thundering "
            "herd hits the database and latency climbs. Clear and warm the cache, "
            "then enable request coalescing so only one fill happens per key."
        ),
        "tags": ["redis", "cache", "stampede", "clear_cache", "latency"],
    },
    {
        "id": "RB-402",
        "title": "error spike immediately after a deploy",
        "text": (
            "Error rate jumps right after a release: the new build is almost "
            "certainly the cause. Roll back to the previous known-good image, "
            "then triage the bad build offline before re-deploying."
        ),
        "tags": ["deploy", "release", "regression", "rollback", "5xx"],
    },
    {
        "id": "RB-118",
        "title": "disk full on a service node",
        "text": (
            "Disk usage at capacity causes write failures and crashes. Clear "
            "rotated logs and temp files to reclaim space, then expand the volume "
            "if usage is structurally high."
        ),
        "tags": ["disk", "storage", "full", "logs", "capacity"],
    },
]


def seed_runbooks(store: "VectorStore", embedder: "Embedder") -> None:
    """Idempotently load the runbook corpus into a vector store. Skips work if
    the store already holds the full set (so per-request construction against a
    durable qdrant costs one count() call, not a full re-embed)."""
    if store.count() >= len(RUNBOOKS):
        return
    vectors = embedder.embed([rb["text"] for rb in RUNBOOKS])
    store.upsert(
        [{"id": rb["id"], "vector": vec, "payload": rb} for rb, vec in zip(RUNBOOKS, vectors)]
    )
