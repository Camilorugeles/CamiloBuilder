import json
import re
from pathlib import Path, PurePosixPath

from builder_cli import BUILDER_METADATA, COMMANDS
from template_system.errors import TemplateError
from template_system.registry import TemplateRegistry


DEFAULT_ROOT = Path(__file__).resolve().parents[1]
CONSTITUTION_VERSION_PATTERN = re.compile(
    r"^\*\*Versión constitucional:\*\* ([^ ]+)  $", re.MULTILINE
)


class IntrospectionError(RuntimeError):
    """Raised when canonical introspection sources cannot be trusted."""


def _safe_source(root: Path, relative_path: str, *, kind: str) -> Path:
    pure = PurePosixPath(relative_path)
    if (
        pure.is_absolute()
        or relative_path != pure.as_posix()
        or any(part in ("", ".", "..") for part in pure.parts)
    ):
        raise IntrospectionError(f"Unsafe canonical source path: {relative_path}")
    path = root.joinpath(*pure.parts)
    current = path
    while current != root:
        if current.is_symlink():
            raise IntrospectionError(f"Symlink canonical source: {relative_path}")
        current = current.parent
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError as error:
        raise IntrospectionError(f"Escaped canonical source: {relative_path}") from error
    valid = path.is_file() if kind == "file" else path.is_dir()
    if not valid:
        raise IntrospectionError(f"Missing canonical source: {relative_path}")
    return path


def _load_json(root: Path, relative_path: str, *, expected_type: type) -> object:
    path = _safe_source(root, relative_path, kind="file")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise IntrospectionError(f"Invalid JSON source: {relative_path}") from error
    if type(value) is not expected_type:
        raise IntrospectionError(f"Unexpected JSON type: {relative_path}")
    return value


def _unique(items: list[object], key, source: str) -> None:
    values = [key(item) for item in items]
    if len(values) != len(set(values)):
        raise IntrospectionError(f"Duplicate entries in canonical source: {source}")


def _block(classification: str, source: str, field: str, content: object) -> dict[str, object]:
    return {"classification": classification, "source": source, field: content}


def _architecture(root: Path) -> dict[str, object]:
    source = "governance/architecture/registry.json"
    document = _load_json(root, source, expected_type=dict)
    if document.get("schema_version") != 2:
        raise IntrospectionError("Unsupported architecture schema_version")
    required = {
        "id", "record_version", "architecture_version", "constitution_version",
        "contract_ids", "modules",
    }
    if not required.issubset(document):
        raise IntrospectionError("Incomplete architecture registry")
    if not isinstance(document["contract_ids"], list) or not isinstance(document["modules"], list):
        raise IntrospectionError("Unexpected architecture registry structure")
    required_module_fields = {
        "id", "allowed_dependency_ids", "prohibited_dependency_ids",
    }
    if any(
        not isinstance(module, dict)
        or not required_module_fields.issubset(module)
        or not isinstance(module["id"], str)
        or not isinstance(module["allowed_dependency_ids"], list)
        or not isinstance(module["prohibited_dependency_ids"], list)
        for module in document["modules"]
    ):
        raise IntrospectionError("Unexpected architecture module structure")
    _unique(document["contract_ids"], lambda item: item, source)
    _unique(document["modules"], lambda item: item.get("id") if isinstance(item, dict) else None, source)
    return document


def _constitution_version(root: Path, declared: object) -> str:
    source = "governance/CONSTITUTION.md"
    path = _safe_source(root, source, kind="file")
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as error:
        raise IntrospectionError(f"Invalid constitutional source: {source}") from error
    match = CONSTITUTION_VERSION_PATTERN.search(text)
    if not match or match.group(1) != declared:
        raise IntrospectionError(
            "Constitution version contradicts the architecture registry"
        )
    return match.group(1)


def _executable_metadata() -> tuple[list[dict[str, object]], list[dict[str, object]], list[str]]:
    commands = []
    for command in COMMANDS:
        if not isinstance(command.get("name"), str) or "description" not in command:
            raise IntrospectionError("Incomplete executable command metadata")
        commands.append({"name": command["name"], "description": command["description"]})
    _unique(commands, lambda item: item["name"], "builder_cli.COMMANDS")

    builders = []
    for metadata in BUILDER_METADATA:
        builder = metadata.get("builder")
        component_type = metadata.get("component_type")
        if not isinstance(builder, type) or not isinstance(component_type, str) or not component_type:
            raise IntrospectionError("Incomplete executable builder metadata")
        builders.append(
            {
                "module": builder.__module__,
                "name": builder.__name__,
                "component_type": component_type,
            }
        )
    _unique(builders, lambda item: (item["module"], item["name"]), "builder_cli.BUILDER_METADATA")
    component_types = [item["component_type"] for item in builders]
    if len(component_types) != len(set(component_types)):
        raise IntrospectionError("Duplicate component type metadata")
    return (
        sorted(commands, key=lambda item: item["name"]),
        sorted(builders, key=lambda item: (item["module"], item["name"])),
        sorted(component_types),
    )


