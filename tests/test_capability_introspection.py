import contextlib
import hashlib
import io
import json
import shutil
import socket
import tempfile
import unittest
from pathlib import Path
from unittest import mock

try:
    from jsonschema import Draft202012Validator
    from referencing import Registry
except ModuleNotFoundError as error:
    raise RuntimeError(
        "Missing development dependency; run: "
        "python3 -m pip install -r requirements-dev.txt"
    ) from error

import capability_introspection.api as introspection_api
from capability_introspection import IntrospectionError, describe_camilobuilder
from builders.project_builder import ProjectBuilder


ROOT = Path(__file__).resolve().parents[1]
V2_SCHEMA = ROOT / "governance" / "schemas" / "v2" / "capability.schema.json"
V2_FIXTURE_ROOT = ROOT / "tests" / "fixtures" / "governance" / "v2"


def load_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def reject_remote_retrieval(uri):
    raise AssertionError(f"Schema validation attempted network retrieval: {uri}")


def validator(schema):
    return Draft202012Validator(
        schema,
        registry=Registry(retrieve=reject_remote_retrieval),
    )


def stable_errors(schema_validator, instance):
    return sorted(
        schema_validator.iter_errors(instance),
        key=lambda error: (
            tuple(str(part) for part in error.absolute_path),
            error.validator,
            error.message,
        ),
    )


def tree_digest(path):
    digest = hashlib.sha256()
    for item in sorted(candidate for candidate in path.rglob("*") if candidate.is_file()):
        digest.update(item.relative_to(path).as_posix().encode("utf-8"))
        digest.update(item.read_bytes())
    return digest.hexdigest()


class CapabilityIntrospectionSchemaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.v2_schema = load_json(V2_SCHEMA)
        cls.valid_v2 = load_json(V2_FIXTURE_ROOT / "valid" / "capability.json")

    def test_v2_is_closed_draft_2020_12_and_validates_locally(self):
        self.assertEqual(self.v2_schema["$schema"], "https://json-schema.org/draft/2020-12/schema")
        self.assertEqual(self.v2_schema["properties"]["schema_version"], {"const": 2})
        Draft202012Validator.check_schema(self.v2_schema)
        nodes = list(self._nodes(self.v2_schema))
        objects = [node for node in nodes if isinstance(node, dict) and node.get("type") == "object"]
        self.assertTrue(all(node.get("additionalProperties") is False for node in objects))
        refs = [node["$ref"] for node in nodes if isinstance(node, dict) and "$ref" in node]
        self.assertTrue(all(reference.startswith("#/$defs/") for reference in refs))
        self.assertEqual(stable_errors(validator(self.v2_schema), self.valid_v2), [])

    def test_invalid_v2_fixtures_have_one_concrete_cause(self):
        cases = {
            "capability-invalid-schema-version": "const",
            "capability-block-multiple-payloads": "additionalProperties",
        }
        paths = sorted((V2_FIXTURE_ROOT / "invalid").glob("capability-*.json"))
        self.assertEqual([path.stem for path in paths], sorted(cases))
        for path in paths:
            errors = stable_errors(validator(self.v2_schema), load_json(path))
            with self.subTest(fixture=path.stem):
                self.assertEqual(len(errors), 1)
                self.assertEqual(errors[0].validator, cases[path.stem])

    @staticmethod
    def _nodes(value):
        yield value
        if isinstance(value, dict):
            for child in value.values():
                yield from CapabilityIntrospectionSchemaTests._nodes(child)
        elif isinstance(value, list):
            for child in value:
                yield from CapabilityIntrospectionSchemaTests._nodes(child)


