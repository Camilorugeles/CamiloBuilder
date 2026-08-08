import ast
import copy
import hashlib
import json
import unittest
from pathlib import Path, PurePosixPath

try:
    from jsonschema import Draft202012Validator, FormatChecker
    from referencing import Registry
except ModuleNotFoundError as error:
    raise RuntimeError(
        "Missing development dependency; run: "
        "python3 -m pip install -r requirements-dev.txt"
    ) from error


ROOT = Path(__file__).resolve().parents[1]
V1_SCHEMA_PATH = ROOT / "governance" / "schemas" / "v1" / "architecture.schema.json"
V2_SCHEMA_PATH = ROOT / "governance" / "schemas" / "v2" / "architecture.schema.json"
V3_SCHEMA_PATH = ROOT / "governance" / "schemas" / "v3" / "architecture.schema.json"
REGISTRY_PATH = ROOT / "governance" / "architecture" / "registry.json"
V1_FIXTURE_PATH = ROOT / "tests" / "fixtures" / "governance" / "v1" / "valid" / "architecture.json"
V2_FIXTURE_ROOT = ROOT / "tests" / "fixtures" / "governance" / "v2"
V3_FIXTURE_ROOT = ROOT / "tests" / "fixtures" / "governance" / "v3"
V1_SCHEMA_SHA256 = "a89ef3fe0d00687d4ee8ea72e154a2ddab5a8b5e1fd783c600ca22c101253d89"
V2_SCHEMA_SHA256 = "acf901da3100f284936da9fe6deae148d1a641141cc93a91b9599e4de8ade3a9"
DERIVED_INVENTORY_FIELDS = {
    "builders",
    "capabilities",
    "commands",
    "component_types",
    "templates",
}
AST_ANALYSIS_SCOPE = (
    "Limited, non-exhaustive analysis of static Python imports; it excludes "
    "dynamic, reflective, conditional, and transitive dependencies."
)


def load_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def reject_remote_retrieval(uri):
    raise AssertionError(f"Schema validation attempted network retrieval: {uri}")


def make_validator(schema):
    return Draft202012Validator(
        schema,
        format_checker=FormatChecker(),
        registry=Registry(retrieve=reject_remote_retrieval),
    )


def stable_schema_errors(validator, instance):
    return sorted(
        validator.iter_errors(instance),
        key=lambda error: (
            tuple(str(part) for part in error.absolute_path),
            error.validator,
            error.message,
        ),
    )


def select_architecture_schema(instance):
    version = instance.get("schema_version")
    paths = {1: V1_SCHEMA_PATH, 2: V2_SCHEMA_PATH, 3: V3_SCHEMA_PATH}
    if version not in paths:
        raise ValueError(f"Unsupported architecture schema_version: {version!r}")
    return load_json(paths[version])


def tree_digest(paths):
    digest = hashlib.sha256()
    files = []
    for path in paths:
        files.extend(item for item in path.rglob("*") if item.is_file())
    for path in sorted(files):
        digest.update(path.relative_to(ROOT).as_posix().encode("utf-8"))
        digest.update(path.read_bytes())
    return digest.hexdigest()


def is_sorted_unique(values):
    return values == sorted(set(values))


def path_is_safe(relative_path):
    pure_path = PurePosixPath(relative_path)
    return (
        not pure_path.is_absolute()
        and relative_path == pure_path.as_posix()
        and all(part not in ("", ".", "..") for part in pure_path.parts)
    )


