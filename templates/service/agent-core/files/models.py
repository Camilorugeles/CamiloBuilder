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
class ConnectorItem:
    reference: str
    metadata: Mapping[str, object]
    content_refs: tuple[str, ...] = ()


@dataclass(frozen=True)
class ConnectorContent:
    reference: str
    media_type: str
    content: bytes


@dataclass(frozen=True)
class AgentAnalysis:
    results: tuple[dict[str, object], ...] = ()
    proposed_actions: tuple[dict[str, object], ...] = ()
    evidence_refs: tuple[str, ...] = ()
    escalation: dict[str, str] | None = None


@dataclass(frozen=True, init=False)
class ApprovalDecision:
    decision: str
    decided_by: str
    decision_ref: str
    notes: str
    decided_at: str | None

    def __init__(self, decision, decided_by=None, decision_ref="", notes="", decided_at=None, *, actor_reference=None):
        actor = actor_reference if actor_reference is not None else decided_by
        if not actor:
            raise ValueError("actor_reference is required")
        if decided_by is not None and actor_reference is not None and decided_by != actor_reference:
            raise ValueError("Conflicting actor references")
        object.__setattr__(self, "decision", decision)
        object.__setattr__(self, "decided_by", actor)
        object.__setattr__(self, "decision_ref", decision_ref)
        object.__setattr__(self, "notes", notes)
        object.__setattr__(self, "decided_at", decided_at)

    @property
    def actor_reference(self): return self.decided_by

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
