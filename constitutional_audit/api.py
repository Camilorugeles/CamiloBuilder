from datetime import datetime
from pathlib import Path

from capability_introspection import IntrospectionError, describe_camilobuilder
from capability_introspection.constitution import (
    ConstitutionSourceError,
    read_constitution_version,
)
from constitutional_audit.controls import CONTROL_BY_ID
from constitutional_audit.validation import (
    AST_ANALYSIS_SCOPE,
    EXCEPTION_TRANSITIONS,
    WORK_ORDER_TRANSITIONS,
    SourceError,
    ValidationUnavailable,
    architecture_issues,
    history_issues,
    load_json,
    local_schema_reference_issues,
    safe_path,
    static_dependency_issues,
    validate_with_schema,
)


DEFAULT_ROOT = Path(__file__).resolve().parents[1]
CRITICAL_PROVISIONS = {
    "principle.failure-safe",
    "principle.least-privilege",
    "principle.non-destruction",
}
NON_EXCUSABLE_CODES = {
    "constitution-version-unknown",
    "exception-registry-invalid",
    "exception-schema-invalid",
    "exception-validation-unavailable",
}
CONTROL_SOURCES = {
    "control.architecture.contracts": ["governance/architecture/registry.json"],
    "control.architecture.dependencies": ["governance/architecture/registry.json"],
    "control.architecture.modules": ["governance/architecture/registry.json"],
    "control.architecture.no-derived-inventories": ["governance/architecture/registry.json"],
    "control.architecture.registry-schema": ["governance/architecture/registry.json", "governance/schemas/v3/architecture.schema.json"],
    "control.architecture.runtime-coherence": ["governance/architecture/registry.json", "repository static Python imports"],
    "control.constitution.version": ["governance/CONSTITUTION.md"],
    "control.exceptions.integrity": ["governance/exceptions/index.json"],
    "control.exceptions.temporal-validity": ["governance/exceptions/index.json"],
    "control.introspection.coherence": ["capability_introspection.describe_camilobuilder"],
    "control.references.integrity": ["governance/architecture/registry.json", "governance/work-orders/index.json", "governance/exceptions/index.json"],
    "control.schemas.references": ["governance/schemas"],
    "control.schemas.selection": ["governance/schemas"],
    "control.schemas.validation": ["governance/schemas", "governance architecture and registry documents"],
    "control.work-orders.integrity": ["governance/work-orders/index.json"],
}


class AuditInputError(ValueError):
    """Raised before auditing when the explicit evaluation instant is invalid."""


def _finding(control_id, outcome, code, source_id, subject_ids):
    control = CONTROL_BY_ID[control_id]
    return {
        "control_id": control_id,
        "severity": control["severity"],
        "outcome": outcome,
        "code": code,
        "message": code.replace("-", " ").capitalize() + ".",
        "source_id": source_id,
        "constitutional_provision": control["constitutional_provision"],
        "subject_ids": sorted(set(subject_ids)),
        "exception_id": None,
    }


def _add(findings, control_id, outcome, code, source_id, *subjects):
    findings.append(_finding(control_id, outcome, code, source_id, list(subjects)))


def _load_index(root, relative_path, fields):
    entries = load_json(root, relative_path, list)
    ids = []
    paths = []
    documents = []
    for entry in entries:
        if not isinstance(entry, dict) or set(entry) != fields or not isinstance(entry.get("id"), str):
            raise SourceError("incoherent-index")
        ids.append(entry["id"])
        paths.append(entry["path"])
        document = load_json(root, entry["path"], dict)
        for field in fields - {"path"}:
            if document.get(field) != entry[field]:
                raise SourceError("incoherent-index")
        documents.append(document)
    if ids != sorted(set(ids)) or paths != sorted(set(paths)):
        raise SourceError("unordered-index")
    return entries, documents


def _schema_path(record_type, version):
    names = {
        "architecture": "architecture.schema.json",
        "work-order": "work-order.schema.json",
        "exception": "exception.schema.json",
    }
    supported = {
        "architecture": {1, 2, 3},
        "work-order": {1, 2},
        "exception": {1, 2},
    }
    if record_type not in supported or version not in supported[record_type]:
        raise SourceError("unknown-schema-version")
    return f"governance/schemas/v{version}/{names[record_type]}"


