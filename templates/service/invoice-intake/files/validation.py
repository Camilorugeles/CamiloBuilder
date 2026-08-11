from __future__ import annotations

import json
from pathlib import Path

from jsonschema import Draft202012Validator
from referencing import Registry


SCHEMAS = Path(__file__).resolve().parent / "schemas"


class InvoiceIntakeConfigurationError(ValueError): pass
class InvoiceAnalysisError(ValueError): pass


def _read_json(path: Path):
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        raise InvoiceIntakeConfigurationError("Unsafe or missing JSON source")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise InvoiceIntakeConfigurationError("Invalid JSON source") from error


def _validate(document, schema_name, error_type):
    schema = json.loads((SCHEMAS / schema_name).read_text(encoding="utf-8"))
    def reject_remote(uri): raise error_type(f"Remote schema retrieval forbidden: {uri}")
    validator = Draft202012Validator(schema, registry=Registry(retrieve=reject_remote))
    errors = sorted(validator.iter_errors(document), key=lambda e: tuple(str(p) for p in e.absolute_path))
    if errors: raise error_type(errors[0].message)
    return document


def load_pilot_configuration(path):
    document = _validate(_read_json(Path(path)), "invoice-pilot-config.schema.json", InvoiceIntakeConfigurationError)
    refs = document["selection"]["pilot_message_refs"]
    if refs != sorted(set(refs)):
        raise InvoiceIntakeConfigurationError("pilot_message_refs must be sorted and unique")
    if document["selection"]["max_messages"] > 15 or len(refs) > document["selection"]["max_messages"]:
        raise InvoiceIntakeConfigurationError("Pilot message limit exceeded")
    for field in ("legal_entities", "activities", "document_types", "knowledge_refs", "reviewer_refs"):
        values = document[field]
        if values != sorted(set(values)):
            raise InvoiceIntakeConfigurationError(f"{field} must be sorted and unique")
    return document


def validate_invoice_analysis(document):
    return _validate(document, "invoice-analysis.schema.json", InvoiceAnalysisError)
