import ast
import json
from datetime import datetime
from pathlib import Path, PurePosixPath


class ValidationUnavailable(RuntimeError):
    pass


class SourceError(RuntimeError):
    pass


WORK_ORDER_TRANSITIONS = {
    ("proposed", "approved"), ("proposed", "cancelled"),
    ("approved", "in_progress"), ("approved", "cancelled"),
    ("in_progress", "completed"), ("in_progress", "cancelled"),
    ("completed", "published"), ("completed", "reverted"),
    ("published", "reverted"),
}
EXCEPTION_TRANSITIONS = {
    ("proposed", "active"), ("proposed", "expired"), ("proposed", "revoked"),
    ("active", "expired"), ("active", "closed"), ("active", "revoked"),
    ("expired", "closed"),
}
DERIVED_FIELDS = {"builders", "capabilities", "commands", "component_types", "templates"}
AST_ANALYSIS_SCOPE = (
    "Limited, non-exhaustive analysis of static Python imports; dynamic, reflective, "
    "conditional, transitive, and runtime-loaded dependencies are excluded."
)


def safe_path(root: Path, relative_path: str, *, file: bool = True) -> Path:
    try:
        pure = PurePosixPath(relative_path)
    except TypeError as error:
        raise SourceError("invalid-relative-path") from error
    if pure.is_absolute() or relative_path != pure.as_posix() or any(
        part in ("", ".", "..") for part in pure.parts
    ):
        raise SourceError("unsafe-relative-path")
    path = root.joinpath(*pure.parts)
    current = path
    while current != root:
        if current.is_symlink():
            raise SourceError("symlink-source")
        current = current.parent
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError as error:
        raise SourceError("escaped-source") from error
    if (file and not path.is_file()) or (not file and not path.is_dir()):
        raise SourceError("missing-source")
    return path


def load_json(root: Path, relative_path: str, expected_type: type) -> object:
    path = safe_path(root, relative_path)
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise SourceError("invalid-json") from error
    if type(value) is not expected_type:
        raise SourceError("unexpected-json-type")
    return value


def validate_with_schema(instance: object, schema: dict[str, object]) -> list[str]:
    try:
        from jsonschema import Draft202012Validator, FormatChecker
        from referencing import Registry
    except ModuleNotFoundError as error:
        raise ValidationUnavailable("jsonschema-unavailable") from error

    def reject_remote(uri):
        raise SourceError("remote-schema-reference")

    validator = Draft202012Validator(
        schema,
        format_checker=FormatChecker(),
        registry=Registry(retrieve=reject_remote),
    )
    errors = sorted(
        validator.iter_errors(instance),
        key=lambda item: (
            tuple(str(part) for part in item.absolute_path),
            str(item.validator),
            item.message,
        ),
    )
    return [f"{'.'.join(str(part) for part in error.absolute_path)}:{error.validator}" for error in errors]


def local_schema_reference_issues(schema: dict[str, object]) -> list[str]:
    issues = []

    def walk(value):
        if isinstance(value, dict):
            reference = value.get("$ref")
            if reference is not None and (
                not isinstance(reference, str) or not reference.startswith("#/$defs/")
            ):
                issues.append("non-local-reference")
            for child in value.values():
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)

    walk(schema)
    return sorted(issues)


def ordered_unique(values: object) -> bool:
    return isinstance(values, list) and values == sorted(set(values))


def history_issues(document: dict[str, object], transitions: set[tuple[str, str]]) -> list[str]:
    history = document.get("status_history")
    if not isinstance(history, list):
        return ["invalid-status-history"]
    issues = []
    previous = None
    dates = []
    for transition in history:
        if not isinstance(transition, dict):
            issues.append("invalid-transition")
            continue
        pair = (transition.get("from"), transition.get("to"))
        if pair not in transitions:
            issues.append("invalid-transition")
        if previous is not None and transition.get("from") != previous:
            issues.append("discontinuous-history")
        previous = transition.get("to")
        try:
            dates.append(datetime.fromisoformat(transition["at"]))
        except (KeyError, TypeError, ValueError):
            issues.append("invalid-transition-date")
    if history and previous != document.get("status"):
        issues.append("status-history-mismatch")
    if dates != sorted(dates):
        issues.append("non-chronological-history")
    return sorted(set(issues))


