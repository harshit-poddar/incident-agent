"""Judge-facing walkthrough of the Java vulnerability-fixer integration.

Drives the full closed loop offline (no GPU, no network):
  SAST finding (CWE-89) -> detect -> diagnose (RAG) -> JavaVulnFixer calls the
  fine-tuned 'vuln-fixer' model -> [HUMAN APPROVAL GATE] -> PR opened -> RESOLVED.

Run:  python scripts/vuln_demo.py
To hit the real fine-tuned endpoint instead of the offline mock:
  VULN_FIXER_MODE=live VULN_FIXER_BASE_URL=http://<POD_HOST>:8000/v1 \
      python scripts/vuln_demo.py
"""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

# Force the plumbing seams offline so the demo never needs Postgres, Redis, a
# GPU, or the network -- same bulletproof posture as the test suite's conftest.
# We deliberately leave VULN_FIXER_MODE untouched: set it to "live" to show the
# REAL fine-tuned model producing the patch while everything else stays mock.
from app.config import settings

settings.store_mode = "memory"
settings.github_mode = "mock"
settings.github_webhook_secret = ""
settings.model_mode = "mock"
settings.telemetry_mode = "mock"
settings.gpu_monitor_mode = "mock"
settings.rag_mode = "memory"
settings.embed_mode = "mock"
settings.trace_mode = "memory"

from app.main import app


def main() -> None:
    c = TestClient(app)
    c.delete("/incidents")

    print("1. A security scan flags a Java file. Opening incident ...\n")
    state = c.post("/github/simulate-vuln").json()

    print(f"   detector  : {state['detection']['summary']}")
    print(f"   diagnoser : {state['diagnosis']['root_cause']}")
    action = state["plan"]["actions"][0]
    print(f"   planner   : {action['action']}  ->  {action['fix']['pr_title']}")
    print(f"   status    : {state['status'].upper()}  (paused at the human gate)\n")

    print("2. Proposed patch (from the fine-tuned vuln-fixer model):")
    print("   " + "-" * 60)
    for line in action["fix"]["new_content"].splitlines():
        print("   " + line)
    print("   " + "-" * 60 + "\n")

    print("3. Human approves -> the PR is opened (gated side effect) ...\n")
    done = c.post(f"/incidents/{state['id']}/approve", json={"approved": True}).json()
    print(f"   remediation : {done['remediation_results'][0]['output']}")
    print(f"   status      : {done['status'].upper()}\n")

    print("4. Full audit trail:")
    for e in done["audit"]:
        print(f"   {e['actor']:<12} {e['event']:<16} {e['detail'][:70]}")


if __name__ == "__main__":
    main()
