from __future__ import annotations

from app.config import settings
from app.orchestration.state import IncidentState


class PostgresIncidentStore:
    """Durable IncidentStore backed by Postgres. The whole IncidentState is
    persisted as JSONB keyed by id -- simple, schema-light, and enough to make
    the async approval gate survive process restarts.

    A connection is opened per call (fine for v1; swap for a pool later).
    psycopg is imported lazily so 'memory' mode keeps zero extra deps."""

    def __init__(self, dsn: str | None = None) -> None:
        import psycopg  # lazy: only when STORE_MODE=postgres

        self._psycopg = psycopg
        self._dsn = dsn or settings.database_url
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        with self._psycopg.connect(self._dsn) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS incidents (
                    id         text PRIMARY KEY,
                    status     text NOT NULL,
                    data       jsonb NOT NULL,
                    updated_at timestamptz NOT NULL DEFAULT now()
                )
                """
            )
            conn.commit()

    def save(self, state: IncidentState) -> None:
        from psycopg.types.json import Jsonb

        with self._psycopg.connect(self._dsn) as conn:
            conn.execute(
                """
                INSERT INTO incidents (id, status, data, updated_at)
                VALUES (%s, %s, %s, now())
                ON CONFLICT (id) DO UPDATE
                  SET status = EXCLUDED.status,
                      data = EXCLUDED.data,
                      updated_at = now()
                """,
                (state.id, state.status.value, Jsonb(state.model_dump(mode="json"))),
            )
            conn.commit()

    def get(self, incident_id: str) -> IncidentState | None:
        with self._psycopg.connect(self._dsn) as conn:
            row = conn.execute(
                "SELECT data FROM incidents WHERE id = %s", (incident_id,)
            ).fetchone()
        if row is None:
            return None
        return IncidentState.model_validate(row[0])

    def list_ids(self) -> list[str]:
        with self._psycopg.connect(self._dsn) as conn:
            rows = conn.execute(
                "SELECT id FROM incidents ORDER BY updated_at DESC"
            ).fetchall()
        return [r[0] for r in rows]