class CapabilityIntrospectionTests(unittest.TestCase):
    def setUp(self):
        self.report = describe_camilobuilder(repository_root=ROOT)

    def test_public_package_exports_only_the_approved_api(self):
        import capability_introspection

        self.assertEqual(
            capability_introspection.__all__,
            ("describe_camilobuilder", "IntrospectionError"),
        )

    def test_report_validates_and_every_block_has_one_payload(self):
        self.assertEqual(stable_errors(validator(load_json(V2_SCHEMA)), self.report), [])
        for name, block in self.report.items():
            if name in {"schema_version", "report_version"}:
                continue
            with self.subTest(block=name):
                self.assertIn(block["classification"], {
                    "executable_derived", "normative_declared", "observed_state"
                })
                self.assertTrue(block["source"])
                self.assertEqual(len({"value", "items", "data"}.intersection(block)), 1)

    def test_derives_exact_executable_commands_builders_and_types(self):
        commands = self.report["commands"]["items"]
        self.assertEqual(len(commands), 14)
        self.assertEqual([item["name"] for item in commands], sorted(item["name"] for item in commands))
        builders = self.report["builders"]["items"]
        self.assertEqual(len(builders), 4)
        project = next(item for item in builders if item["name"] == "ProjectBuilder")
        self.assertEqual(project, {
            "module": ProjectBuilder.__module__, "name": "ProjectBuilder", "component_type": "project"
        })
        self.assertEqual(self.report["component_types"]["items"], ["agent", "department", "project", "service"])

    def test_templates_contracts_dependencies_and_indexes_use_canonical_sources(self):
        templates = self.report["templates"]["items"]
        self.assertEqual(
            [(item["component_type"], item["name"]) for item in templates],
            [
                ("agent", "camilo-os-agent"),
                ("agent", "default"),
                ("department", "default"),
                ("project", "default"),
                ("service", "agent-core"),
                ("service", "default"),
            ],
        )
        architecture = load_json(ROOT / "governance" / "architecture" / "registry.json")
        self.assertEqual(self.report["contracts"]["items"], sorted(architecture["contract_ids"]))
        self.assertEqual(
            [item["module_id"] for item in self.report["architectural_dependencies"]["items"]],
            sorted(module["id"] for module in architecture["modules"]),
        )
        self.assertEqual(self.report["work_orders"]["source"], "governance/work-orders/")
        self.assertEqual(self.report["work_orders"]["items"], [
            {
                "id": "WORK-009", "title": "Establish CamiloBuilder Constitution",
                "status": "published", "path": "governance/work-orders/WORK-009.json",
            },
            {
                "id": "WORK-010", "title": "Make constitutional CI history-aware",
                "status": "done", "path": "governance/work-orders/WORK-010.json",
            },
            {
                "id": "WORK-011", "title": "Introduce Work Order Schema v3",
                "status": "cancelled", "path": "governance/work-orders/WORK-011.json",
            },
        ])
        self.assertEqual(self.report["active_exceptions"]["items"], [])

    def test_classifications_sources_versions_and_observations_are_exact(self):
        self.assertEqual(self.report["architecture_version"]["value"], "1.3.0")
        self.assertEqual(self.report["constitution_version"]["value"], "2.0.0")
        self.assertEqual(
            self.report["constitution_version"]["source"],
            "governance/CONSTITUTION.md",
        )
        self.assertEqual(self.report["commands"]["classification"], "executable_derived")
        self.assertEqual(self.report["contracts"]["classification"], "normative_declared")
        self.assertEqual(self.report["limitations"]["classification"], "observed_state")
        observations = self.report["limitations"]["items"]
        self.assertEqual([item["id"] for item in observations], [
            "observed.capability-registry-absent",
            "observed.contract-registry-absent",
        ])
        self.assertTrue(all(set(item) == {"id", "operation", "target", "result"} for item in observations))
        self.assertTrue(all(item["result"] == "absent" for item in observations))

    def test_is_deterministic_silent_read_only_offline_and_clock_independent(self):
        before = tree_digest(ROOT)
        stdout = io.StringIO()
        stderr = io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr), \
             mock.patch.object(socket, "socket", side_effect=AssertionError("network forbidden")), \
             mock.patch("time.time", side_effect=AssertionError("clock forbidden")):
            first = describe_camilobuilder(repository_root=ROOT)
            second = describe_camilobuilder(repository_root=ROOT)
        after = tree_digest(ROOT)
        self.assertEqual(first, second)
        self.assertEqual(
            json.dumps(first, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(),
            json.dumps(second, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(),
        )
        self.assertEqual(stdout.getvalue(), "")
        self.assertEqual(stderr.getvalue(), "")
        self.assertEqual(before, after)

    def test_fails_safely_without_partial_report_for_corrupt_sources(self):
        cases = {
            "corrupt-json": lambda root: (root / "governance/architecture/registry.json").write_text("{", encoding="utf-8"),
            "unknown-schema": lambda root: self._mutate_json(root / "governance/architecture/registry.json", "schema_version", 99),
            "invalid-constitution": lambda root: (root / "governance/CONSTITUTION.md").write_text("**Versión constitucional:** invalid  \n", encoding="utf-8"),
            "incoherent-work-order": lambda root: self._mutate_json(
                root / "governance/work-orders/WORK-010.json", "id", "WORK-999"
            ),
        }
        for name, corrupt in cases.items():
            with self.subTest(case=name), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                shutil.copytree(ROOT / "governance", root / "governance")
                shutil.copytree(ROOT / "templates", root / "templates")
                corrupt(root)
                with self.assertRaises(IntrospectionError):
                    describe_camilobuilder(repository_root=root)

    def test_fails_safely_for_missing_source_symlink_and_incomplete_metadata(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            shutil.copytree(ROOT / "governance", root / "governance")
            shutil.copytree(ROOT / "templates", root / "templates")
            report = describe_camilobuilder(repository_root=root)
            self.assertEqual(report["active_exceptions"], {
                "classification": "normative_declared",
                "source": "active governance model",
                "items": [],
            })

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            shutil.copytree(ROOT / "governance", root / "governance")
            shutil.copytree(ROOT / "templates", root / "templates")
            registry = root / "governance/architecture/registry.json"
            external = root / "architecture.json"
            registry.replace(external)
            registry.symlink_to(external)
            with self.assertRaises(IntrospectionError):
                describe_camilobuilder(repository_root=root)

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            shutil.copytree(ROOT / "governance", root / "governance")
            shutil.copytree(ROOT / "templates", root / "templates")
            (root / "templates/agent/default/template.json").write_text("{", encoding="utf-8")
            with self.assertRaises(IntrospectionError):
                describe_camilobuilder(repository_root=root)

        with mock.patch.object(introspection_api, "BUILDER_METADATA", ({"builder": ProjectBuilder},)):
            with self.assertRaises(IntrospectionError):
                describe_camilobuilder(repository_root=ROOT)

    @staticmethod
    def _mutate_json(path, field, value):
        document = load_json(path)
        if field == "0.status":
            document[0]["status"] = value
        else:
            document[field] = value
        path.write_text(json.dumps(document), encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
