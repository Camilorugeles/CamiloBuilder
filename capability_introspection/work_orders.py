import json
import re
from pathlib import Path


WORK_ORDER_NAME = re.compile(r"^WORK-[0-9]{3,}\.json$")
WORK_ORDER_ID = re.compile(r"^WORK-[0-9]{3,}$")
EVIDENCE_REF = re.compile(
    r"^(?:commit:[0-9a-f]{40}|github-actions-run:[0-9]+|adr:ADR-[0-9]{4}|pr:[0-9]+)$"
)
DECISION_REF = re.compile(r"^adr:ADR-[0-9]{4}$")
LIGHTWEIGHT_REQUIRED = {
    "format", "format_version", "id", "title", "objective", "status",
    "historical_record", "scope", "contract_impact", "risks", "reversal",
    "evidence_refs",
}
LIGHTWEIGHT_OPTIONAL = {"dependencies", "decision_refs", "notes"}
LIGHTWEIGHT_STATUSES = {"proposed", "active", "done", "cancelled"}
LEGACY_STATUSES = {
    1: {"proposed", "approved", "in_progress", "implemented", "published", "reverted", "cancelled"},
    2: {"proposed", "approved", "in_progress", "completed", "published", "reverted", "cancelled"},
}
IMPACT_LEVELS = {"compatible": 1, "deprecation": 2, "incompatible": 3}


class WorkOrderSourceError(RuntimeError):
    """Raised when Work Order discovery cannot produce a trusted catalog."""

    def __init__(self, message, *, code="work-order-source-invalid"):
        super().__init__(message)
        self.code = code


def _ordered_unique_strings(value, *, allow_empty=True):
    return (
        isinstance(value, list)
        and (allow_empty or bool(value))
        and all(isinstance(item, str) and item for item in value)
        and value == sorted(set(value))
    )


def _validate_adr(root: Path, reference: str) -> None:
    identifier = reference.removeprefix("adr:")
    decisions = root / "governance" / "decisions"
    matches = sorted(decisions.glob(f"{identifier}-*.md")) if decisions.is_dir() else []
    if len(matches) != 1 or matches[0].is_symlink() or not matches[0].is_file():
        raise WorkOrderSourceError("Unknown or unsafe ADR reference")


def _validate_lightweight(root: Path, document: dict[str, object]) -> None:
    keys = set(document)
    if not LIGHTWEIGHT_REQUIRED.issubset(keys) or keys - LIGHTWEIGHT_REQUIRED - LIGHTWEIGHT_OPTIONAL:
        raise WorkOrderSourceError("Invalid lightweight Work Order fields")
    if document.get("format") != "camilobuilder.work-order" or document.get("format_version") != 1:
        raise WorkOrderSourceError("Unsupported lightweight Work Order format")
    if not isinstance(document.get("title"), str) or not document["title"]:
        raise WorkOrderSourceError("Invalid lightweight Work Order title")
    if not isinstance(document.get("objective"), str) or not document["objective"]:
        raise WorkOrderSourceError("Invalid lightweight Work Order objective")
    if document.get("status") not in LIGHTWEIGHT_STATUSES:
        raise WorkOrderSourceError("Invalid lightweight Work Order status")
    if not isinstance(document.get("historical_record"), bool):
        raise WorkOrderSourceError("Invalid lightweight historical_record")
    if not isinstance(document.get("reversal"), str) or not document["reversal"]:
        raise WorkOrderSourceError("Invalid lightweight Work Order reversal")
    for field in ("scope", "risks", "evidence_refs"):
        if not _ordered_unique_strings(document.get(field)):
            raise WorkOrderSourceError(f"Invalid lightweight Work Order {field}")
    for field in LIGHTWEIGHT_OPTIONAL:
        if field in document and not _ordered_unique_strings(document[field]):
            raise WorkOrderSourceError(f"Invalid lightweight Work Order {field}")
    if any(not WORK_ORDER_ID.fullmatch(item) for item in document.get("dependencies", [])):
        raise WorkOrderSourceError("Invalid lightweight Work Order dependency")
    evidence = document["evidence_refs"]
    if any(not EVIDENCE_REF.fullmatch(item) for item in evidence):
        raise WorkOrderSourceError("Invalid lightweight Work Order evidence")
    decisions = document.get("decision_refs", [])
    if any(not DECISION_REF.fullmatch(item) for item in decisions):
        raise WorkOrderSourceError("Invalid lightweight decision reference")
    for reference in [*evidence, *decisions]:
        if reference.startswith("adr:"):
            _validate_adr(root, reference)

    impact = document.get("contract_impact")
    if not isinstance(impact, dict) or set(impact) != {"classification", "surfaces"}:
        raise WorkOrderSourceError("Invalid lightweight contract impact")
    classification = impact.get("classification")
    surfaces = impact.get("surfaces")
    if classification not in {"none", *IMPACT_LEVELS} or not isinstance(surfaces, list):
        raise WorkOrderSourceError("Invalid lightweight contract impact")
    if classification == "none":
        if surfaces:
            raise WorkOrderSourceError("Contract impact none requires no surfaces")
        return
    if not surfaces:
        raise WorkOrderSourceError("Contract impact requires surfaces")
    names = []
    impacts = []
    for surface in surfaces:
        if not isinstance(surface, dict) or set(surface) != {"surface", "impact"}:
            raise WorkOrderSourceError("Invalid contract impact surface")
        name = surface.get("surface")
        surface_impact = surface.get("impact")
        if not isinstance(name, str) or not name or surface_impact not in IMPACT_LEVELS:
            raise WorkOrderSourceError("Invalid contract impact surface")
        names.append(name)
        impacts.append(surface_impact)
    if names != sorted(set(names)):
        raise WorkOrderSourceError("Unordered or duplicate contract impact surface")
    aggregate = max(impacts, key=lambda item: IMPACT_LEVELS[item])
    if classification != aggregate:
        raise WorkOrderSourceError("Incoherent aggregate contract impact")


