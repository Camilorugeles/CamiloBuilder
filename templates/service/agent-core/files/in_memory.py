from __future__ import annotations

import copy
from collections.abc import Mapping

from .errors import ConcurrentUpdateError, DuplicateRunError
from .models import ActionOutcome, ApprovalDecision, InputReference


class InMemoryConnector:
    def __init__(self, items: Mapping[str, Mapping[str, object]]):
        self._items = copy.deepcopy(dict(items))
        self._outcomes: dict[str, ActionOutcome] = {}
        self.execution_count = 0

    def read(self, reference: InputReference) -> Mapping[str, object]:
        if reference.reference not in self._items:
            raise KeyError(f"Unknown input reference: {reference.reference}")
        return copy.deepcopy(self._items[reference.reference])

    def execute(self, *, action_id, parameters, idempotency_key):
        if idempotency_key not in self._outcomes:
            self.execution_count += 1
            self._outcomes[idempotency_key] = ActionOutcome(
                outcome="completed",
                result_ref=f"memory:action-result-{idempotency_key.split(':')[-1][:12]}",
            )
        return self._outcomes[idempotency_key]


class InMemoryApprovalGateway:
    def __init__(self):
        self.requests: dict[str, dict[str, object]] = {}
        self.decisions: dict[str, ApprovalDecision] = {}

    def request(self, proposal):
        self.requests.setdefault(str(proposal["proposal_id"]), copy.deepcopy(dict(proposal)))

    def decide(self, proposal_id: str, decision: ApprovalDecision) -> None:
        self.decisions[proposal_id] = decision

    def get_decision(self, proposal_id):
        return self.decisions.get(proposal_id)


class InMemoryExecutionRecordStore:
    def __init__(self):
        self._records: dict[str, dict[str, object]] = {}

    def get(self, run_id):
        record = self._records.get(run_id)
        return copy.deepcopy(record) if record is not None else None

    def create(self, record):
        run_id = str(record["run_id"])
        if run_id in self._records:
            raise DuplicateRunError(f"Run already exists: {run_id}")
        self._records[run_id] = copy.deepcopy(record)

    def replace(self, record, *, expected_revision):
        run_id = str(record["run_id"])
        current = self._records.get(run_id)
        if current is None or current["revision"] != expected_revision:
            raise ConcurrentUpdateError(f"Stale execution record: {run_id}")
        replacement = copy.deepcopy(record)
        replacement["revision"] = expected_revision + 1
        self._records[run_id] = replacement