def cross_validation_issues(document, check_filesystem=False):
    issues = []
    contracts = set(document["contract_ids"])
    modules = document["modules"]
    module_ids = [module["id"] for module in modules]
    known_modules = set(module_ids)

    if not is_sorted_unique(document["contract_ids"]):
        issues.append(("unsorted-contract-ids", "contract_ids"))
    if not is_sorted_unique(module_ids):
        issue = "duplicate-module-id" if len(module_ids) != len(set(module_ids)) else "unsorted-modules"
        issues.append((issue, "modules"))

    seen_paths = set()
    for module in modules:
        module_id = module["id"]
        list_fields = (
            "paths",
            "responsibilities",
            "provides_contract_ids",
            "consumes_contract_ids",
            "allowed_dependency_ids",
            "prohibited_dependency_ids",
        )
        for field in list_fields:
            if not is_sorted_unique(module[field]):
                issues.append(("unsorted-array", f"{module_id}.{field}"))

        for relative_path in module["paths"]:
            if relative_path in seen_paths:
                issues.append(("duplicate-path", relative_path))
            seen_paths.add(relative_path)
            if not path_is_safe(relative_path):
                issues.append(("unsafe-path", relative_path))
                continue
            if check_filesystem:
                candidate = ROOT / relative_path
                if not candidate.exists():
                    issues.append(("missing-path", relative_path))
                else:
                    current = candidate
                    while current != ROOT:
                        if current.is_symlink():
                            issues.append(("symlink-path", relative_path))
                            break
                        current = current.parent
                    try:
                        candidate.resolve().relative_to(ROOT.resolve())
                    except ValueError:
                        issues.append(("escaped-path", relative_path))

        referenced_contracts = set(module["provides_contract_ids"])
        referenced_contracts.update(module["consumes_contract_ids"])
        for contract_id in sorted(referenced_contracts - contracts):
            issues.append(("unknown-contract", f"{module_id}:{contract_id}"))

        allowed = set(module["allowed_dependency_ids"])
        prohibited = set(module["prohibited_dependency_ids"])
        for dependency_id in sorted((allowed | prohibited) - known_modules):
            issues.append(("unknown-dependency", f"{module_id}:{dependency_id}"))
        if module_id in allowed or module_id in prohibited:
            issues.append(("self-dependency", module_id))
        for dependency_id in sorted(allowed & prohibited):
            issues.append(("dependency-conflict", f"{module_id}:{dependency_id}"))

    return sorted(issues)


def internal_static_dependencies(document):
    """Return only directly observable imports; this is deliberately not exhaustive."""
    module_by_import = {
        "builder": "module.public-facade",
        "builder_cli": "module.cli",
        "builders": "module.builders",
        "capability_introspection": "module.capability-introspection",
        "constitutional_audit": "module.constitutional-audit",
        "template_system": "module.template-system",
    }
    observed = {module["id"]: set() for module in document["modules"]}
    for module in document["modules"]:
        for relative_path in module["paths"]:
            path = ROOT / relative_path
            python_files = [path] if path.is_file() and path.suffix == ".py" else sorted(path.rglob("*.py"))
            for python_file in python_files:
                tree = ast.parse(python_file.read_text(encoding="utf-8"))
                for node in ast.walk(tree):
                    imported = []
                    if isinstance(node, ast.Import):
                        imported = [alias.name.split(".")[0] for alias in node.names]
                    elif isinstance(node, ast.ImportFrom) and node.module:
                        imported = [node.module.split(".")[0]]
                    for root_name in imported:
                        target = module_by_import.get(root_name)
                        if target and target != module["id"]:
                            observed[module["id"]].add(target)
    return observed


class ArchitectureRegistryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.v1_schema = load_json(V1_SCHEMA_PATH)
        cls.v2_schema = load_json(V2_SCHEMA_PATH)
        cls.v3_schema = load_json(V3_SCHEMA_PATH)
        cls.registry = load_json(REGISTRY_PATH)
        cls.valid_v2_fixture = load_json(V2_FIXTURE_ROOT / "valid" / "architecture.json")
        cls.valid_fixture = load_json(V3_FIXTURE_ROOT / "valid" / "architecture.json")

    def test_v1_schema_is_byte_for_byte_unchanged_and_still_validates(self):
        digest = hashlib.sha256(V1_SCHEMA_PATH.read_bytes()).hexdigest()
        self.assertEqual(digest, V1_SCHEMA_SHA256)
        fixture = load_json(V1_FIXTURE_PATH)
        self.assertEqual(stable_schema_errors(make_validator(self.v1_schema), fixture), [])

    def test_schema_selection_is_explicit_and_rejects_unknown_versions(self):
        v1_fixture = load_json(V1_FIXTURE_PATH)
        self.assertEqual(select_architecture_schema(v1_fixture)["properties"]["schema_version"], {"const": 1})
        self.assertEqual(select_architecture_schema(self.valid_v2_fixture)["properties"]["schema_version"], {"const": 2})
        self.assertEqual(select_architecture_schema(self.valid_fixture)["properties"]["schema_version"], {"const": 3})
        with self.assertRaisesRegex(ValueError, "Unsupported architecture schema_version"):
            select_architecture_schema({"schema_version": 4})

    def test_v2_schema_is_draft_2020_12_closed_and_network_independent(self):
        self.assertEqual(self.v2_schema["$schema"], "https://json-schema.org/draft/2020-12/schema")
        self.assertEqual(self.v2_schema["properties"]["schema_version"], {"const": 2})
        Draft202012Validator.check_schema(self.v2_schema)
        object_nodes = [
            node
            for node in self._nodes(self.v2_schema)
            if isinstance(node, dict) and node.get("type") == "object"
        ]
        self.assertTrue(all(node.get("additionalProperties") is False for node in object_nodes))
        refs = [node["$ref"] for node in self._nodes(self.v2_schema) if isinstance(node, dict) and "$ref" in node]
        self.assertTrue(refs)
        self.assertTrue(all(ref.startswith("#/$defs/") for ref in refs))
        self.assertEqual(hashlib.sha256(V2_SCHEMA_PATH.read_bytes()).hexdigest(), V2_SCHEMA_SHA256)
        self.assertEqual(stable_schema_errors(make_validator(self.v2_schema), self.valid_v2_fixture), [])

    def test_v3_differs_from_v2_only_by_version_metadata_and_constitution_field(self):
        self.assertEqual(self.v3_schema["properties"]["schema_version"], {"const": 3})
        self.assertNotIn("constitution_version", self.v3_schema["properties"])
        self.assertNotIn("constitution_version", self.v3_schema["required"])
        normalized_v2 = copy.deepcopy(self.v2_schema)
        normalized_v3 = copy.deepcopy(self.v3_schema)
        for schema in (normalized_v2, normalized_v3):
            schema.pop("$id")
            schema.pop("title")
            schema["properties"]["schema_version"] = {"const": "normalized"}
        normalized_v2["required"].remove("constitution_version")
        normalized_v2["properties"].pop("constitution_version")
        self.assertEqual(normalized_v2, normalized_v3)
        Draft202012Validator.check_schema(self.v3_schema)
        self.assertEqual(stable_schema_errors(make_validator(self.v3_schema), self.registry), [])
        invalid = load_json(V3_FIXTURE_ROOT / "invalid/architecture-constitution-version.json")
        errors = stable_schema_errors(make_validator(self.v3_schema), invalid)
        self.assertTrue(any(error.validator == "additionalProperties" for error in errors))

    def test_registry_validates_without_writes(self):
        guarded_paths = [ROOT / "governance", V2_FIXTURE_ROOT, V3_FIXTURE_ROOT]
        before = tree_digest(guarded_paths)
        first = stable_schema_errors(make_validator(self.v3_schema), self.registry)
        second = stable_schema_errors(make_validator(self.v3_schema), self.registry)
        after = tree_digest(guarded_paths)
        self.assertEqual(first, [])
        self.assertEqual(first, second)
        self.assertEqual(before, after)

    def test_registry_has_safe_existing_unique_paths_and_valid_references(self):
        self.assertEqual(cross_validation_issues(self.registry, check_filesystem=True), [])

    def test_cross_validation_rejects_duplicate_ids_self_dependencies_and_conflicts(self):
        duplicate = copy.deepcopy(self.valid_fixture)
        duplicate["modules"][1]["id"] = duplicate["modules"][0]["id"]
        self.assertIn("duplicate-module-id", {issue[0] for issue in cross_validation_issues(duplicate)})

        self_dependency = copy.deepcopy(self.valid_fixture)
        self_dependency["modules"][0]["allowed_dependency_ids"] = [
            self_dependency["modules"][0]["id"]
        ]
        self.assertIn("self-dependency", {issue[0] for issue in cross_validation_issues(self_dependency)})

        conflict = copy.deepcopy(self.valid_fixture)
        dependency = conflict["modules"][0]["allowed_dependency_ids"][0]
        conflict["modules"][0]["prohibited_dependency_ids"] = [dependency]
        self.assertIn("dependency-conflict", {issue[0] for issue in cross_validation_issues(conflict)})

    def test_registry_versions_are_the_governed_initial_versions(self):
        self.assertEqual(self.registry["schema_version"], 3)
        self.assertEqual(self.registry["record_version"], "2.0.0")
        self.assertEqual(self.registry["architecture_version"], "1.3.0")
        self.assertNotIn("constitution_version", self.registry)

    def test_registry_contains_no_derived_inventories(self):
        present = DERIVED_INVENTORY_FIELDS.intersection(self.registry)
        self.assertEqual(present, set())
        all_keys = {
            key
            for node in self._nodes(self.registry)
            if isinstance(node, dict)
            for key in node
        }
        self.assertEqual(DERIVED_INVENTORY_FIELDS.intersection(all_keys), set())

    def test_required_architectural_relations_are_exact(self):
        modules = {module["id"]: module for module in self.registry["modules"]}
        expected_allowed = {
            "module.public-facade": {"module.cli"},
            "module.capability-introspection": {
                "module.builders",
                "module.cli",
                "module.governance",
                "module.template-catalog",
                "module.template-system",
            },
            "module.cli": {"module.builders", "module.template-system"},
            "module.constitutional-audit": {
                "module.capability-introspection", "module.governance"
            },
            "module.builders": {"module.template-catalog", "module.template-system"},
            "module.template-system": {"module.template-catalog"},
            "module.template-catalog": set(),
            "module.governance": set(),
        }
        self.assertEqual(
            {name: set(module["allowed_dependency_ids"]) for name, module in modules.items()},
            expected_allowed,
        )
        self.assertNotIn(
            "contract.public-facade", modules["module.cli"]["consumes_contract_ids"]
        )
        self.assertEqual(
            modules["module.template-catalog"]["provides_contract_ids"],
            ["contract.default-generated-content"],
        )
        self.assertEqual(modules["module.template-catalog"]["consumes_contract_ids"], [])
        self.assertEqual(modules["module.governance"]["allowed_dependency_ids"], [])
        for name, module in modules.items():
            if name not in {
                "module.governance",
                "module.capability-introspection",
                "module.constitutional-audit",
            }:
                self.assertNotIn("module.governance", module["allowed_dependency_ids"])
        self.assertEqual(
            modules["module.capability-introspection"]["provides_contract_ids"],
            ["contract.capability-introspection"],
        )
        self.assertEqual(
            modules["module.constitutional-audit"]["provides_contract_ids"],
            ["contract.constitutional-audit"],
        )
        self.assertEqual(
            modules["module.constitutional-audit"]["consumes_contract_ids"],
            [
                "contract.capability-introspection",
                "contract.governance-policy",
                "contract.governance-schema",
            ],
        )
        self.assertEqual(
            modules["module.governance"]["provides_contract_ids"],
            ["contract.governance-policy", "contract.governance-schema"],
        )
        self.assertNotIn("contract.builder-services", self.registry["contract_ids"])
        self.assertNotIn(
            "contract.builder-public-api",
            modules["module.capability-introspection"]["consumes_contract_ids"],
        )
        for name, module in modules.items():
            if name not in {
                "module.capability-introspection", "module.constitutional-audit"
            }:
                self.assertNotIn(
                    "module.capability-introspection", module["allowed_dependency_ids"]
                )
            if name != "module.constitutional-audit":
                self.assertNotIn(
                    "module.constitutional-audit", module["allowed_dependency_ids"]
                )

    def test_static_ast_analysis_is_limited_and_finds_no_prohibited_imports(self):
        self.assertIn("non-exhaustive", AST_ANALYSIS_SCOPE)
        observed = internal_static_dependencies(self.registry)
        modules = {module["id"]: module for module in self.registry["modules"]}
        for module_id, dependencies in observed.items():
            with self.subTest(module=module_id):
                prohibited = set(modules[module_id]["prohibited_dependency_ids"])
                allowed = set(modules[module_id]["allowed_dependency_ids"])
                self.assertEqual(dependencies & prohibited, set())
                self.assertLessEqual(dependencies, allowed)

    def test_each_invalid_v2_fixture_fails_for_one_specific_reason(self):
        cases = {
            "architecture-duplicate-path": ("cross", "duplicate-path"),
            "architecture-invalid-contract-reference": ("cross", "unknown-contract"),
            "architecture-invalid-dependency": ("cross", "unknown-dependency"),
            "architecture-invalid-path-escape": ("schema", "pattern"),
            "architecture-invalid-schema-version": ("schema", "const"),
            "architecture-unknown-property": ("schema", "additionalProperties"),
        }
        invalid_dir = V2_FIXTURE_ROOT / "invalid"
        self.assertEqual(
            sorted(path.stem for path in invalid_dir.glob("architecture-*.json")),
            sorted(cases),
        )
        for name, (validation_type, expected) in cases.items():
            fixture = load_json(invalid_dir / f"{name}.json")
            schema_errors = stable_schema_errors(make_validator(self.v2_schema), fixture)
            cross_issues = cross_validation_issues(fixture)
            with self.subTest(fixture=name):
                if validation_type == "schema":
                    self.assertEqual(len(schema_errors), 1)
                    self.assertEqual(schema_errors[0].validator, expected)
                else:
                    self.assertEqual(schema_errors, [])
                    self.assertEqual(len(cross_issues), 1)
                    self.assertEqual(cross_issues[0][0], expected)

    @staticmethod
    def _nodes(value):
        yield value
        if isinstance(value, dict):
            for child in value.values():
                yield from ArchitectureRegistryTests._nodes(child)
        elif isinstance(value, list):
            for child in value:
                yield from ArchitectureRegistryTests._nodes(child)


if __name__ == "__main__":
    unittest.main()
