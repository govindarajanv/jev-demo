"""The engine you write without Jev: keyword lists.

It has the same interface, so the same policy runs against it. A rule engine
is always certain, so it reports confidence 1.0 for whatever it matched, and
anything it cannot match falls through as unknown.
"""

import re

from .policy import (
    RISK_DESTRUCTIVE,
    RISK_MUTATING,
    RISK_READ_ONLY,
    RISK_UNKNOWN,
    Judgments,
)

READ_ONLY_VERBS = {
    "get", "describe", "logs", "top", "explain", "api-resources", "api-versions",
    "version", "cluster-info", "diff", "port-forward", "wait", "config", "events",
}

MUTATING_VERBS = {
    "apply", "create", "patch", "replace", "scale", "rollout", "annotate",
    "label", "set", "expose", "run", "autoscale", "cp", "attach", "exec",
}

DESTRUCTIVE_PATTERNS = [
    r"\bdelete\b",
    r"\bdrain\b",
    r"\brm\s+-rf\b",
    r"\bdrop\s+(table|database)\b",
    r"\bevict\b",
    r"--force\b",
]


class KeywordEngine:
    @property
    def name(self) -> str:
        return "keywords"

    def judge(self, state: dict) -> Judgments:
        command = state["command"]
        tokens = re.findall(r"[a-zA-Z_][a-zA-Z0-9_.-]*", command)
        verbs = {token for token in tokens if token in READ_ONLY_VERBS | MUTATING_VERBS}
        destructive_hit = next(
            (p for p in DESTRUCTIVE_PATTERNS if re.search(p, command)), None
        )

        if destructive_hit:
            return self._result(RISK_DESTRUCTIVE, f"matched {destructive_hit!r}")
        if verbs & MUTATING_VERBS:
            return self._result(RISK_MUTATING, f"verb {sorted(verbs & MUTATING_VERBS)[0]!r}")
        if verbs & READ_ONLY_VERBS:
            return self._result(RISK_READ_ONLY, f"verb {sorted(verbs & READ_ONLY_VERBS)[0]!r}")
        return self._result(RISK_UNKNOWN, "no verb matched")

    def _result(self, risk: str, reason: str) -> Judgments:
        data_loss = 1.0 if risk == RISK_DESTRUCTIVE else 0.0
        blast_radius = {"read_only": 0.0, "unknown": 0.0, "mutating": 1.0, "destructive": 2.0}[risk]
        return Judgments(
            risk=risk,
            confidence=1.0,
            data_loss=data_loss,
            blast_radius=blast_radius,
            reason=reason,
            source=self.name,
        )