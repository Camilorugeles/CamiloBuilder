from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping


@dataclass(frozen=True)
class InputReference:
    source_id: str
    reference: str

    def as_dict(self) -> dict[str, str]:
        return {"reference": self.reference, "source_id": self.source_id}


@dataclass(frozen=True)
class AgentAnalysis:
    results: tuple[dict[str, object], ...] = ()
    proposed_actions: tuple[dict[str, object], ...] = ()
    evidence_refs: tuple[str, ...] = ()
    escalation: dict[str, str] | None = None


@dataclass(frozen=True)
class ApprovalDecision:
    decision: str
    decided_by: str
    decision_ref: str
    notes: str = ""

    def as_dict(self) -> dict[str, str]:
        return {
            "decided_by": self.decided_by,
            "decision": self.decision,
            "decision_ref": self.decision_ref,
            "notes": self.notes,
        }


@dataclass(frozen=True)
class ActionOutcome:
    outcome: str
    result_ref: str


AgentDefinition = Mapping[str, object]
ExecutionRecord = dict[str, object]
