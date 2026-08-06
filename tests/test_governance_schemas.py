import copy
import hashlib
import json
import unittest
from pathlib import Path

try:
    from jsonschema import Draft202012Validator, FormatChecker, validators
    from referencing import Registry
except ModuleNotFoundError as error:
    raise RuntimeError(
        "Missing development dependency; run: "
        "python3 -m pip install -r requirements-dev.txt"
    ) from error


ROOT = Path(__file__).resolve().parents[1]
SCHEMA_DIR = ROOT / "governance" / "schemas" / "v1"
FIXTURE_DIR = ROOT / "tests" / "fixtures" / "governance" / "v1"
SCHEMA_NAMES = (
    "architecture",
    "capability",
    "constitution-version",
    "contract",
    "exception",
    "work-order",
)


def load_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def reject_remote_retrieval(uri):
    raise AssertionError(f"Schema validation attempted network retrieval: {uri}")


def validator_for(schema):
    return Draft202012Validator(
        schema,
        format_checker=FormatChecker(),
        registry=Registry(retrieve=reject_remote_retrieval),
    )


def stable_errors(validator, instance):
    errors = validator.iter_errors(instance)
    return sorted(
        errors,
        key=lambda error: (
            tuple(str(part) for part in error.absolute_path),
            error.validator,
            error.message,
        ),
    )


def tree_digest(root):
    digest = hashlib.sha256()
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        digest.update(path.relative_to(root).as_posix().encode("utf-8"))
        digest.update(path.read_bytes())
    return digest.hexdigest()


def iter_nodes(value):
    yield value
    if isinstance(value, dict):
        for child in value.values():
            yield from iter_nodes(child)
    elif isinstance(value, list):
        for child in value:
            yield from iter_nodes(child)


class GovernanceSchemaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.schemas = {
            name: load_json(SCHEMA_DIR / f"{name}.schema.json")
            for name in SCHEMA_NAMES
        }
        cls.valid = {
            name: load_json(FIXTURE_DIR / "valid" / f"{name}.json")
            for name in SCHEMA_NAMES
        }

    def test_exactly_six_versioned_schemas_exist_and_are_valid_json(self):
        schema_files = sorted(path.name for path in SCHEMA_DIR.glob("*.schema.json"))
        self.assertEqual(
            schema_files,
            [f"{name}.schema.json" for name in sorted(SCHEMA_NAMES)],
        )
        self.assertEqual(len(self.schemas), 6)

    def test_jsonschema_dependency_supports_draft_2020_12(self):
        self.assertIs(
            Draft202012Validator,
            validators.validator_for(
                {"$schema": "https://json-schema.org/draft/2020-12/schema"}
            ),
        )
        for schema in self.schemas.values():
            Draft202012Validator.check_schema(schema)

    def test_schemas_declare_draft_unique_ids_and_schema_version_one(self):
        schema_ids = []
        for name, schema in self.schemas.items():
            with self.subTest(schema=name):
                self.assertEqual(
                    schema["$schema"],
                    "https://json-schema.org/draft/2020-12/schema",
                )
                self.assertEqual(schema["properties"]["schema_version"], {"const": 1})
                self.assertIn("schema_version", schema["required"])
                schema_ids.append(schema["$id"])
        self.assertEqual(len(schema_ids), len(set(schema_ids)))

    def test_schema_record_constitution_and_architecture_versions_are_separate(self):
        for name, schema in self.schemas.items():
            with self.subTest(schema=name):
                self.assertIn("record_version", schema["required"])
                self.assertIn("record_version", schema["properties"])
        self.assertIn(
            "architecture_version", self.schemas["architecture"]["required"]
        )
        self.assertIn(
            "constitution_version", self.schemas["architecture"]["required"]
        )
        self.assertIn(
            "constitution_version",
            self.schemas["constitution-version"]["required"],
        )

    def test_all_object_schemas_reject_unknown_properties(self):
        for name, schema in self.schemas.items():
            object_nodes = [
                node
                for node in iter_nodes(schema)
                if isinstance(node, dict) and node.get("type") == "object"
            ]
            with self.subTest(schema=name):
                self.assertTrue(object_nodes)
                self.assertTrue(
                    all(node.get("additionalProperties") is False for node in object_nodes)
                )
                instance = {**self.valid[name], "unexpected": True}
                errors = stable_errors(validator_for(schema), instance)
                self.assertEqual(errors[0].validator, "additionalProperties")

    def test_all_references_are_internal_and_resolve_without_network(self):
        for name, schema in self.schemas.items():
            references = [
                node["$ref"]
                for node in iter_nodes(schema)
                if isinstance(node, dict) and "$ref" in node
            ]
            with self.subTest(schema=name):
                self.assertTrue(references)
                self.assertTrue(all(ref.startswith("#/$defs/") for ref in references))
                self.assertEqual(stable_errors(validator_for(schema), self.valid[name]), [])

    def test_valid_fixtures_are_deterministic_and_do_not_write(self):
        before = tree_digest(ROOT / "governance"), tree_digest(FIXTURE_DIR)
        first = {}
        second = {}
        for name, schema in self.schemas.items():
            validator = validator_for(schema)
            first[name] = [error.message for error in stable_errors(validator, self.valid[name])]
            second[name] = [error.message for error in stable_errors(validator, self.valid[name])]
        after = tree_digest(ROOT / "governance"), tree_digest(FIXTURE_DIR)
        self.assertEqual(first, second)
        self.assertEqual(first, {name: [] for name in SCHEMA_NAMES})
        self.assertEqual(before, after)

    def test_identifier_arrays_in_valid_fixtures_have_stable_order(self):
        for name, fixture in self.valid.items():
            for field, value in fixture.items():
                if isinstance(value, list) and all(isinstance(item, str) for item in value):
                    with self.subTest(schema=name, field=field):
                        self.assertEqual(value, sorted(value))

    def test_each_invalid_fixture_fails_for_its_expected_reason(self):
        cases = {
            "architecture-missing-schema-version": (
                "architecture", (), "required", "schema_version"
            ),
            "capability-invalid-dependency": (
                "capability", ("dependency_ids", 0), "pattern", None
            ),
            "constitution-version-invalid-semver": (
                "constitution-version", ("constitution_version",), "pattern", None
            ),
            "contract-invalid-change-type": (
                "contract", ("change_type",), "enum", None
            ),
            "exception-missing-expiration": (
                "exception", (), "required", "expires_at"
            ),
            "work-order-missing-reversal": (
                "work-order", (), "required", "reversal"
            ),
        }
        invalid_dir = FIXTURE_DIR / "invalid"
        self.assertEqual(
            sorted(path.stem for path in invalid_dir.glob("*.json")),
            sorted(cases),
        )
        for fixture_name, (schema_name, path, keyword, message_part) in cases.items():
            instance = load_json(invalid_dir / f"{fixture_name}.json")
            errors = stable_errors(validator_for(self.schemas[schema_name]), instance)
            with self.subTest(fixture=fixture_name):
                self.assertEqual(len(errors), 1)
                self.assertEqual(tuple(errors[0].absolute_path), path)
                self.assertEqual(errors[0].validator, keyword)
                if message_part:
                    self.assertIn(message_part, errors[0].message)

    def test_semver_git_hash_dates_and_enumerations_are_enforced(self):
        cases = (
            ("architecture", "architecture_version", "1.0", "pattern"),
            ("architecture", "source_commit", "abc123", "pattern"),
            ("constitution-version", "effective_at", "06/08/2026", "format"),
            ("contract", "status", "unknown", "enum"),
        )
        for schema_name, field, invalid_value, keyword in cases:
            instance = {**self.valid[schema_name], field: invalid_value}
            errors = stable_errors(validator_for(self.schemas[schema_name]), instance)
            with self.subTest(schema=schema_name, field=field):
                self.assertEqual(len(errors), 1)
                self.assertEqual(errors[0].validator, keyword)

    def test_completed_work_orders_require_commits_tests_and_reversal(self):
        schema = self.schemas["work-order"]
        for status in ("implemented", "published"):
            for missing in ("commits", "tests", "reversal"):
                instance = copy.deepcopy(self.valid["work-order"])
                instance["status"] = status
                del instance[missing]
                errors = stable_errors(validator_for(schema), instance)
                with self.subTest(status=status, missing=missing):
                    self.assertEqual(len(errors), 1)
                    self.assertEqual(errors[0].validator, "required")
                    self.assertIn(missing, errors[0].message)

    def test_exception_requires_governance_and_expiration_fields(self):
        schema = self.schemas["exception"]
        required = (
            "expires_at",
            "compensating_controls",
            "approval_ids",
            "remediation_work_order_id",
        )
        for missing in required:
            instance = copy.deepcopy(self.valid["exception"])
            del instance[missing]
            errors = stable_errors(validator_for(schema), instance)
            with self.subTest(missing=missing):
                self.assertEqual(len(errors), 1)
                self.assertEqual(errors[0].validator, "required")
                self.assertIn(missing, errors[0].message)


if __name__ == "__main__":
    unittest.main()
