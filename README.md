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

## Demo

Two ways to show the closed loop end-to-end — both run on CPU in mock mode, no
GPU or external services required.

### Web dashboard (recommended)

```bash
uvicorn app.main:app --port 8000
```

Open <http://localhost:8000> in a browser, then:

1. Click **⚡ Trigger incident** — the agents fill in (Detector → Diagnoser with
   runbook evidence → Planner) and the pipeline advances.
2. It **pauses at the Human Approval Gate** — click **✓ Approve remediation**.
3. It resumes → remediates → verifies → **RESOLVED**, with the full audit trail
   and a live **MI300X GPU panel**.
4. Click **↺ Reset** to run it again from a clean slate.

### Terminal walkthrough (offline fallback)

```bash
python scripts/demo.py
```

Runs the whole loop in the terminal and pauses at the gate for a keypress.
No server, no GPU, no internet — useful when wifi or a projector is flaky.

### Optional: back the demo with real services

```bash
docker compose up -d postgres qdrant redis
STORE_MODE=postgres RAG_MODE=qdrant TELEMETRY_MODE=redis uvicorn app.main:app --port 8000
```

Same UI, now persisting incidents in Postgres, retrieving runbooks from qdrant,
and ingesting telemetry from a Redis stream. To monitor a real MI300X, add
`GPU_MONITOR_MODE=rocm` on the pod.

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
