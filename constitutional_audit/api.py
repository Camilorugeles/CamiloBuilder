from datetime import datetime
from pathlib import Path

from capability_introspection import IntrospectionError, describe_camilobuilder
from capability_introspection.constitution import (
    ConstitutionSourceError,
    read_constitution_version,
)
from capability_introspection.work_orders import (
    WorkOrderSourceError,
    discover_work_orders,
)
from constitutional_audit.controls import (
    CONTROL_BY_ID,
    MANUAL_ASSERTIONS,
    UNVERIFIED_OBLIGATIONS,
)
from constitutional_audit.validation import (
    AST_ANALYSIS_SCOPE,
    SourceError,
    ValidationUnavailable,
    architecture_issues,
    load_json,
    local_schema_reference_issues,
    safe_path,
    static_dependency_issues,
    validate_with_schema,
)


DEFAULT_ROOT = Path(__file__).resolve().parents[1]
ACTIVE_SCHEMA_PATHS = (
    "governance/schemas/v2/audit-report.schema.json",
    "governance/schemas/v3/architecture.schema.json",
)
CONTROL_SOURCES = {
    "control.architecture.contracts": ["governance/architecture/registry.json"],
    "control.architecture.dependencies": ["governance/architecture/registry.json"],
    "control.architecture.modules": ["governance/architecture/registry.json"],
    "control.architecture.no-derived-inventories": ["governance/architecture/registry.json"],
    "control.architecture.registry-schema": ["governance/architecture/registry.json", "governance/schemas/v3/architecture.schema.json"],
    "control.architecture.runtime-coherence": ["governance/architecture/registry.json", "repository static Python imports"],
    "control.constitution.version": ["governance/CONSTITUTION.md"],
    "control.governance.manual-assertion-sources": ["governance/MAINTAINERS.md"],
    "control.introspection.coherence": ["capability_introspection.describe_camilobuilder"],
    "control.references.integrity": ["governance/architecture/registry.json", "governance/work-orders/"],
    "control.schemas.references": ["governance/schemas"],
    "control.schemas.selection": ["governance/schemas"],
    "control.schemas.validation": ["governance/schemas", "governance architecture and registry documents"],
    "control.work-orders.integrity": ["governance/work-orders/"],
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


def _schema_path(record_type, version):
    names = {
        "architecture": "architecture.schema.json",
        "work-order": "work-order.schema.json",
    }
    supported = {
        "architecture": {1, 2, 3},
        "work-order": {1, 2},
    }
    if record_type not in supported or version not in supported[record_type]:
        raise SourceError("unknown-schema-version")
    return f"governance/schemas/v{version}/{names[record_type]}"


def _validate_record(root, record_type, document):
    version = document.get("schema_version")
    schema_relative = _schema_path(record_type, version)
    schema = load_json(root, schema_relative, dict)
    return validate_with_schema(document, schema)


def _classify_result(controls):
    if any(
        item["status"] == "failed" and item["severity"] in {"critical", "error"}
        for item in controls
    ):
        return "failed"
    if any(item["status"] == "indeterminate" for item in controls):
        return "indeterminate"
    if any(item["status"] == "excepted" for item in controls):
        return "verified_with_declared_exceptions"
    return "verified"


def _manual_assertions(root):
    source = "governance/MAINTAINERS.md"
    try:
        text = safe_path(root, source).read_text(encoding="utf-8")
        prefix = "**Última confirmación:** "
        date_lines = [line for line in text.splitlines() if line.startswith(prefix)]
        if len(date_lines) != 1:
            raise SourceError("invalid-maintainer-confirmation-date")
        confirmed_at = datetime.fromisoformat(date_lines[0].removeprefix(prefix))
        if confirmed_at.tzinfo is None or confirmed_at.utcoffset() is None:
            raise SourceError("invalid-maintainer-confirmation-date")
        if any(marker not in text for _id, _title, _source, marker in MANUAL_ASSERTIONS):
            raise SourceError("incomplete-maintainer-declarations")
        status = "declared"
        issue = None
    except (OSError, UnicodeDecodeError, ValueError, SourceError) as error:
        status = "unavailable"
        issue = str(error) if isinstance(error, SourceError) else "maintainer-source-unavailable"
    assertions = [
        {
            "id": assertion_id,
            "title": title,
            "source_id": assertion_source,
            "declaration_status": status,
            "verification_scope": "presence_only",
        }
        for assertion_id, title, assertion_source, _marker in MANUAL_ASSERTIONS
    ]
    return assertions, issue


def _unverified_obligations():
    return [
        {"id": item_id, "title": title, "source_id": source, "reason": reason}
        for item_id, title, source, reason in UNVERIFIED_OBLIGATIONS
    ]


def _perform_audit(root, instant):
    findings = []
    architecture = None
    schema_validation_available = True
    constitution_version = None

    manual_assertions, assertion_issue = _manual_assertions(root)
    if assertion_issue:
        _add(
            findings,
            "control.governance.manual-assertion-sources",
            "indeterminate",
            assertion_issue,
            "governance/MAINTAINERS.md",
            "governance.maintainers",
        )

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

    try:
        for relative in ACTIVE_SCHEMA_PATHS:
            path = safe_path(root, relative)
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
        discovered_work_orders = discover_work_orders(root)
        work_order_index = [
            {field: item[field] for field in ("id", "title", "status", "path")}
            for item in discovered_work_orders
        ]
        known_work_orders = {item["id"] for item in discovered_work_orders}
    except WorkOrderSourceError as error:
        discovered_work_orders = []
        work_order_index = []
        known_work_orders = set()
        _add(findings, "control.work-orders.integrity", "failed", error.code, "governance/work-orders/", "governance.work-orders")

    if architecture is not None:
        for item in discovered_work_orders:
            if item["model"] != "lightweight":
                continue
            dependencies = item["document"].get("dependencies", [])
            for dependency in sorted(set(dependencies) - known_work_orders):
                _add(findings, "control.references.integrity", "failed", "unknown-work-order-dependency", "governance/work-orders/", dependency)

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
        if (
            description["identity"]["value"]["id"] != architecture.get("id")
            or
            description["architecture_version"]["value"] != architecture.get("architecture_version")
            or description["constitution_version"]["value"] != constitution_version
            or description["contracts"]["items"] != sorted(architecture.get("contract_ids", []))
            or description["architectural_dependencies"]["items"] != expected_dependencies
            or description["work_orders"]["items"] != work_order_index
            or description["active_exceptions"]["items"] != []
        ):
            _add(findings, "control.introspection.coherence", "failed", "introspection-source-mismatch", "capability_introspection.describe_camilobuilder", "architecture.camilobuilder")
    except (IntrospectionError, KeyError, TypeError, UnboundLocalError):
        _add(findings, "control.introspection.coherence", "indeterminate", "introspection-unavailable", "capability_introspection.describe_camilobuilder", "architecture.camilobuilder")

    findings.sort(key=lambda item: (
        item["control_id"], item["code"], item["source_id"], tuple(item["subject_ids"])
    ))
    for index, finding in enumerate(findings, 1):
        finding["id"] = f"finding.{index:03d}"

    declared_exceptions = []

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
    automated_summary = {
        "passed": sum(item["status"] == "passed" for item in controls),
        "failed": sum(item["status"] == "failed" for item in controls),
        "excepted": sum(item["status"] == "excepted" for item in controls),
        "indeterminate": sum(item["status"] == "indeterminate" for item in controls),
    }
    return {
        "schema_version": 2,
        "report_version": "2.0.0",
        "evaluation_instant": instant.isoformat(),
        "automated_result": result,
        "constitution_version": constitution_version or "unknown",
        "architecture_version": architecture.get("architecture_version", "unknown") if architecture else "unknown",
        "automated_summary": automated_summary,
        "automated_controls": controls,
        "manual_assertions": manual_assertions,
        "unverified_obligations": _unverified_obligations(),
        "declared_exceptions": declared_exceptions,
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
            "schema_version": 2, "report_version": "2.0.0",
            "evaluation_instant": evaluation_instant.isoformat(), "automated_result": "indeterminate",
            "constitution_version": "unknown", "architecture_version": "unknown",
            "automated_summary": {"passed": 0, "failed": 0, "excepted": 0, "indeterminate": len(controls)},
            "automated_controls": controls,
            "manual_assertions": [
                {
                    "id": assertion_id, "title": title, "source_id": source,
                    "declaration_status": "unavailable",
                    "verification_scope": "presence_only",
                }
                for assertion_id, title, source, _marker in MANUAL_ASSERTIONS
            ],
            "unverified_obligations": _unverified_obligations(),
            "declared_exceptions": [], "findings": findings,
        }