def _validate_record(root, record_type, document):
    version = document.get("schema_version")
    schema_relative = _schema_path(record_type, version)
    schema = load_json(root, schema_relative, dict)
    return validate_with_schema(document, schema)


def _exception_semantic_issues(document, instant, known_contracts, known_work_orders):
    issues = history_issues(document, EXCEPTION_TRANSITIONS)
    try:
        starts_at = datetime.fromisoformat(document["starts_at"])
        expires_at = datetime.fromisoformat(document["expires_at"])
    except (KeyError, TypeError, ValueError):
        return sorted(set(issues + ["invalid-exception-date"]))
    if starts_at >= expires_at:
        issues.append("invalid-exception-date-order")
    if document.get("status") == "active" and instant < starts_at:
        issues.append("active-exception-not-started")
    if document.get("status") == "active" and instant >= expires_at:
        issues.append("active-exception-expired")
    if document.get("status") == "expired":
        issues.append("expired-exception")
    if set(document.get("affected_contract_ids", [])) - known_contracts:
        issues.append("unknown-exception-contract")
    if document.get("remediation_work_order_id") not in known_work_orders:
        issues.append("unknown-remediation-work-order")
    if document.get("affected_capability_ids"):
        issues.append("unknown-exception-capability")
    return sorted(set(issues))


def _exception_covers(exception, finding, instant):
    if finding["outcome"] != "failed" or finding["code"] in NON_EXCUSABLE_CODES:
        return False
    if exception.get("status") != "active":
        return False
    try:
        starts = datetime.fromisoformat(exception["starts_at"])
        expires = datetime.fromisoformat(exception["expires_at"])
    except (KeyError, TypeError, ValueError):
        return False
    if not starts <= instant < expires:
        return False
    if exception.get("constitutional_provision") != finding["constitutional_provision"]:
        return False
    subjects = set(exception.get("affected_component_ids", []))
    subjects.update(exception.get("affected_contract_ids", []))
    subjects.update(exception.get("affected_capability_ids", []))
    if not set(finding["subject_ids"]).issubset(subjects):
        return False
    if not finding["subject_ids"]:
        return False
    if exception.get("constitutional_provision") in CRITICAL_PROVISIONS:
        if exception.get("approval_policy") != "critical" or len(exception.get("approval_ids", [])) < 2:
            return False
    return True


def _classify_result(controls):
    if any(
        item["status"] == "failed" and item["severity"] in {"critical", "error"}
        for item in controls
    ):
        return "non_compliant"
    if any(item["status"] == "indeterminate" for item in controls):
        return "indeterminate"
    if any(item["status"] == "excepted" for item in controls):
        return "compliant_with_exceptions"
    return "compliant"


