"""The contract between an engine and the policy, plus the policy itself.

Everything here is deterministic code. It never changes between the
"with jev" and "without jev" runs: that is the point of the demo.
"""

from dataclasses import dataclass

ALLOW = "ALLOW"
CONFIRM = "CONFIRM"
BLOCK = "BLOCK"
ASK_HUMAN = "ASK_HUMAN"

RISK_READ_ONLY = "read_only"
RISK_MUTATING = "mutating"
RISK_DESTRUCTIVE = "destructive"
RISK_UNKNOWN = "unknown"

AUTO_TRUST = 0.85
REVIEW_FLOOR = 0.50


@dataclass(frozen=True)
class Judgments:
    """What every engine must return, whether it used Jev or keywords."""

    risk: str
    confidence: float
    data_loss: float
    blast_radius: float
    reason: str
    source: str


def decide(j: Judgments) -> str:
    """Routing policy. Code owns it; the engine only supplies judgments."""

    if j.confidence < REVIEW_FLOOR:
        return ASK_HUMAN
    if j.risk == RISK_DESTRUCTIVE:
        return BLOCK if j.confidence >= AUTO_TRUST else CONFIRM
    if j.risk == RISK_MUTATING:
        return CONFIRM
    if j.risk == RISK_READ_ONLY and j.confidence >= AUTO_TRUST:
        return ALLOW
    return CONFIRM