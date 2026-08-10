from __future__ import annotations

from typing import Mapping, Protocol

from .models import ActionOutcome, AgentAnalysis, ApprovalDecision, InputReference


class ConnectorPort(Protocol):
    def read(self, reference: InputReference) -> Mapping[str, object]: ...

    def execute(
        self,
        *,
        action_id: str,
        parameters: Mapping[str, object],
        idempotency_key: str,
    ) -> ActionOutcome: ...


class ApprovalGateway(Protocol):
    def request(self, proposal: Mapping[str, object]) -> None: ...

    def get_decision(self, proposal_id: str) -> ApprovalDecision | None: ...


class ExecutionRecordStore(Protocol):
    def get(self, run_id: str) -> dict[str, object] | None: ...

    def create(self, record: dict[str, object]) -> None: ...

    def replace(self, record: dict[str, object], *, expected_revision: int) -> None: ...


class AgentBehavior(Protocol):
    def analyze(
        self,
        *,
        input_reference: InputReference,
        connector: ConnectorPort,
    ) -> AgentAnalysis: ...
