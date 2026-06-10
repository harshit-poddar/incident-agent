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

The dashboard is a React app (`frontend/`, built with Vite). The repo ships the
built assets in `frontend/dist`, which FastAPI serves automatically — so the
demo machine needs **no Node**. (If `frontend/dist` is absent, FastAPI falls
back to the self-contained `app/web/index.html`, so the API always has a UI.)

```bash
uvicorn app.main:app --port 8000          # serves the built dashboard at /
# to rebuild the dashboard after changes:
cd frontend && npm install && npm run build
# or hack on it live with hot reload (proxies the API to :8000):
cd frontend && npm run dev                 # http://localhost:5173
```

Open <http://localhost:8000> in a browser, then:

1. Click **⚡ Trigger incident** — the agents fill in (Detector → Diagnoser with
   runbook evidence → Planner) and the animated pipeline advances.
2. It **pauses at the Human Approval Gate** — click **✓ Approve remediation**.
3. It resumes → remediates → verifies → **RESOLVED**, with the full audit trail,
   the **execution trace waterfall**, and a live **MI300X GPU panel**.
4. Click **↺ Reset** to run it again from a clean slate.

### Terminal walkthrough (offline fallback)

```bash
python scripts/demo.py
```

Runs the whole loop in the terminal and pauses at the gate for a keypress.
No server, no GPU, no internet — useful when wifi or a projector is flaky.

### Live: real GitHub CI → agent-authored fix PR

The headline demo. A real (or simulated) CI failure flows through the agent,
which diagnoses it and proposes a code fix — opened as a real pull request only
*after* a human approves it in the dashboard (opening a PR is a gated side
effect, same rule as any remediation).

**Offline (no GitHub, no network — the bulletproof fallback):**

1. Click **🐙 Simulate CI failure** in the dashboard (or `POST /github/simulate`).
2. The agent diagnoses the OOM and the **Proposed code fix** panel shows the
   LLM-generated patch to `payments/handler.py`.
3. Approve at the gate → the (mock) PR is opened and linked. RESOLVED.

**Live (real GitHub):**

```bash
# 1. Token + repo
export GITHUB_MODE=live
export GITHUB_TOKEN=<PAT with repo + workflow scope>
export GITHUB_REPO=<owner/name>
export GITHUB_WEBHOOK_SECRET=<shared secret>

# 2. Expose the webhook (real-time trigger)
cloudflared tunnel --url http://localhost:8000     # or: ngrok http 8000
#   add the public URL + secret as a repo webhook for the "Workflow runs" event

# 3. Run the agent
uvicorn app.main:app --port 8000
```

Trigger the **deploy** workflow from the repo's Actions tab
(`.github/workflows/payments-deploy.yml` fails on purpose). GitHub fires the
`workflow_run` webhook → the agent pulls the run logs, diagnoses, and proposes a
fix → you approve in the dashboard → it opens a **real PR** against your repo.
If wifi or the runner is flaky on stage, fall back to **🐙 Simulate CI failure** —
same code path, no network.

### Optional: back the demo with real services

```bash
docker compose up -d postgres qdrant redis
STORE_MODE=postgres RAG_MODE=qdrant TELEMETRY_MODE=redis uvicorn app.main:app --port 8000
```

Same UI, now persisting incidents in Postgres, retrieving runbooks from qdrant,
and ingesting telemetry from a Redis stream. To monitor a real MI300X, add
`GPU_MONITOR_MODE=rocm` on the pod.

## Observability (tracing)

Every incident is traced across the agent graph. Each agent call, model
invocation, and tool call is a timed, nested span; the dashboard renders them
as a waterfall, and the API exposes them at `GET /traces` and
`GET /traces/{incident_id}`.

```bash
# default: in-process tracer, zero deps, powers the dashboard
TRACE_MODE=memory uvicorn app.main:app --port 8000

# export the same spans to OpenTelemetry (console, or an OTLP collector)
pip install opentelemetry-sdk opentelemetry-exporter-otlp
TRACE_MODE=otel OTEL_ENDPOINT=localhost:4317 uvicorn app.main:app --port 8000
```

Agents are not aware of tracing — LLM calls are wrapped by a `TracingLLMClient`
at the seam, and the supervisor opens spans around each graph node, so the
instrumentation never leaks into agent code.

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
  obs/                 tracing seam: in-memory tracer + OpenTelemetry exporter
  github/              GitHub client seam + webhook (CI → fix-PR flow)
  pipeline/            live CI/runtime log monitor (SSE)
  web/                 legacy single-file dashboard (fallback)
  main.py              FastAPI surface
frontend/              React ops dashboard (Vite); built to frontend/dist
scripts/run_skeleton.py
tests/
```

See `CLAUDE.md` for the full design context and build roadmap.
