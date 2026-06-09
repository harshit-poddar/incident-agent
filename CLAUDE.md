# CLAUDE.md — project context for Claude Code

This file is read automatically by Claude Code at the repo root. It is the
shared brain for the build. Keep it current.

## What we are building

AGENTS_026 — an **Autonomous Incident Diagnosis & Resolution Agent** (AIOps).
A supervisor coordinates four specialist agents to run a closed loop:

  detect → diagnose → plan → [HUMAN APPROVAL GATE] → remediate → verify

Track 1 of the TCS–AMD hackathon. The model is **frozen** (inference only — no
fine-tuning). Hardware: 1× AMD MI300X (192 GB VRAM), but **4 GPU-hours/day**.

## North-star goals

1. Showcase end-to-end AI engineering with strong software practices.
2. Demonstrate genuine hardware/infra understanding (the agent monitors the
   MI300X pod it runs on, via rocm-smi).
3. A scalable architecture (stateless workers + ingress/LB + event queue).

## Golden-path demo scenario

`payments-api` error rate spikes (OOM) → detector flags → diagnoser finds the
memory leak via runbook RAG → planner proposes a restart (requires approval) →
human approves → executor restarts it in the sandbox cluster → verifier confirms
recovery from telemetry → RESOLVED, with a full audit trail.

## Core design rules (do not break)

- **Agents depend only on the `LLMClient` protocol** (`app/llm/base.py`). They
  never import a concrete client. This is what lets everything run on CPU.
- **The model target is a single env switch** (`MODEL_MODE` = mock | live). No
  code path hard-codes a model or URL.
- **The human-approval gate is enforced in two places**: the supervisor pauses
  for it, AND the `RemediationExecutor` raises `GateError` if called without an
  approved decision. Never weaken either.
- **Side-effects only via tools.** Anything that changes the world (restart,
  scale) lives behind the gated executor, never inline in an agent.
- Strict typed I/O via pydantic everywhere — no free-form dict passing.
- Sentence case, two-space-clean modules, type hints on public functions.

## GPU budget discipline

- Develop against `MODEL_MODE=mock` (CPU). Never burn GPU to write code.
- One person holds the GPU session at a time; their job is to serve the model
  and **capture fixtures** the whole team reuses, plus benchmarks/telemetry.
- Serve vLLM in `tmux`, not a notebook cell. Use the platform's shared model
  cache or a quantized (AWQ) build — raw 70B weights exceed the 25 GB disk.

## How to run

```bash
pip install -r requirements.txt
python scripts/run_skeleton.py     # full graph, mock model
pytest                              # tests must stay green
uvicorn app.main:app --reload      # API
```

## Build roadmap (next slices, in order)

1. **Record-and-replay fixtures** — capture real vLLM outputs into `fixtures/`,
   add a `ReplayLLMClient` (MODEL_MODE=replay) for deterministic dev + demo.
2. **Real async approval** — pause the graph at the gate; `/incidents/{id}/approve`
   resumes it. Persist `IncidentState` in Postgres; stream events over WebSocket.
3. **Real RAG** — embed runbooks + past incidents into qdrant; replace the
   `KnowledgeTool` stub. Serve the embedding model on the pod.
4. **Real telemetry** — ingest from the mock Docker cluster via an event queue;
   add the MI300X self-monitor (rocm-smi) as a telemetry source.
5. **Eval harness** — labelled incident set; score diagnosis accuracy and
   remediation success (base model vs our prompt/agent stack).
6. **Observability** — tracing (Logfire/OpenTelemetry) across the agent graph.
7. **Frontend** — React ops dashboard: live telemetry, agent reasoning panel,
   approval control, RCA report, and the GPU telemetry panel.

## Migration note

The dev-time `VLLMClient` uses plain OpenAI-compatible structured output. For
production-grade tool-calling, migrate agents to `pydantic_ai`'s `Agent`
(mandated stack) — keep the `LLMClient`-style seam so mock/replay still work.
