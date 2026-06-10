from __future__ import annotations

from typing import Protocol, runtime_checkable

from app.orchestration.state import IncidentState


@runtime_checkable
class IncidentStore(Protocol):
    """Persistence seam for incidents -- the same pattern as LLMClient.

    The async approval gate needs state to survive between the POST that pauses
    the graph and the /approve call (possibly minutes later, possibly after a
    process restart). Agents/API depend only on this protocol; the concrete
    store is a single config switch (STORE_MODE = memory | postgres)."""

    def save(self, state: IncidentState) -> None:
        ...

    def get(self, incident_id: str) -> IncidentState | None:
        ...

    def list_ids(self) -> list[str]:
        ...


class InMemoryIncidentStore:
    """Default store: a dict. Zero dependencies, perfect for tests and CPU dev.
    Not durable -- state is lost on restart. Swap for PostgresIncidentStore when
    durability matters (STORE_MODE=postgres)."""

    def __init__(self) -> None:
        self._by_id: dict[str, IncidentState] = {}

    def save(self, state: IncidentState) -> None:
        # Store a copy so external mutation of the returned object can't corrupt
        # what we hold -- mirrors how a real DB row is decoupled from memory.
        self._by_id[state.id] = state.model_copy(deep=True)

    def get(self, incident_id: str) -> IncidentState | None:
        found = self._by_id.get(incident_id)
        return found.model_copy(deep=True) if found is not None else None

    def list_ids(self) -> list[str]:
        return list(self._by_id.keys())


def get_incident_store() -> IncidentStore:
    """Single switch for the persistence backend (STORE_MODE).
    memory -> InMemoryIncidentStore (default, no deps).
    postgres -> PostgresIncidentStore (durable, survives restarts)."""
    from app.config import settings

    if settings.store_mode == "postgres":
        from app.orchestration.store_postgres import PostgresIncidentStore

        return PostgresIncidentStore()
    return InMemoryIncidentStore()
