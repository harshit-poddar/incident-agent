from __future__ import annotations

from app.llm.mock import default_mock_client
from app.llm.replay import RecordingLLMClient, ReplayLLMClient, fixture_key
from app.orchestration.state import IncidentState, IncidentStatus
from app.orchestration.supervisor import Supervisor
from app.schemas.incident import Diagnosis, Signal
from app.tools.knowledge import KnowledgeTool
from app.tools.remediation import MockCluster, RemediationExecutor
from app.tools.schemas import ApprovalDecision
from app.tools.telemetry import TelemetryTool


def _signal() -> Signal:
    return Signal(
        service="payments-api",
        metric="error_rate",
        value=0.38,
        threshold=0.02,
        message="5xx error rate breached threshold",
    )


def _run(llm, cluster):
    supervisor = Supervisor(llm, KnowledgeTool(), TelemetryTool(), RemediationExecutor(cluster))
    provider = lambda s: ApprovalDecision(approved=True, approver="auto", reason="t")
    return supervisor.run(IncidentState(signal=_signal()), provider)


def test_capture_then_replay_reproduces_resolution(tmp_path):
    # Capture: wrap the mock, run the graph, fixtures land in tmp_path.
    recorder = RecordingLLMClient(default_mock_client(), tmp_path)
    cap_cluster = MockCluster()
    cap_cluster.register("payments-api")
    cap_cluster.inject_fault("payments-api")
    _run(recorder, cap_cluster)

    # One fixture per agent call: Detection, Diagnosis, RemediationPlan, Verification.
    assert len(recorder.captured) == 4
    assert {p.name.split(".")[0] for p in recorder.captured} == {
        "Detection",
        "Diagnosis",
        "RemediationPlan",
        "Verification",
    }

    # Replay: no model involved, graph still resolves identically.
    replay_cluster = MockCluster()
    replay_cluster.register("payments-api")
    replay_cluster.inject_fault("payments-api")
    state = _run(ReplayLLMClient(tmp_path), replay_cluster)

    assert state.status == IncidentStatus.RESOLVED
    assert state.verification and state.verification.resolved
    assert replay_cluster.services["payments-api"] == "healthy"


def test_replay_falls_back_when_prompt_drifts(tmp_path):
    # Seed fixtures, then ask with a prompt that was never recorded.
    RecordingLLMClient(default_mock_client(), tmp_path).generate(
        system="sys", user="original user", output_model=Diagnosis
    )
    replay = ReplayLLMClient(tmp_path)

    # Exact hash differs, but the lenient per-model fallback still serves it.
    assert fixture_key("sys", "drifted user") != fixture_key("sys", "original user")
    out = replay.generate(system="sys", user="drifted user", output_model=Diagnosis)
    assert isinstance(out, Diagnosis)
    assert out.root_cause


def test_empty_fixtures_dir_raises(tmp_path):
    try:
        ReplayLLMClient(tmp_path)
        raise AssertionError("expected FileNotFoundError for empty fixtures dir")
    except FileNotFoundError:
        pass
