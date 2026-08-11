from __future__ import annotations

from typing import Iterable, Mapping, Protocol

from .models import (
    ActionOutcome, AgentAnalysis, ApprovalDecision, ConnectorContent,
    ConnectorItem, InputReference,
)


class ConnectorPort(Protocol):
    connector_id: str
    provider_id: str

    def capabilities(self) -> frozenset[str]: ...

    def list_items(self, *, source_id: str) -> Iterable[ConnectorItem]: ...

    def read(self, reference: InputReference) -> Mapping[str, object]: ...

    def read_content(self, reference: str) -> ConnectorContent: ...

    def execute(
        self,
        *,
        action_id: str,
        parameters: Mapping[str, object],
        idempotency_key: str,
    ) -> ActionOutcome: ...


class ConnectorResolver(Protocol):
    def resolve(self, connector_id: str) -> ConnectorPort: ...

    def resolve_for_agent(self, *, definition, source_id: str) -> ConnectorPort: ...


class SecretProvider(Protocol):
    def resolve(self, credential_ref: str): ...


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
