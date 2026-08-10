import json
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry

from .errors import DefinitionError, RecordError


SCHEMAS = Path(__file__).resolve().parent / "schemas"


def _load(path: Path) -> object:
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"Unsafe or missing JSON source: {path.name}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"Invalid JSON source: {path.name}") from error


def _validate(document: object, schema_name: str, error_type):
    schema = _load(SCHEMAS / schema_name)

    def reject_remote(uri):
        raise error_type(f"Remote schema retrieval forbidden: {uri}")

    validator = Draft202012Validator(
        schema,
        format_checker=FormatChecker(),
        registry=Registry(retrieve=reject_remote),
    )
    errors = sorted(
        validator.iter_errors(document),
        key=lambda error: (
            tuple(str(part) for part in error.absolute_path),
            error.validator,
            error.message,
        ),
    )
    if errors:
        raise error_type(errors[0].message)
    return document


def load_agent_definition(path: Path) -> dict[str, object]:
    try:
        document = _load(Path(path))
    except ValueError as error:
        raise DefinitionError(str(error)) from error
    return validate_agent_definition(document)


def validate_agent_definition(document: object) -> dict[str, object]:
    validated = dict(_validate(document, "agent-definition.schema.json", DefinitionError))
    ordered_fields = {
        "authorized_sources": "source_id",
        "authorized_actions": "action_id",
    }
    for field, identifier in ordered_fields.items():
        values = [item[identifier] for item in validated[field]]
        if values != sorted(set(values)):
            raise DefinitionError(f"{field} must be sorted and unique by {identifier}")
    for field in ("inputs", "outputs", "knowledge_refs"):
        values = validated[field]
        if values != sorted(set(values)):
            raise DefinitionError(f"{field} must be sorted and unique")
    for source in validated["authorized_sources"]:
        permissions = source["permissions"]
        if permissions != sorted(set(permissions)):
            raise DefinitionError("source permissions must be sorted and unique")
    return validated


def validate_execution_record(document: object) -> dict[str, object]:
    validated = dict(_validate(document, "execution-record.schema.json", RecordError))
    ordered_fields = {
        "input_refs": "reference",
        "results": "result_id",
        "proposed_actions": "proposal_id",
        "executed_actions": "execution_id",
        "errors": "code",
    }
    for field, identifier in ordered_fields.items():
        values = [item[identifier] for item in validated[field]]
        if values != sorted(set(values)):
            raise RecordError(f"{field} must be sorted and unique by {identifier}")
    evidence = validated["evidence_refs"]
    if evidence != sorted(set(evidence)):
        raise RecordError("evidence_refs must be sorted and unique")
    return validated