def _perform_audit(root, instant):
    findings = []
    architecture = None
    work_orders = []
    exception_documents = []
    valid_active_exceptions = []
    schema_validation_available = True
    constitution_version = None

    try:
        architecture = load_json(root, "governance/architecture/registry.json", dict)
    except SourceError:
        for control_id in (
            "control.architecture.registry-schema", "control.architecture.modules",
            "control.architecture.dependencies", "control.architecture.contracts",
            "control.architecture.no-derived-inventories", "control.architecture.runtime-coherence",
            "control.constitution.version", "control.references.integrity",
        ):
            _add(findings, control_id, "indeterminate", "architecture-registry-unavailable", "governance/architecture/registry.json", "architecture.camilobuilder")

    if architecture is not None:
        try:
            if architecture.get("schema_version") not in {1, 2, 3}:
                _add(findings, "control.schemas.selection", "failed", "unknown-schema-version", "governance/architecture/registry.json", "architecture.camilobuilder")
            errors = _validate_record(root, "architecture", architecture)
            for _error in errors:
                _add(findings, "control.architecture.registry-schema", "failed", "architecture-schema-invalid", "governance/architecture/registry.json", "architecture.camilobuilder")
                break
        except ValidationUnavailable:
            schema_validation_available = False
            _add(findings, "control.architecture.registry-schema", "indeterminate", "schema-validation-unavailable", "governance/schemas/v3/architecture.schema.json", "architecture.camilobuilder")
        except SourceError as error:
            outcome = "failed" if str(error) == "unknown-schema-version" else "indeterminate"
            _add(findings, "control.architecture.registry-schema", outcome, str(error), "governance/architecture/registry.json", "architecture.camilobuilder")

        try:
            groups = architecture_issues(root, architecture)
            mapping = {
                "modules": "control.architecture.modules",
                "dependencies": "control.architecture.dependencies",
                "contracts": "control.architecture.contracts",
                "inventories": "control.architecture.no-derived-inventories",
            }
            for group, issues in groups.items():
                for code, subject in issues:
                    _add(findings, mapping[group], "failed", code, "governance/architecture/registry.json", subject)
        except (KeyError, TypeError, SourceError):
            for control_id in (
                "control.architecture.modules", "control.architecture.dependencies",
                "control.architecture.contracts", "control.architecture.no-derived-inventories",
            ):
                _add(findings, control_id, "indeterminate", "architecture-structure-unavailable", "governance/architecture/registry.json", "architecture.camilobuilder")
        try:
            for code, subject in static_dependency_issues(root, architecture):
                _add(findings, "control.architecture.runtime-coherence", "failed", code, "repository static Python imports", subject)
        except (KeyError, OSError, SyntaxError, SourceError):
            _add(findings, "control.architecture.runtime-coherence", "indeterminate", "static-analysis-unavailable", "repository static Python imports", "architecture.camilobuilder")

    try:
        constitution_version = read_constitution_version(root)
        if constitution_version != "2.0.0":
            _add(findings, "control.constitution.version", "failed", "constitution-version-unknown", "governance/CONSTITUTION.md", "constitution.camilobuilder")
    except ConstitutionSourceError:
        _add(findings, "control.constitution.version", "indeterminate", "constitution-unavailable", "governance/CONSTITUTION.md", "constitution.camilobuilder")

    schema_files = []
    try:
        schemas_root = safe_path(root, "governance/schemas", file=False)
        if any(path.is_symlink() for path in schemas_root.rglob("*")):
            raise SourceError("symlink-schema-source")
        schema_files = sorted(path for path in schemas_root.rglob("*.json") if path.is_file())
        for path in schema_files:
            relative = path.relative_to(root).as_posix()
            schema = load_json(root, relative, dict)
            if schema.get("$schema") != "https://json-schema.org/draft/2020-12/schema":
                _add(findings, "control.schemas.selection", "failed", "unknown-schema-draft", relative, "governance.schemas")
            directory_version = path.parent.name
            expected_version = int(directory_version[1:]) if directory_version.startswith("v") and directory_version[1:].isdigit() else None
            declared_version = schema.get("properties", {}).get("schema_version", {}).get("const")
            if expected_version is None or declared_version != expected_version:
                _add(findings, "control.schemas.selection", "failed", "schema-version-path-mismatch", relative, "governance.schemas")
            for code in local_schema_reference_issues(schema):
                _add(findings, "control.schemas.references", "failed", code, relative, "governance.schemas")
    except SourceError:
        _add(findings, "control.schemas.selection", "indeterminate", "schema-catalog-unavailable", "governance/schemas", "governance.schemas")
        _add(findings, "control.schemas.references", "indeterminate", "schema-catalog-unavailable", "governance/schemas", "governance.schemas")

    try:
        work_order_index, work_orders = _load_index(
            root, "governance/work-orders/index.json", {"id", "title", "status", "path"}
        )
        known_work_orders = {item["id"] for item in work_order_index}
        for entry, document in zip(work_order_index, work_orders):
            try:
                if document.get("schema_version") not in {1, 2}:
                    _add(findings, "control.schemas.selection", "failed", "unknown-schema-version", entry["path"], entry["id"])
                errors = _validate_record(root, "work-order", document)
                if errors:
                    _add(findings, "control.work-orders.integrity", "failed", "work-order-schema-invalid", entry["path"], entry["id"])
            except ValidationUnavailable:
                schema_validation_available = False
                _add(findings, "control.work-orders.integrity", "indeterminate", "schema-validation-unavailable", entry["path"], entry["id"])
            except SourceError as error:
                _add(findings, "control.work-orders.integrity", "failed", str(error), entry["path"], entry["id"])
            for issue in history_issues(document, WORK_ORDER_TRANSITIONS):
                _add(findings, "control.work-orders.integrity", "failed", issue, entry["path"], entry["id"])
    except SourceError as error:
        known_work_orders = set()
        outcome = "failed" if str(error) in {"incoherent-index", "unordered-index"} else "indeterminate"
        _add(findings, "control.work-orders.integrity", outcome, "work-order-index-invalid", "governance/work-orders/index.json", "governance.work-orders")

    known_contracts = set(architecture.get("contract_ids", [])) if architecture else set()
    if architecture is not None:
        for document in work_orders:
            work_id = document.get("id", "governance.work-orders")
            for contract in sorted(set(document.get("affected_contract_ids", [])) - known_contracts):
                _add(findings, "control.references.integrity", "failed", "unknown-work-order-contract", "governance/work-orders/index.json", contract)
            for dependency in sorted(set(document.get("dependency_ids", [])) - known_work_orders):
                _add(findings, "control.references.integrity", "failed", "unknown-work-order-dependency", "governance/work-orders/index.json", dependency)

    exception_registry_valid = True
    try:
        exception_index, exception_documents = _load_index(
            root, "governance/exceptions/index.json", {"id", "status", "path"}
        )
        for entry, document in zip(exception_index, exception_documents):
            valid_document = True
            try:
                if document.get("schema_version") not in {1, 2}:
                    valid_document = False
                    _add(findings, "control.schemas.selection", "failed", "unknown-schema-version", entry["path"], entry["id"])
                errors = _validate_record(root, "exception", document)
                if errors:
                    valid_document = False
                    _add(findings, "control.exceptions.integrity", "failed", "exception-schema-invalid", entry["path"], entry["id"])
            except ValidationUnavailable:
                schema_validation_available = False
                valid_document = False
                exception_registry_valid = False
                _add(findings, "control.exceptions.integrity", "indeterminate", "exception-validation-unavailable", entry["path"], entry["id"])
            except SourceError as error:
                valid_document = False
                _add(findings, "control.exceptions.integrity", "failed", str(error), entry["path"], entry["id"])
            semantic = _exception_semantic_issues(document, instant, known_contracts, known_work_orders)
            for issue in semantic:
                control = "control.exceptions.temporal-validity" if issue in {
                    "active-exception-expired", "active-exception-not-started",
                    "expired-exception", "invalid-exception-date", "invalid-exception-date-order"
                } else "control.references.integrity" if issue.startswith("unknown-") else "control.exceptions.integrity"
                _add(findings, control, "failed", issue, entry["path"], entry["id"])
                valid_document = False
            if valid_document and document.get("status") == "active":
                valid_active_exceptions.append(document)
    except SourceError as error:
        exception_registry_valid = False
        outcome = "failed" if str(error) in {"incoherent-index", "unordered-index"} else "indeterminate"
        _add(findings, "control.exceptions.integrity", outcome, "exception-registry-invalid", "governance/exceptions/index.json", "governance.exceptions")

    if not schema_validation_available:
        _add(findings, "control.schemas.validation", "indeterminate", "schema-validation-unavailable", "governance/schemas", "governance.schemas")
    else:
        governed_schema_findings = [
            item for item in findings
            if item["code"].endswith("schema-invalid") or item["code"] == "unknown-schema-version"
        ]
        if governed_schema_findings:
            _add(findings, "control.schemas.validation", "failed", "governed-schema-validation-failed", "governance/schemas", "governance.schemas")

    try:
        description = describe_camilobuilder(repository_root=root)
        if architecture is None:
            raise IntrospectionError("architecture unavailable")
        expected_dependencies = [
            {
                "module_id": module["id"],
                "allowed_dependency_ids": sorted(module["allowed_dependency_ids"]),
                "prohibited_dependency_ids": sorted(module["prohibited_dependency_ids"]),
            }
            for module in sorted(architecture["modules"], key=lambda item: item["id"])
        ]
        expected_active_exceptions = [
            entry for entry in exception_index if entry["status"] == "active"
        ]
        if (
            description["identity"]["value"]["id"] != architecture.get("id")
            or
            description["architecture_version"]["value"] != architecture.get("architecture_version")
            or description["constitution_version"]["value"] != constitution_version
            or description["contracts"]["items"] != sorted(architecture.get("contract_ids", []))
            or description["architectural_dependencies"]["items"] != expected_dependencies
            or description["work_orders"]["items"] != work_order_index
            or description["active_exceptions"]["items"] != expected_active_exceptions
        ):
            _add(findings, "control.introspection.coherence", "failed", "introspection-source-mismatch", "capability_introspection.describe_camilobuilder", "architecture.camilobuilder")
    except (IntrospectionError, KeyError, TypeError, UnboundLocalError):
        _add(findings, "control.introspection.coherence", "indeterminate", "introspection-unavailable", "capability_introspection.describe_camilobuilder", "architecture.camilobuilder")

    if exception_registry_valid:
        for finding in findings:
            for exception in sorted(valid_active_exceptions, key=lambda item: item["id"]):
                if _exception_covers(exception, finding, instant):
                    finding["outcome"] = "excepted"
                    finding["exception_id"] = exception["id"]
                    break

    findings.sort(key=lambda item: (
        item["control_id"], item["code"], item["source_id"], tuple(item["subject_ids"])
    ))
    for index, finding in enumerate(findings, 1):
        finding["id"] = f"finding.{index:03d}"

    controls = []
    for control_id in sorted(CONTROL_BY_ID):
        related = [item for item in findings if item["control_id"] == control_id]
        outcomes = {item["outcome"] for item in related}
        if "failed" in outcomes:
            status = "failed"
        elif "indeterminate" in outcomes:
            status = "indeterminate"
        elif "excepted" in outcomes:
            status = "excepted"
        else:
            status = "passed"
        controls.append({
            "id": control_id,
            "title": CONTROL_BY_ID[control_id]["title"],
            "severity": CONTROL_BY_ID[control_id]["severity"],
            "status": status,
            "source_ids": sorted(CONTROL_SOURCES[control_id]),
            "finding_ids": [item["id"] for item in related],
            "exception_ids": sorted({item["exception_id"] for item in related if item["exception_id"]}),
        })

    result = _classify_result(controls)
    summary = {
        "passed": sum(item["status"] == "passed" for item in controls),
        "failed": sum(item["status"] == "failed" for item in controls),
        "excepted": sum(item["status"] == "excepted" for item in controls),
        "indeterminate": sum(item["status"] == "indeterminate" for item in controls),
    }
    return {
        "schema_version": 1,
        "report_version": "1.0.0",
        "evaluation_instant": instant.isoformat(),
        "result": result,
        "constitution_version": constitution_version or "unknown",
        "architecture_version": architecture.get("architecture_version", "unknown") if architecture else "unknown",
        "summary": summary,
        "active_exception_ids": sorted(item["id"] for item in valid_active_exceptions),
        "controls": controls,
        "findings": findings,
    }