def architecture_issues(root: Path, document: dict[str, object]) -> dict[str, list[tuple[str, str]]]:
    result = {"modules": [], "dependencies": [], "contracts": [], "inventories": []}
    contracts = document.get("contract_ids")
    modules = document.get("modules")
    if not ordered_unique(contracts) or not isinstance(modules, list):
        result["contracts"].append(("invalid-contract-catalog", "architecture.camilobuilder"))
        return result
    module_ids = [item.get("id") for item in modules if isinstance(item, dict)]
    if len(module_ids) != len(modules) or module_ids != sorted(set(module_ids)):
        result["modules"].append(("invalid-module-catalog", "architecture.camilobuilder"))
        return result
    known_modules = set(module_ids)
    known_contracts = set(contracts)
    seen_paths = set()
    for module in modules:
        module_id = module["id"]
        for relative in module.get("paths", []):
            if relative in seen_paths:
                result["modules"].append(("duplicate-module-path", module_id))
            seen_paths.add(relative)
            try:
                safe_path(root, relative, file=Path(relative).suffix == ".py")
            except SourceError:
                result["modules"].append(("invalid-module-path", module_id))
        provided = module.get("provides_contract_ids", [])
        consumed = module.get("consumes_contract_ids", [])
        if not ordered_unique(provided) or not ordered_unique(consumed):
            result["contracts"].append(("unordered-contract-reference", module_id))
        for contract in sorted((set(provided) | set(consumed)) - known_contracts):
            result["contracts"].append(("unknown-contract", contract))
        allowed = module.get("allowed_dependency_ids", [])
        prohibited = module.get("prohibited_dependency_ids", [])
        if not ordered_unique(allowed) or not ordered_unique(prohibited):
            result["dependencies"].append(("unordered-dependency", module_id))
        if module_id in set(allowed) | set(prohibited):
            result["dependencies"].append(("self-dependency", module_id))
        for dependency in sorted((set(allowed) | set(prohibited)) - known_modules):
            result["dependencies"].append(("unknown-dependency", dependency))
        for dependency in sorted(set(allowed) & set(prohibited)):
            result["dependencies"].append(("dependency-conflict", dependency))
    keys = set()

    def collect(value):
        if isinstance(value, dict):
            keys.update(value)
            for child in value.values():
                collect(child)
        elif isinstance(value, list):
            for child in value:
                collect(child)

    collect(document)
    for field in sorted(keys & DERIVED_FIELDS):
        result["inventories"].append(("derived-inventory", field))
    return result


def static_dependency_issues(root: Path, architecture: dict[str, object]) -> list[tuple[str, str]]:
    import_map = {
        "builder": "module.public-facade",
        "builder_cli": "module.cli",
        "builders": "module.builders",
        "capability_introspection": "module.capability-introspection",
        "constitutional_audit": "module.constitutional-audit",
        "template_system": "module.template-system",
    }
    issues = []
    for module in architecture["modules"]:
        observed = set()
        for relative in module["paths"]:
            path = safe_path(root, relative, file=Path(relative).suffix == ".py")
            python_files = [path] if path.is_file() else sorted(path.rglob("*.py"))
            for python_file in python_files:
                tree = ast.parse(python_file.read_text(encoding="utf-8"))
                for node in ast.walk(tree):
                    names = []
                    if isinstance(node, ast.Import):
                        names = [item.name.split(".")[0] for item in node.names]
                    elif isinstance(node, ast.ImportFrom) and node.module:
                        names = [node.module.split(".")[0]]
                    observed.update(import_map[name] for name in names if name in import_map)
        observed.discard(module["id"])
        prohibited = set(module["prohibited_dependency_ids"])
        allowed = set(module["allowed_dependency_ids"])
        for dependency in sorted(observed & prohibited):
            issues.append(("prohibited-static-dependency", f"{module['id']}:{dependency}"))
        for dependency in sorted(observed - allowed - prohibited):
            issues.append(("undeclared-static-dependency", f"{module['id']}:{dependency}"))
    return sorted(issues)