def discover_work_orders(repository_root: Path) -> list[dict[str, object]]:
    root = Path(repository_root)
    directory = root / "governance" / "work-orders"
    if root.is_symlink() or directory.is_symlink() or not directory.is_dir():
        raise WorkOrderSourceError("Invalid Work Order source directory")
    try:
        directory.resolve().relative_to(root.resolve())
    except ValueError as error:
        raise WorkOrderSourceError("Escaped Work Order source directory") from error
    records = []
    for path in sorted(directory.iterdir(), key=lambda item: item.name):
        if not WORK_ORDER_NAME.fullmatch(path.name):
            continue
        if path.is_symlink() or not path.is_file():
            raise WorkOrderSourceError("Unsafe Work Order source")
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise WorkOrderSourceError("Invalid Work Order JSON") from error
        if not isinstance(document, dict):
            raise WorkOrderSourceError("Invalid Work Order root type")
        has_schema = "schema_version" in document
        has_format = "format" in document or "format_version" in document
        if has_schema == has_format:
            raise WorkOrderSourceError("Ambiguous Work Order format discriminator")
        if has_schema:
            if document.get("schema_version") not in {1, 2}:
                raise WorkOrderSourceError(
                    "Unsupported legacy Work Order schema",
                    code="unknown-schema-version",
                )
            version = document["schema_version"]
            schema_path = root / "governance" / "schemas" / f"v{version}" / "work-order.schema.json"
            if schema_path.is_symlink() or not schema_path.is_file():
                raise WorkOrderSourceError("Unavailable legacy Work Order schema")
            try:
                schema_path.resolve().relative_to(root.resolve())
            except ValueError as error:
                raise WorkOrderSourceError("Escaped legacy Work Order schema") from error
            if document.get("status") not in LEGACY_STATUSES[version]:
                raise WorkOrderSourceError("Invalid legacy Work Order status")
            model = "legacy"
        else:
            _validate_lightweight(root, document)
            model = "lightweight"
        identifier = document.get("id")
        if not isinstance(identifier, str) or not WORK_ORDER_ID.fullmatch(identifier):
            raise WorkOrderSourceError("Invalid Work Order id")
        if path.stem != identifier:
            raise WorkOrderSourceError("Work Order filename and id mismatch")
        if (
            not isinstance(document.get("title"), str)
            or not document["title"]
            or not isinstance(document.get("status"), str)
        ):
            raise WorkOrderSourceError("Incomplete Work Order summary")
        records.append({
            "id": identifier,
            "title": document["title"],
            "status": document["status"],
            "path": path.relative_to(root).as_posix(),
            "model": model,
            "document": document,
        })
    ids = [item["id"] for item in records]
    if ids != sorted(set(ids)):
        raise WorkOrderSourceError("Duplicate or unordered Work Order ids")
    return records