def _templates(root: Path) -> list[dict[str, object]]:
    templates_path = _safe_source(root, "templates", kind="directory")
    if any(path.is_symlink() for path in templates_path.rglob("*")):
        raise IntrospectionError("Symlink registered template source")
    try:
        registered = TemplateRegistry(templates_path).list()
    except (OSError, TemplateError) as error:
        raise IntrospectionError("Invalid registered template") from error
    items = [
        {
            "component_type": manifest.component_type,
            "name": manifest.name,
            "schema_version": manifest.schema_version,
            "description": manifest.description,
            "required_variables": sorted(manifest.required_variables),
        }
        for _path, manifest in registered
    ]
    _unique(items, lambda item: (item["component_type"], item["name"]), "TemplateRegistry")
    return sorted(items, key=lambda item: (item["component_type"], item["name"]))


def _index(root: Path, relative_path: str, fields: set[str]) -> list[dict[str, object]]:
    entries = _load_json(root, relative_path, expected_type=list)
    for entry in entries:
        if not isinstance(entry, dict) or set(entry) != fields or not isinstance(entry.get("id"), str):
            raise IntrospectionError(f"Incoherent governed index: {relative_path}")
        if "path" in entry:
            document = _load_json(root, entry["path"], expected_type=dict)
            if document.get("schema_version") != 2:
                raise IntrospectionError(f"Unsupported governed record schema_version: {entry['path']}")
            for field in fields - {"path"}:
                if document.get(field) != entry[field]:
                    raise IntrospectionError(f"Incoherent governed index: {relative_path}")
    _unique(entries, lambda item: item["id"], relative_path)
    return sorted(entries, key=lambda item: item["id"])


def _limitations(root: Path, architecture: dict[str, object]) -> list[dict[str, str]]:
    observations = []
    checks = (
        ("observed.capability-registry-absent", "path_exists", "governance/capabilities/index.json"),
        ("observed.contract-registry-absent", "path_exists", "governance/contracts/index.json"),
    )
    for identifier, operation, target in checks:
        if not root.joinpath(*PurePosixPath(target).parts).exists():
            observations.append(
                {"id": identifier, "operation": operation, "target": target, "result": "absent"}
            )
    module_ids = {module["id"] for module in architecture["modules"]}
    if "module.constitutional-audit" not in module_ids:
        observations.append(
            {
                "id": "observed.constitutional-audit-module-absent",
                "operation": "module_id_exists",
                "target": "module.constitutional-audit",
                "result": "absent",
            }
        )
    return sorted(observations, key=lambda item: item["id"])


def _describe_camilobuilder(
    *,
    repository_root: Path | None = None,
) -> dict[str, object]:
    root = Path(repository_root) if repository_root is not None else DEFAULT_ROOT
    if root.is_symlink() or not root.is_dir():
        raise IntrospectionError("Invalid repository root")
    architecture = _architecture(root)
    constitution_version = _constitution_version(root, architecture["constitution_version"])
    commands, builders, component_types = _executable_metadata()
    templates = _templates(root)
    work_orders = _index(
        root,
        "governance/work-orders/index.json",
        {"id", "title", "status", "path"},
    )
    exceptions = _index(root, "governance/exceptions/index.json", {"id", "status", "path"})
    active_exceptions = [entry for entry in exceptions if entry["status"] == "active"]
    modules = sorted(architecture["modules"], key=lambda item: item["id"])
    dependencies = [
        {
            "module_id": module["id"],
            "allowed_dependency_ids": sorted(module["allowed_dependency_ids"]),
            "prohibited_dependency_ids": sorted(module["prohibited_dependency_ids"]),
        }
        for module in modules
    ]
    architecture_source = "governance/architecture/registry.json"
    return {
        "schema_version": 2,
        "report_version": "1.0.0",
        "identity": _block(
            "normative_declared", architecture_source, "value", {"id": architecture["id"]}
        ),
        "constitution_version": _block(
            "normative_declared",
            f"{architecture_source} + governance/CONSTITUTION.md",
            "value",
            constitution_version,
        ),
        "architecture_version": _block(
            "normative_declared", architecture_source, "value", architecture["architecture_version"]
        ),
        "commands": _block("executable_derived", "builder_cli.COMMANDS", "items", commands),
        "builders": _block("executable_derived", "builder_cli.BUILDER_METADATA", "items", builders),
        "component_types": _block(
            "executable_derived", "builder_cli.BUILDER_METADATA", "items", component_types
        ),
        "templates": _block(
            "executable_derived", "TemplateRegistry + TemplateManifest", "items", templates
        ),
        "contracts": _block(
            "normative_declared", architecture_source, "items", sorted(architecture["contract_ids"])
        ),
        "architectural_dependencies": _block(
            "normative_declared", architecture_source, "items", dependencies
        ),
        "work_orders": _block(
            "normative_declared", "governance/work-orders/index.json", "items", work_orders
        ),
        "active_exceptions": _block(
            "normative_declared", "governance/exceptions/index.json", "items", active_exceptions
        ),
        "limitations": _block(
            "observed_state",
            "repository checks + governance/architecture/registry.json",
            "items",
            _limitations(root, architecture),
        ),
    }


def describe_camilobuilder(
    *,
    repository_root: Path | None = None,
) -> dict[str, object]:
    try:
        return _describe_camilobuilder(repository_root=repository_root)
    except IntrospectionError:
        raise
    except (KeyError, OSError, TypeError, ValueError) as error:
        raise IntrospectionError("Canonical introspection source is inconsistent") from error
