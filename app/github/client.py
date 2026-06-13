from __future__ import annotations

from typing import Protocol, runtime_checkable

from app.config import settings
from app.github.schemas import PullRequestRef
from app.schemas.incident import ProposedFix


@runtime_checkable
class GitHubClient(Protocol):
    """The seam between the agent and GitHub. Mock = offline canned data (the
    whole demo runs on CPU); Rest = the real REST API behind a PAT. Same pattern
    as LLMClient and TelemetrySource -- agents/executor never import a concrete
    client, they receive one."""

    def fetch_run_logs(self, repo: str, run_id: int) -> str:
        """Return the failed run's job logs as plain text."""
        ...

    def get_file(self, repo: str, path: str, ref: str) -> str:
        """Return the current text content of a file at a ref (branch/sha)."""
        ...

    def open_pr(self, repo: str, base: str, fix: ProposedFix) -> PullRequestRef:
        """Create a branch, commit the fix, and open a PR. Side-effectful: only
        ever called by the gated executor after human approval."""
        ...


# A small, realistic-looking offending file the mock 'serves' and the LLM fixes.
_MOCK_FILE = """\
# payments/handler.py  (excerpt)
CACHE = {}

def handle_payment(req):
    # BUG: unbounded cache -> memory grows until the pod is OOMKilled
    CACHE[req.id] = build_receipt(req)
    return CACHE[req.id]
"""

# A vulnerable Java file the mock 'serves' for the security-scan demo: a textbook
# CWE-89 (the user_id is concatenated straight into the SQL string). The
# fine-tuned vuln-fixer model rewrites it to a parameterised PreparedStatement.
_MOCK_JAVA_FILE = """\
package com.acme.payments;

import java.sql.Connection;
import java.sql.ResultSet;
import java.sql.Statement;

public class PaymentRepository {
    private final Connection connection;

    public PaymentRepository(Connection connection) {
        this.connection = connection;
    }

    public ResultSet findByUser(String userId) throws Exception {
        Statement stmt = connection.createStatement();
        // VULN (CWE-89): untrusted userId concatenated straight into the query.
        String query = "SELECT * FROM payments WHERE user_id = '" + userId + "'";
        return stmt.executeQuery(query);
    }
}
"""

_MOCK_LOGS = """\
2025-06-10T12:34:16Z payments-api ERROR java.lang.OutOfMemoryError: Java heap space
2025-06-10T12:34:16Z payments-api ERROR pod payments-api-7c9 OOMKilled -- restarting
2025-06-10T12:34:18Z ci  deploy step failed: health check (3/3) err_rate 0.38 > 0.02
2025-06-10T12:34:18Z ci  ::error:: payments-api did not become healthy; failing the run
"""


class MockGitHubClient:
    """Offline GitHub. Returns canned logs/file content and records any PR it is
    asked to open (so tests and the demo can assert on it) without a network."""

    def __init__(self) -> None:
        self.opened: list[PullRequestRef] = []
        self._next_number = 42

    def fetch_run_logs(self, repo: str, run_id: int) -> str:
        return _MOCK_LOGS

    def get_file(self, repo: str, path: str, ref: str) -> str:
        return _MOCK_JAVA_FILE if path.endswith(".java") else _MOCK_FILE

    def open_pr(self, repo: str, base: str, fix: ProposedFix) -> PullRequestRef:
        number = self._next_number
        self._next_number += 1
        branch = f"agent/fix-{number}"
        pr = PullRequestRef(
            number=number,
            url=f"https://github.com/{repo}/pull/{number}",
            branch=branch,
        )
        self.opened.append(pr)
        return pr


class RestGitHubClient:
    """Real GitHub via the REST API (httpx + a PAT). Opening a PR is: read base
    ref -> create a branch -> commit the file via the Contents API -> open the
    PR. httpx is imported lazily so 'mock' mode keeps zero extra runtime weight."""

    def __init__(self, token: str | None = None) -> None:
        import httpx  # lazy: only when GITHUB_MODE=live

        self._token = token or settings.github_token
        self._http = httpx.Client(
            base_url="https://api.github.com",
            headers={
                "Authorization": f"Bearer {self._token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
            timeout=30.0,
        )

    def fetch_run_logs(self, repo: str, run_id: int) -> str:
        # The logs endpoint streams a zip; for a diagnosis we fetch the jobs and
        # concatenate their step names/conclusions -- enough signal for the LLM,
        # and avoids unzipping in-process. (Full log text can be added later.)
        # Tolerant: if the run id doesn't exist (e.g. /github/simulate used as a
        # fallback in live mode), fall back to a synthetic summary so the rest of
        # the flow -- diagnose, propose, open PR -- still runs.
        try:
            r = self._http.get(f"/repos/{repo}/actions/runs/{run_id}/jobs")
            r.raise_for_status()
        except Exception:
            return f"workflow run {run_id} on {repo}: deploy failed (logs unavailable)"
        lines: list[str] = []
        for job in r.json().get("jobs", []):
            lines.append(f"job {job['name']}: {job.get('conclusion')}")
            for step in job.get("steps", []):
                lines.append(f"  step {step['name']}: {step.get('conclusion')}")
        return "\n".join(lines) or f"workflow run {run_id}: failed"

    def get_file(self, repo: str, path: str, ref: str) -> str:
        import base64

        r = self._http.get(f"/repos/{repo}/contents/{path}", params={"ref": ref})
        r.raise_for_status()
        return base64.b64decode(r.json()["content"]).decode("utf-8")

    def open_pr(self, repo: str, base: str, fix: ProposedFix) -> PullRequestRef:
        import base64

        # 1. base branch head sha
        ref = self._http.get(f"/repos/{repo}/git/ref/heads/{base}")
        ref.raise_for_status()
        base_sha = ref.json()["object"]["sha"]

        # 2. new branch -- find a free name so repeated demo runs don't collide
        stem = f"agent/fix-{fix.file_path.replace('/', '-')}"
        branch = stem
        for n in range(2, 50):
            resp = self._http.post(
                f"/repos/{repo}/git/refs",
                json={"ref": f"refs/heads/{branch}", "sha": base_sha},
            )
            if resp.status_code < 300:
                break
            if resp.status_code == 422:  # ref exists -> try the next suffix
                branch = f"{stem}-{n}"
                continue
            resp.raise_for_status()

        # 3. current file sha on the new branch (needed to update it)
        cur = self._http.get(
            f"/repos/{repo}/contents/{fix.file_path}", params={"ref": branch}
        )
        file_sha = cur.json().get("sha") if cur.status_code == 200 else None

        # 4. commit the fix
        payload = {
            "message": fix.pr_title,
            "content": base64.b64encode(fix.new_content.encode("utf-8")).decode("ascii"),
            "branch": branch,
        }
        if file_sha:
            payload["sha"] = file_sha
        self._http.put(
            f"/repos/{repo}/contents/{fix.file_path}", json=payload
        ).raise_for_status()

        # 5. open the PR
        pr = self._http.post(
            f"/repos/{repo}/pulls",
            json={"title": fix.pr_title, "body": fix.pr_body, "head": branch, "base": base},
        )
        pr.raise_for_status()
        data = pr.json()
        return PullRequestRef(number=data["number"], url=data["html_url"], branch=branch)


def get_github_client() -> GitHubClient:
    """Single env switch, same as every other seam."""
    if settings.github_mode == "live":
        return RestGitHubClient()
    return MockGitHubClient()
