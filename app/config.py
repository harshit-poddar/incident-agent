from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central config. Everything model-related is driven by env so the same
    code runs against a mock, a small CPU model, or the 70B on the MI300X."""

    model_config = SettingsConfigDict(
        env_file=".env", extra="ignore", protected_namespaces=()
    )

    # "mock"   -> offline scripted responses (no GPU)
    # "replay" -> serve fixtures captured from a real model (no GPU, deterministic)
    # "live"   -> hit the vLLM endpoint on the MI300X
    model_mode: str = "mock"
    model_base_url: str = "http://localhost:8000/v1"
    model_name: str = "Qwen3-4B"
    model_api_key: str = "abc-123"

    # Where ReplayLLMClient reads, and capture_fixtures.py writes, fixtures.
    fixtures_dir: str = "fixtures"

    # Incident persistence backend. "memory" (default, no deps) keeps state in a
    # dict; "postgres" persists it so it survives restarts and the async gate.
    store_mode: str = "memory"
    database_url: str = "postgresql://agent:agent@localhost:5432/incidents"

    # RAG over runbooks. rag_mode picks the vector store (memory | qdrant);
    # embed_mode picks the embedder (mock = HashEmbedder, no GPU; live = served
    # embedding model). embed_dim must match the qdrant collection AND, in live
    # mode, the embedding model's output dimension.
    rag_mode: str = "memory"
    embed_mode: str = "mock"
    embed_dim: int = 256
    embed_model_name: str = "bge-small-en"
    qdrant_url: str = "http://localhost:6333"
    qdrant_collection: str = "runbooks"

    # Telemetry. telemetry_mode picks the service-metrics source (mock = in-proc,
    # redis = ingest from a Redis Stream event queue). gpu_monitor_mode picks the
    # MI300X self-monitor (mock = fake readings, rocm = shell out to rocm-smi).
    telemetry_mode: str = "mock"
    gpu_monitor_mode: str = "mock"
    redis_url: str = "redis://localhost:6379/0"

    # GitHub integration. github_mode picks the client (mock = offline canned
    # data, no network; live = real REST API behind a PAT). The webhook receiver
    # verifies payloads against github_webhook_secret; the agent opens PRs
    # against github_base_branch in github_repo (owner/name). The offending file
    # the Fixer reads/patches in the demo scenario is github_target_file.
    github_mode: str = "mock"
    github_token: str = ""
    github_repo: str = "harshit-poddar/incident-agent"
    github_base_branch: str = "main"
    github_webhook_secret: str = ""
    github_target_file: str = "payments/handler.py"

    # Observability (Slice 6). trace_mode picks the span sink: "memory" (default,
    # no deps -- powers the dashboard waterfall) or "otel" (memory + an
    # OpenTelemetry exporter). With otel, an empty otel_endpoint uses the console
    # exporter; set it to an OTLP gRPC endpoint (e.g. localhost:4317) to ship
    # spans to Jaeger/Tempo/Logfire.
    trace_mode: str = "memory"
    otel_endpoint: str = ""
    otel_service_name: str = "agents-026-incident-agent"


settings = Settings()
