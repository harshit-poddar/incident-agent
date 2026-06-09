from __future__ import annotations

# RAG stub. Swap for vector search over runbooks + past incidents.
_RUNBOOKS = {
    "oom": (
        "RB-114: payments-api OOM -- restart pods to clear leaked memory; "
        "if it recurs within 1h, roll back to last stable image."
    ),
}


class KnowledgeTool:
    def search_runbooks(self, query: str) -> list[str]:
        hits = [v for k, v in _RUNBOOKS.items() if k in query.lower()]
        return hits or ["No matching runbook; proceed with standard triage."]
