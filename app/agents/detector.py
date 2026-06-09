from __future__ import annotations

from app.llm.base import LLMClient
from app.schemas.incident import Detection, Signal

SYSTEM = (
    "You are the Detector agent in an autonomous incident-response system. "
    "Decide whether a signal is a genuine anomaly worth investigating."
)


def detect(signal: Signal, llm: LLMClient) -> Detection:
    user = (
        f"Signal: service={signal.service} metric={signal.metric} "
        f"value={signal.value} threshold={signal.threshold} msg={signal.message!r}"
    )
    return llm.generate(system=SYSTEM, user=user, output_model=Detection)
