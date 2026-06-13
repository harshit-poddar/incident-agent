from __future__ import annotations

from fastapi.testclient import TestClient

from app.agents.java_vuln_fixer import JavaVulnFixer
from app.github.client import MockGitHubClient
from app.github.schemas import WorkflowRun
from app.github.webhook import is_security_failure, parse_sast_finding
from app.main import app
from app.tools.schemas import RemediationActionType
from app.tools.vuln_fixer import (
    VULN_FIXER_SYSTEM,
    MockVulnFixerClient,
    RemoteVulnFixerClient,
    UnsupportedCWE,
    build_user_prompt,
    extract_java,
    fix_java_vulnerability,
)

client = TestClient(app)


# --- The fine-tuned prompt contract is reproduced verbatim -----------------


def test_user_prompt_is_verbatim():
    code = "class X {}"
    prompt = build_user_prompt(code, "CWE-89")
    # The exact template the adapter was fine-tuned on -- do not reformat.
    assert prompt == (
        "Review the following Java code for a CWE-89 vulnerability "
        "(SQL Injection: untrusted input is concatenated into a SQL query). "
        "If the vulnerability is present, fix it. If the code is already secure, "
        "return it unchanged.\n\n"
        "```java\nclass X {}\n```"
    )


def test_system_prompt_is_verbatim():
    assert VULN_FIXER_SYSTEM.startswith("You are a senior application-security engineer.")
    assert "ONLY the complete fixed Java code inside a single ```java code block" in VULN_FIXER_SYSTEM


def test_unknown_cwe_is_rejected():
    try:
        build_user_prompt("class X {}", "CWE-79")
        raise AssertionError("expected UnsupportedCWE")
    except UnsupportedCWE:
        pass


def test_extract_java_pulls_code_from_fence():
    raw = "Here is the fix:\n```java\nclass Safe {}\n```\nDone."
    assert extract_java(raw) == "class Safe {}"


def test_extract_java_falls_back_to_raw_when_no_fence():
    assert extract_java("class Safe {}") == "class Safe {}"


# --- The remote client talks to the endpoint correctly (GPU mocked) --------


class _FakeMessage:
    def __init__(self, content: str) -> None:
        self.content = content


class _FakeChoice:
    def __init__(self, content: str) -> None:
        self.message = _FakeMessage(content)


class _FakeResponse:
    def __init__(self, content: str) -> None:
        self.choices = [_FakeChoice(content)]


class _FakeCompletions:
    def __init__(self) -> None:
        self.kwargs: dict = {}

    def create(self, **kwargs):
        self.kwargs = kwargs
        return _FakeResponse("```java\nclass Fixed {}\n```")


class _FakeOpenAIClient:
    def __init__(self) -> None:
        self.chat = type("Chat", (), {"completions": _FakeCompletions()})()


def test_remote_client_sends_tuned_request_and_extracts_code():
    fixer = RemoteVulnFixerClient()  # no network at construction
    fake = _FakeOpenAIClient()
    fixer._client = fake  # inject: skip the real OpenAI HTTP client

    out = fixer.fix(code="class X {}", cwe="cwe-89")  # lower-case normalises

    assert out == "class Fixed {}"  # fence stripped
    kwargs = fake.chat.completions.kwargs
    assert kwargs["model"] == "vuln-fixer"
    assert kwargs["temperature"] == 0.0
    assert kwargs["max_tokens"] == 1024
    assert kwargs["messages"][0] == {"role": "system", "content": VULN_FIXER_SYSTEM}
    assert kwargs["messages"][1]["content"] == build_user_prompt("class X {}", "CWE-89")


# --- The mock client returns a genuinely secure rewrite (no GPU) -----------


def test_mock_fixer_parameterises_sql():
    out = MockVulnFixerClient().fix(code="anything", cwe="CWE-89")
    assert "PreparedStatement" in out
    assert "setString(1, userId)" in out
    assert "'\" + userId + \"'" not in out  # the concatenation is gone


def test_fix_java_vulnerability_entrypoint_uses_mock_by_default():
    out = fix_java_vulnerability("class X {}", "CWE-89")
    assert "PreparedStatement" in out


# --- The planner drops into the same gated OPEN_PR seam as the CI Fixer -----


def test_planner_proposes_gated_open_pr():
    fixer = JavaVulnFixer(
        github=MockGitHubClient(),
        vuln_fixer=MockVulnFixerClient(),
        repo="owner/repo",
        ref="main",
        file_path="src/main/java/com/acme/payments/PaymentRepository.java",
        cwe="CWE-89",
    )
    plan = fixer.plan(state=None, llm=None)  # plan ignores state/llm here
    assert plan.requires_approval is True
    action = plan.actions[0]
    assert action.action == RemediationActionType.OPEN_PR
    assert action.fix is not None
    assert "PreparedStatement" in action.fix.new_content
    assert "CWE-89" in action.fix.pr_title


# --- Routing: a security-scan failure goes to the vuln fixer, CI failures don't


def _run(name: str) -> WorkflowRun:
    return WorkflowRun(
        run_id=1, repo="acme/incident-agent-demo", name=name,
        head_branch="main", head_sha="abc", conclusion="failure",
    )


def test_security_workflow_name_routes_to_vuln_fixer():
    assert is_security_failure(_run("security-scan"), logs="build ok") is True
    assert is_security_failure(_run("codeql"), logs="") is True


def test_cwe_in_logs_routes_to_vuln_fixer_even_without_name():
    logs = "SAST: CWE-89 detected in src/main/java/com/acme/payments/PaymentRepository.java:23"
    assert is_security_failure(_run("deploy"), logs=logs) is True


def test_generic_ci_failure_does_not_route_to_vuln_fixer():
    assert is_security_failure(_run("deploy"), logs="java.lang.OutOfMemoryError") is False


def test_parse_sast_finding_extracts_cwe_and_java_file():
    logs = (
        "::error file=src/main/java/com/acme/payments/PaymentRepository.java,line=23::"
        "CWE-89 SQL Injection: untrusted input is concatenated into a SQL query"
    )
    cwe, path = parse_sast_finding(logs)
    assert cwe == "CWE-89"
    assert path == "src/main/java/com/acme/payments/PaymentRepository.java"


def test_parse_sast_finding_returns_none_when_absent():
    assert parse_sast_finding("nothing to see here") == (None, None)


# --- End-to-end: SAST finding -> gate -> PR (the judge demo path) -----------


def test_simulate_vuln_is_gated_and_opens_pr_after_approval():
    client.delete("/incidents")

    state = client.post("/github/simulate-vuln").json()
    assert state["status"] == "awaiting_approval"
    action = state["plan"]["actions"][0]
    assert action["action"] == "open_pr"
    assert "PaymentRepository.java" in action["fix"]["file_path"]
    assert "PreparedStatement" in action["fix"]["new_content"]  # real security fix

    done = client.post(
        f"/incidents/{state['id']}/approve", json={"approved": True}
    ).json()
    assert done["status"] == "resolved"
    out = done["remediation_results"][0]["output"]
    assert "opened PR #" in out


def test_simulate_vuln_rejected_opens_no_pr():
    client.delete("/incidents")
    state = client.post("/github/simulate-vuln").json()
    done = client.post(
        f"/incidents/{state['id']}/approve", json={"approved": False}
    ).json()
    assert done["status"] == "rejected"
    assert done["remediation_results"] == []
