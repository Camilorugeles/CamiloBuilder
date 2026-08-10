from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping

from .models import InputReference
from .validation import validate_agent_definition, validate_execution_record


def _canonical(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _identifier(prefix: str, value: object) -> str:
    digest = hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()
    return f"{prefix}:sha256:{digest}"


def _error(code: str, message: str) -> dict[str, str]:
    return {"code": code, "message": message}


def _policies(definition):
    return {
        item["action_id"]: item["approval"]
        for item in definition["authorized_actions"]
    }


def _new_record(definition, run_id, input_reference):
    return {
        "schema_version": 1,
        "record_version": "1.0.0",
        "revision": 1,
        "run_id": run_id,
        "agent_id": definition["agent_id"],
        "agent_version": definition["version"],
        "status": "completed",
        "input_refs": [input_reference.as_dict()],
        "results": [],
        "proposed_actions": [],
        "human_decision": None,
        "executed_actions": [],
        "errors": [],
        "escalation": None,
        "evidence_refs": [],
    }


def _store_failed(store, record, code, message):
    record["status"] = "failed"
    record["errors"] = [_error(code, message)]
    validate_execution_record(record)
    store.create(record)
    return store.get(record["run_id"])


def run_agent(
    *, definition, behavior, connector, approval_gateway, record_store,
    input_reference: InputReference, operation_key: str,
):
    definition = validate_agent_definition(definition)
    run_id = _identifier(
        "run",
        {
            "agent_id": definition["agent_id"],
            "agent_version": definition["version"],
            "input_refs": [input_reference.as_dict()],
            "operation_key": operation_key,
        },
    )
    existing = record_store.get(run_id)
    if existing is not None:
        return existing
    record = _new_record(definition, run_id, input_reference)
    sources = {item["source_id"] for item in definition["authorized_sources"]}
    if input_reference.source_id not in sources:
        return _store_failed(
            record_store, record, "unauthorized-source", "Input source is not authorized"
        )
    try:
        analysis = behavior.analyze(
            input_reference=input_reference,
            connector=connector,
        )
    except Exception as error:
        return _store_failed(
            record_store, record, "technical-error", f"{type(error).__name__}: {error}"
        )
    record["results"] = sorted(
        [dict(item) for item in analysis.results], key=lambda item: item["result_id"]
    )
    record["evidence_refs"] = sorted(set(analysis.evidence_refs))
    if analysis.escalation is not None:
        record["status"] = "needs_review"
        record["escalation"] = dict(analysis.escalation)
        validate_execution_record(record)
        record_store.create(record)
        return record_store.get(run_id)

    policies = _policies(definition)
    requested_actions = []
    required_count = 0
    seen_requests = set()
    for requested in sorted(analysis.proposed_actions, key=lambda item: item["action_id"]):
        action_id = requested["action_id"]
        parameters = dict(requested.get("parameters", {}))
        request_key = (action_id, _canonical(parameters))
        if request_key in seen_requests:
            continue
        seen_requests.add(request_key)
        policy = policies.get(action_id)
        if policy is None:
            return _store_failed(
                record_store, record, "undeclared-action", f"Action is not declared: {action_id}"
            )
        if policy == "forbidden":
            return _store_failed(
                record_store, record, "forbidden-action", f"Action is forbidden: {action_id}"
            )
        required_count += policy == "required"
        requested_actions.append((action_id, parameters, policy))
    if required_count > 1:
        return _store_failed(
            record_store,
            record,
            "multiple-approval-actions",
            "A run may contain at most one action requiring human approval",
        )

    pending = False
    for action_id, parameters, policy in requested_actions:
        proposal_id = _identifier(
            "proposal",
            {"action_id": action_id, "parameters": parameters, "run_id": run_id},
        )
        proposal = {
            "action_id": action_id,
            "approval": policy,
            "parameters": parameters,
            "proposal_id": proposal_id,
            "status": "pending" if policy == "required" else "approved",
        }
        record["proposed_actions"].append(proposal)
        if policy == "required":
            pending = True
            approval_gateway.request(proposal)
            continue
        outcome = connector.execute(
            action_id=action_id,
            parameters=parameters,
            idempotency_key=proposal_id,
        )
        record["executed_actions"].append({
            "action_id": action_id,
            "execution_id": _identifier("execution", {"proposal_id": proposal_id}),
            "outcome": outcome.outcome,
            "proposal_id": proposal_id,
            "result_ref": outcome.result_ref,
        })
    record["proposed_actions"] = sorted(
        record["proposed_actions"], key=lambda item: item["proposal_id"]
    )
    record["executed_actions"] = sorted(
        record["executed_actions"], key=lambda item: item["execution_id"]
    )
    record["status"] = "pending_approval" if pending else "completed"
    validate_execution_record(record)
    record_store.create(record)
    return record_store.get(run_id)


def resume_agent(
    *, run_id, definition, connector, approval_gateway, record_store,
):
    definition = validate_agent_definition(definition)
    record = record_store.get(run_id)
    if record is None:
        raise KeyError(f"Unknown run: {run_id}")
    if record["agent_id"] != definition["agent_id"]:
        raise ValueError("Agent Definition does not match execution record")
    if record["status"] != "pending_approval":
        return record
    pending = next(
        (item for item in record["proposed_actions"] if item["status"] == "pending"),
        None,
    )
    if pending is None:
        return record
    decision = approval_gateway.get_decision(pending["proposal_id"])
    if decision is None:
        return record
    previous_revision = record["revision"]
    record["human_decision"] = decision.as_dict()
    if decision.decision == "rejected":
        pending["status"] = "rejected"
        record["status"] = "completed"
    elif decision.decision == "approved":
        pending["status"] = "approved"
        if not any(
            item["proposal_id"] == pending["proposal_id"]
            for item in record["executed_actions"]
        ):
            try:
                outcome = connector.execute(
                    action_id=pending["action_id"],
                    parameters=pending["parameters"],
                    idempotency_key=pending["proposal_id"],
                )
            except Exception as error:
                record["status"] = "failed"
                record["errors"] = [
                    _error("technical-error", f"{type(error).__name__}: {error}")
                ]
                validate_execution_record(record)
                record_store.replace(record, expected_revision=previous_revision)
                return record_store.get(run_id)
            record["executed_actions"].append({
                "action_id": pending["action_id"],
                "execution_id": _identifier(
                    "execution",
                    {
                        "decision": decision.as_dict(),
                        "proposal_id": pending["proposal_id"],
                    },
                ),
                "outcome": outcome.outcome,
                "proposal_id": pending["proposal_id"],
                "result_ref": outcome.result_ref,
            })
        record["status"] = "completed"
    else:
        raise ValueError(f"Unsupported approval decision: {decision.decision}")
    record["executed_actions"] = sorted(
        record["executed_actions"], key=lambda item: item["execution_id"]
    )
    validate_execution_record(record)
    record_store.replace(record, expected_revision=previous_revision)
    return record_store.get(run_id)


def stable_json(record: Mapping[str, object]) -> str:
    return json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
