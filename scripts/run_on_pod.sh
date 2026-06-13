#!/usr/bin/env bash
# Launch the agent ON the MI300X pod.
#
# Assumes: this repo is cloned, vLLM is already serving on :8000, and .env
# exists (copy from .env.pod.example and fill GITHUB_TOKEN). Run it inside tmux
# so it survives your Jupyter session closing:
#
#     tmux new -s agent
#     bash scripts/run_on_pod.sh
#     # detach: Ctrl-b then d   |   reattach: tmux attach -t agent
#
# Then expose it:   ngrok http 8080
set -euo pipefail
cd "$(dirname "$0")/.."

PORT="${PORT:-8080}"

echo ">> installing deps (idempotent)…"
python -m pip install -q -r requirements.txt

echo ">> pre-flight…"
if ! python scripts/preflight.py; then
  echo ">> pre-flight failed — fix the FAIL rows above, then re-run." >&2
  exit 1
fi

echo ">> starting agent on 0.0.0.0:${PORT}  (expose with: ngrok http ${PORT})"
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT}"
