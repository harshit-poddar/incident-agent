from __future__ import annotations

from app.pipeline.logsource import LogLine
from app.schemas.incident import Signal


class LogMonitor:
    """Watches log lines for known failure signatures and, on a match, emits a
    Signal that opens an incident -- the 'auto-trigger' seam.

    Here the rule is intentionally simple: the monitor fires on the line that
    confirms an SLO breach (error rate over threshold), having already seen the
    OOM lead-up as context. In production these rules would be richer (regex,
    PromQL alert rules, or an anomaly model) but the contract is the same: a
    LogLine in, an optional Signal out."""

    def inspect(self, line: LogLine) -> Signal | None:
        if line.level != "ERROR":
            return None
        text = line.msg.lower()
        # Trip on the SLO-breach line, not on every symptom line.
        if "err_rate" in text:
            return Signal(
                service=line.service or "payments-api",
                metric="error_rate",
                value=0.38,
                threshold=0.02,
                message=line.msg,
            )
        return None
