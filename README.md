# AGENTS_026 — Autonomous incident diagnosis & resolution agent

A multi-agent system that watches infrastructure telemetry, detects anomalies,
diagnoses root cause, proposes remediation, gates it behind human approval,
executes it against a sandboxed cluster, and verifies recovery.

Built for the TCS–AMD hackathon (Track 1). Designed so ~90% of development runs
on CPU against a mock model — the AMD MI300X is reserved for serving the real
model and capturing benchmarks/telemetry.

## Quickstart (no GPU, no services)

```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# run the full agent graph end-to-end against the mock model
python scripts/run_skeleton.py

# run the test suite
pytest
```

You should see the incident move DETECTED → ... → RESOLVED with a full audit trail.

## Run the API

```bash
uvicorn app.main:app --reload
# POST /incidents  with a Signal body;  GET /incidents/{id}
```

## Switch to the real model (MI300X)

1. On the GPU pod, serve the model in tmux:
   `vllm serve <model> --served-model-name <name> --api-key abc-123 --port 8000 ...`
2. Port-forward it to your laptop: `kubectl port-forward pod/<name> 8000:8000`
3. Flip config: set `MODEL_MODE=live` and `MODEL_NAME=<name>` in `.env`.

No application code changes — only the env. That is the whole point of the
`LLMClient` abstraction.

## Layout

```
app/
  config.py            env-driven settings (the MODEL_* switch)
  llm/                 LLMClient protocol + Mock and vLLM implementations
  schemas/             domain models (Signal, Detection, Diagnosis, ...)
  tools/               telemetry, knowledge (RAG), gated remediation, schemas
  agents/              detector, diagnoser, planner, verifier
  orchestration/       IncidentState + Supervisor (the agent graph)
  main.py              FastAPI surface
scripts/run_skeleton.py
tests/
```

See `CLAUDE.md` for the full design context and build roadmap.