def audit_camilobuilder(
    *,
    evaluation_instant: datetime,
    repository_root: Path | None = None,
) -> dict[str, object]:
    if not isinstance(evaluation_instant, datetime) or evaluation_instant.tzinfo is None or evaluation_instant.utcoffset() is None:
        raise AuditInputError("evaluation_instant must be a timezone-aware datetime")
    root = Path(repository_root) if repository_root is not None else DEFAULT_ROOT
    try:
        if root.is_symlink() or not root.is_dir():
            raise SourceError("invalid-repository-root")
        return _perform_audit(root, evaluation_instant)
    except AuditInputError:
        raise
    except Exception:
        controls = []
        findings = []
        for index, control_id in enumerate(sorted(CONTROL_BY_ID), 1):
            finding = _finding(
                control_id, "indeterminate", "audit-source-processing-failed",
                "governance", ["architecture.camilobuilder"],
            )
            finding["id"] = f"finding.{index:03d}"
            findings.append(finding)
            controls.append({
                "id": control_id,
                "title": CONTROL_BY_ID[control_id]["title"],
                "severity": CONTROL_BY_ID[control_id]["severity"],
                "status": "indeterminate",
                "source_ids": sorted(CONTROL_SOURCES[control_id]),
                "finding_ids": [finding["id"]],
                "exception_ids": [],
            })
        return {
            "schema_version": 1, "report_version": "1.0.0",
            "evaluation_instant": evaluation_instant.isoformat(), "result": "indeterminate",
            "constitution_version": "unknown", "architecture_version": "unknown",
            "summary": {"passed": 0, "failed": 0, "excepted": 0, "indeterminate": len(controls)},
            "active_exception_ids": [], "controls": controls, "findings": findings,
        }
