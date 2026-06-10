"""payments-api request handler (demo target).

This file is intentionally buggy: `CACHE` grows without bound, so under
sustained load the pod's heap fills and it gets OOM-killed -- the incident the
agent diagnoses. The agent's proposed fix (after human approval) replaces the
unbounded dict with a bounded LRU cache and opens a PR against this file."""
from __future__ import annotations

CACHE: dict = {}


def build_receipt(req):
    return {"id": req.id, "status": "ok"}


def handle_payment(req):
    # BUG: unbounded cache -> memory grows until the pod is OOMKilled.
    CACHE[req.id] = build_receipt(req)
    return CACHE[req.id]
