import contextlib
import hashlib
import io
import json
import shutil
import socket
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest import mock

try:
    from jsonschema import Draft202012Validator, FormatChecker
    from referencing import Registry
except ModuleNotFoundError as error:
    raise RuntimeError(
        "Missing development dependency; run: "
        "python3 -m pip install -r requirements-dev.txt"
    ) from error

import constitutional_audit.api as audit_api
from constitutional_audit import AuditInputError, audit_camilobuilder
from constitutional_audit.controls import CONTROLS, MANUAL_ASSERTIONS, UNVERIFIED_OBLIGATIONS
from constitutional_audit.validation import AST_ANALYSIS_SCOPE, ValidationUnavailable


ROOT = Path(__file__).resolve().parents[1]
V1_SCHEMA = ROOT / "governance/schemas/v1/audit-report.schema.json"
V2_SCHEMA = ROOT / "governance/schemas/v2/audit-report.schema.json"
V1_FIXTURES = ROOT / "tests/fixtures/governance/audit/v1"
V2_FIXTURES = ROOT / "tests/fixtures/governance/audit/v2"
V1_SCHEMA_SHA256 = "3f54aed74a6f6a6f0943a48a82af12674b71d8b0a68f011c0dab88def0f4b727"
INSTANT = datetime.fromisoformat("2026-08-07T12:00:00+00:00")
EXPECTED_CONTROLS = {
    "control.constitution.version",
    "control.schemas.selection",
    "control.schemas.validation",
    "control.schemas.references",
    "control.architecture.registry-schema",
    "control.architecture.modules",
    "control.architecture.dependencies",
    "control.architecture.runtime-coherence",
    "control.architecture.contracts",
    "control.architecture.no-derived-inventories",
    "control.work-orders.integrity",
    "control.governance.manual-assertion-sources",
    "control.references.integrity",
    "control.introspection.coherence",
}
COPY_PATHS = (
    "builder.py", "builder_cli.py", "builders", "capability_introspection",
    "constitutional_audit", "governance", "template_system", "templates",
)


def load_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def stable_errors(schema, instance):
    def reject_remote(uri):
        raise AssertionError(f"network retrieval attempted: {uri}")

    validator = Draft202012Validator(
        schema,
        format_checker=FormatChecker(),
        registry=Registry(retrieve=reject_remote),
    )
    return sorted(
        validator.iter_errors(instance),
        key=lambda error: (
            tuple(str(part) for part in error.absolute_path),
            error.validator,
            error.message,
        ),
    )


def digest(root):
    result = hashlib.sha256()
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        result.update(path.relative_to(root).as_posix().encode())
        result.update(path.read_bytes())
    return result.hexdigest()


def copy_repository(destination):
    for relative in COPY_PATHS:
        source = ROOT / relative
        target = destination / relative
        if source.is_dir():
            shutil.copytree(source, target)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)


def mutate_json(root, relative, mutator):
    path = root / relative
    document = load_json(path)
    mutator(document)
    write_json(path, document)


def install_exception(root, status="active", *, covering=False, critical_incomplete=False):
    source_name = "exception-closed.json" if status in {"closed", "revoked"} else "exception-active.json"
    document = load_json(ROOT / "tests/fixtures/governance/v2/valid" / source_name)
    document["id"] = "EXCEPTION-001"
    document["starts_at"] = "2026-08-01T00:00:00+00:00"
    document["expires_at"] = "2026-09-01T00:00:00+00:00"
    if covering:
        document["constitutional_provision"] = "principle.traceability"
        document["approval_policy"] = "ordinary"
        document["affected_component_ids"] = ["module.builders"]
        document["affected_contract_ids"] = []
    if status == "active":
        document["status"] = "active"
        document["conformance_status"] = "temporarily_authorized"
        document["status_history"] = [{
            "from": "proposed", "to": "active", "at": "2026-08-01T01:00:00+00:00"
        }]
        document.pop("closure", None)
    elif status == "expired":
        document["status"] = "expired"
        document["conformance_status"] = "nonconforming"
        document["expires_at"] = "2026-08-06T00:00:00+00:00"
        document["status_history"] = [
            {"from": "proposed", "to": "active", "at": "2026-08-01T01:00:00+00:00"},
            {"from": "active", "to": "expired", "at": "2026-08-06T00:00:00+00:00"},
        ]
        document.pop("closure", None)
    else:
        document["status"] = status
        document["conformance_status"] = "resolved" if status == "closed" else "nonconforming"
        document["status_history"] = [
            {"from": "proposed", "to": "active", "at": "2026-08-01T01:00:00+00:00"},
            {"from": "active", "to": status, "at": "2026-08-02T00:00:00+00:00"},
        ]
        document["closure"] = {
            "at": "2026-08-02T00:00:00+00:00",
            "reason": "Synthetic closure",
            "approval_ids": ["approval.architect"],
        }
    if critical_incomplete:
        document["constitutional_provision"] = "principle.failure-safe"
        document["approval_policy"] = "critical"
        document["approval_ids"] = ["approval.only-one"]
    path = root / "governance/exceptions/EXCEPTION-001.json"
    write_json(path, document)
    write_json(root / "governance/exceptions/index.json", [{
        "id": "EXCEPTION-001", "status": status,
        "path": "governance/exceptions/EXCEPTION-001.json",
    }])


class AuditReportSchemaTests(unittest.TestCase):
    def test_v1_is_byte_for_byte_intact_and_v2_is_closed_local_draft_2020_12(self):
        self.assertEqual(hashlib.sha256(V1_SCHEMA.read_bytes()).hexdigest(), V1_SCHEMA_SHA256)
        schema = load_json(V2_SCHEMA)
        self.assertEqual(schema["$schema"], "https://json-schema.org/draft/2020-12/schema")
        self.assertEqual(schema["properties"]["schema_version"], {"const": 2})
        Draft202012Validator.check_schema(schema)
        nodes = list(self._nodes(schema))
        objects = [item for item in nodes if isinstance(item, dict) and item.get("type") == "object"]
        self.assertTrue(all(item.get("additionalProperties") is False for item in objects))
        refs = [item["$ref"] for item in nodes if isinstance(item, dict) and "$ref" in item]
        self.assertTrue(all(reference.startswith("#/$defs/") for reference in refs))

    def test_v1_and_v2_select_explicitly_and_invalid_v2_fixtures_have_one_cause(self):
        v1_schema = load_json(V1_SCHEMA)
        v2_schema = load_json(V2_SCHEMA)
        v1_report = load_json(V1_FIXTURES / "valid/audit-report.json")
        v2_report = load_json(V2_FIXTURES / "valid/audit-report.json")
        self.assertEqual(stable_errors(v1_schema, v1_report), [])
        self.assertEqual(stable_errors(v2_schema, v2_report), [])
        self.assertTrue(stable_errors(v1_schema, v2_report))
        self.assertTrue(stable_errors(v2_schema, v1_report))
        unknown = {**v2_report, "schema_version": 99}
        unknown_errors = stable_errors(v2_schema, unknown)
        self.assertEqual(len(unknown_errors), 1)
        self.assertEqual(unknown_errors[0].validator, "const")
        cases = {
            "audit-report-legacy-result": "enum",
            "audit-report-unknown-property": "additionalProperties",
        }
        paths = sorted((V2_FIXTURES / "invalid").glob("*.json"))
        self.assertEqual([item.stem for item in paths], sorted(cases))
        for path in paths:
            errors = stable_errors(v2_schema, load_json(path))
            with self.subTest(path=path.name):
                self.assertEqual(len(errors), 1)
                self.assertEqual(errors[0].validator, cases[path.stem])

    @staticmethod
    def _nodes(value):
        yield value
        if isinstance(value, dict):
            for child in value.values():
                yield from AuditReportSchemaTests._nodes(child)
        elif isinstance(value, list):
            for child in value:
                yield from AuditReportSchemaTests._nodes(child)


class ConstitutionalAuditTests(unittest.TestCase):
    def test_current_repository_is_verified_with_exact_governance_catalogs(self):
        report = audit_camilobuilder(evaluation_instant=INSTANT, repository_root=ROOT)
        self.assertEqual(report["automated_result"], "verified")
        self.assertEqual(report["constitution_version"], "2.0.0")
        self.assertEqual(report["architecture_version"], "1.3.0")
        self.assertEqual(report["automated_summary"], {"passed": 14, "failed": 0, "excepted": 0, "indeterminate": 0})
        self.assertEqual({item[0] for item in CONTROLS}, EXPECTED_CONTROLS)
        self.assertEqual([item["id"] for item in report["automated_controls"]], sorted(EXPECTED_CONTROLS))
        self.assertEqual([item["id"] for item in report["manual_assertions"]], [item[0] for item in MANUAL_ASSERTIONS])
        self.assertTrue(all(item["declaration_status"] == "declared" and item["verification_scope"] == "presence_only" for item in report["manual_assertions"]))
        self.assertEqual([item["id"] for item in report["unverified_obligations"]], [item[0] for item in UNVERIFIED_OBLIGATIONS])
        self.assertEqual(report["findings"], [])
        self.assertEqual(stable_errors(load_json(V2_SCHEMA), report), [])
        self.assertIn("non-exhaustive", AST_ANALYSIS_SCOPE)
        control = next(
            item for item in report["automated_controls"]
            if item["id"] == "control.constitution.version"
        )
        self.assertEqual(control["source_ids"], ["governance/CONSTITUTION.md"])

    def test_constitution_source_fails_safely_when_missing_or_invalid(self):
        for case in ("missing", "invalid"):
            with self.subTest(case=case), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                copy_repository(root)
                path = root / "governance/CONSTITUTION.md"
                if case == "missing":
                    path.unlink()
                else:
                    path.write_text("**Versión constitucional:** invalid  \n", encoding="utf-8")
                report = audit_camilobuilder(evaluation_instant=INSTANT, repository_root=root)
                self.assertEqual(report["automated_result"], "indeterminate")
                self.assertGreater(report["automated_summary"]["indeterminate"], 0)

    def test_architecture_v3_is_supported_but_work_order_v3_is_not(self):
        self.assertEqual(
            load_json(ROOT / "governance/architecture/registry.json")["schema_version"],
            3,
        )
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            copy_repository(root)
            mutate_json(
                root,
                "governance/work-orders/WORK-011.json",
                lambda value: value.update(schema_version=3),
            )
            report = audit_camilobuilder(evaluation_instant=INSTANT, repository_root=root)
            self.assertEqual(report["automated_result"], "failed")
            self.assertIn("unknown-schema-version", {item["code"] for item in report["findings"]})

    def test_active_schema_catalog_excludes_legacy_but_protects_active_contracts(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            copy_repository(root)
            (root / "governance/schemas/v1/contract.schema.json").write_text(
                "{", encoding="utf-8"
            )
            report = audit_camilobuilder(evaluation_instant=INSTANT, repository_root=root)
            self.assertEqual(report["automated_result"], "verified")

        for relative in (
            "governance/schemas/v2/audit-report.schema.json",
            "governance/schemas/v3/architecture.schema.json",
        ):
            with self.subTest(schema=relative), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                copy_repository(root)
                mutate_json(
                    root,
                    relative,
                    lambda value: value.update({"$schema": "https://example.invalid/schema"}),
                )
                report = audit_camilobuilder(
                    evaluation_instant=INSTANT, repository_root=root
                )
                self.assertEqual(report["automated_result"], "failed")
                self.assertIn(
                    "unknown-schema-draft", {item["code"] for item in report["findings"]}
                )

    def test_requires_timezone_aware_explicit_instant(self):
        with self.assertRaises(AuditInputError):
            audit_camilobuilder(evaluation_instant=datetime(2026, 8, 7), repository_root=ROOT)
        with self.assertRaises(AuditInputError):
            audit_camilobuilder(evaluation_instant="2026-08-07T12:00:00Z", repository_root=ROOT)

    def test_global_result_precedence_and_warning_behavior_are_exact(self):
        classify = audit_api._classify_result
        self.assertEqual(classify([{"status": "failed", "severity": "warning"}]), "verified")
        self.assertEqual(classify([{"status": "excepted", "severity": "error"}]), "verified_with_declared_exceptions")
        self.assertEqual(classify([{"status": "indeterminate", "severity": "error"}]), "indeterminate")
        self.assertEqual(
            classify([
                {"status": "indeterminate", "severity": "critical"},
                {"status": "failed", "severity": "error"},
            ]),
            "failed",
        )

    def test_jsonschema_is_lazy_and_absence_makes_audit_indeterminate(self):
        command = [sys.executable, "-S", "-c", "import constitutional_audit; print(constitutional_audit.__all__)"]
        imported = subprocess.run(command, cwd=ROOT, check=True, capture_output=True, text=True)
        self.assertIn("audit_camilobuilder", imported.stdout)
        with mock.patch("constitutional_audit.api.validate_with_schema", side_effect=ValidationUnavailable("missing")):
            report = audit_camilobuilder(evaluation_instant=INSTANT, repository_root=ROOT)
        self.assertEqual(report["automated_result"], "indeterminate")
        self.assertGreater(report["automated_summary"]["indeterminate"], 0)

    def test_corrupt_architecture_and_unknown_schema_fail_safely(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            copy_repository(root)
            (root / "governance/architecture/registry.json").write_text("{", encoding="utf-8")
            report = audit_camilobuilder(evaluation_instant=INSTANT, repository_root=root)
            self.assertEqual(report["automated_result"], "indeterminate")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            copy_repository(root)
            mutate_json(root, "governance/architecture/registry.json", lambda value: value.update(schema_version=99))
            report = audit_camilobuilder(evaluation_instant=INSTANT, repository_root=root)
            self.assertEqual(report["automated_result"], "failed")
            self.assertIn("unknown-schema-version", {item["code"] for item in report["findings"]})

    def test_detects_missing_module_prohibited_dependency_contract_and_inventory(self):
        mutations = {
            "missing-module": lambda value: value["modules"][0].update(paths=["missing-module"]),
            "prohibited-dependency": lambda value: value["modules"][0]["allowed_dependency_ids"].append("module.cli"),
            "unknown-contract": lambda value: value["modules"][0]["consumes_contract_ids"].append("contract.unknown"),
            "derived-inventory": lambda value: value.update(commands=[]),
        }
        for name, mutation in mutations.items():
            with self.subTest(case=name), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                copy_repository(root)
                mutate_json(root, "governance/architecture/registry.json", mutation)
                report = audit_camilobuilder(evaluation_instant=INSTANT, repository_root=root)
                self.assertEqual(report["automated_result"], "failed")

    def test_active_verification_reads_only_legacy_summary_fields(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            copy_repository(root)
            mutate_json(
                root,
                "governance/work-orders/WORK-011.json",
                lambda value: value.update(status="proposed"),
            )
            self.assertEqual(
                audit_camilobuilder(
                    evaluation_instant=INSTANT, repository_root=root
                )["automated_result"],
                "verified",
            )
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            copy_repository(root)
            mutate_json(root, "governance/work-orders/WORK-009.json", lambda value: value["affected_contract_ids"].append("contract.unknown"))
            report = audit_camilobuilder(evaluation_instant=INSTANT, repository_root=root)
            self.assertEqual(report["automated_result"], "verified")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            copy_repository(root)
            mutate_json(root, "governance/work-orders/WORK-011.json", lambda value: value.update(status="unknown"))
            report = audit_camilobuilder(evaluation_instant=INSTANT, repository_root=root)
            self.assertEqual(report["automated_result"], "failed")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            copy_repository(root)
            mutate_json(root, "governance/work-orders/WORK-010.json", lambda value: value.update(dependencies=["WORK-999"]))
            report = audit_camilobuilder(evaluation_instant=INSTANT, repository_root=root)
            self.assertEqual(report["automated_result"], "failed")
            self.assertIn("unknown-work-order-dependency", {item["code"] for item in report["findings"]})

    def test_legacy_exception_registry_is_not_an_active_verification_source(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            copy_repository(root)
            def disorder(value):
                builders = next(item for item in value["modules"] if item["id"] == "module.builders")
                builders["consumes_contract_ids"] = list(reversed(builders["consumes_contract_ids"]))
            mutate_json(root, "governance/architecture/registry.json", disorder)
            install_exception(root, covering=True)
            report = audit_camilobuilder(evaluation_instant=INSTANT, repository_root=root)
            self.assertEqual(report["automated_result"], "failed")
            self.assertEqual(report["declared_exceptions"], [])
            self.assertFalse(any(item["outcome"] == "excepted" for item in report["findings"]))

    def test_all_legacy_exception_states_are_ignored_by_active_verification(self):
        for case in ("active", "expired", "not-started", "critical", "closed", "revoked"):
            with self.subTest(case=case), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                copy_repository(root)
                if case == "critical":
                    install_exception(root, critical_incomplete=True)
                elif case == "not-started":
                    install_exception(root)
                    mutate_json(
                        root,
                        "governance/exceptions/EXCEPTION-001.json",
                        lambda value: value.update(
                            starts_at="2026-08-08T00:00:00+00:00",
                            expires_at="2026-09-01T00:00:00+00:00",
                            status_history=[{
                                "from": "proposed", "to": "active",
                                "at": "2026-08-08T01:00:00+00:00",
                            }],
                        ),
                    )
                else:
                    install_exception(root, status=case)
                report = audit_camilobuilder(evaluation_instant=INSTANT, repository_root=root)
                self.assertEqual(report["automated_result"], "verified")
                self.assertEqual(report["declared_exceptions"], [])
                self.assertFalse(
                    any(item["id"].startswith("control.exceptions.") for item in report["automated_controls"])
                )

    def test_active_verification_does_not_require_the_legacy_exception_index(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            copy_repository(root)
            (root / "governance/exceptions/index.json").unlink()
            report = audit_camilobuilder(evaluation_instant=INSTANT, repository_root=root)
            self.assertEqual(report["automated_result"], "verified")
            self.assertEqual(report["declared_exceptions"], [])

    def test_active_verification_does_not_require_historical_git_objects(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            copy_repository(root)
            (root / ".git").mkdir()
            mutate_json(
                root,
                "governance/work-orders/WORK-010.json",
                lambda value: value["evidence_refs"].__setitem__(0, "commit:" + "0" * 40),
            )
            with mock.patch("subprocess.run", side_effect=AssertionError("Git history lookup forbidden")):
                report = audit_camilobuilder(evaluation_instant=INSTANT, repository_root=root)
            self.assertEqual(report["automated_result"], "verified")
            self.assertEqual(report["automated_summary"]["failed"], 0)
            self.assertEqual(report["automated_summary"]["indeterminate"], 0)

    def test_introspection_mismatch_fails_technical_verification(self):
        real = audit_api.describe_camilobuilder(repository_root=ROOT)
        inconsistent = json.loads(json.dumps(real))
        inconsistent["architecture_version"]["value"] = "9.0.0"
        with mock.patch.object(audit_api, "describe_camilobuilder", return_value=inconsistent):
            report = audit_camilobuilder(evaluation_instant=INSTANT, repository_root=ROOT)
        self.assertEqual(report["automated_result"], "failed")
        self.assertIn("introspection-source-mismatch", {item["code"] for item in report["findings"]})

    def test_missing_unsafe_or_incomplete_maintainer_source_is_indeterminate(self):
        for case in ("missing", "symlink", "invalid-utf8", "incomplete"):
            with self.subTest(case=case), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                copy_repository(root)
                source = root / "governance/MAINTAINERS.md"
                if case == "missing":
                    source.unlink()
                elif case == "symlink":
                    external = root / "maintainers-external.md"
                    source.replace(external)
                    source.symlink_to(external)
                elif case == "invalid-utf8":
                    source.write_bytes(b"\xff\xfe")
                else:
                    source.write_text("**Última confirmación:** 2026-08-08T17:46:16+02:00\n", encoding="utf-8")
                report = audit_camilobuilder(evaluation_instant=INSTANT, repository_root=root)
                self.assertEqual(report["automated_result"], "indeterminate")
                self.assertTrue(all(item["declaration_status"] == "unavailable" for item in report["manual_assertions"]))

    def test_governance_catalog_ids_sources_and_order_are_stable(self):
        groups = (CONTROLS, MANUAL_ASSERTIONS, UNVERIFIED_OBLIGATIONS)
        ids = [item[0] for group in groups for item in group]
        self.assertEqual(len(ids), len(set(ids)))
        for group in groups:
            self.assertEqual([item[0] for item in group], sorted(item[0] for item in group))
        provisions = {
            "principle.determinism", "principle.incremental-evolution",
            "principle.no-drift-self-knowledge",
            "principle.safe-failure-minimum-access", "principle.traceability",
        }
        self.assertTrue(all(item[3] in provisions for item in CONTROLS))
        for _id, _title, source, _detail in MANUAL_ASSERTIONS:
            self.assertTrue((ROOT / source).is_file())
        for _id, _title, source, _reason in UNVERIFIED_OBLIGATIONS:
            relative, separator, fragment = source.partition("#")
            self.assertEqual(separator, "#")
            self.assertTrue(fragment)
            self.assertTrue((ROOT / relative).is_file())

    def test_is_deterministic_silent_read_only_offline_and_clock_free(self):
        before = digest(ROOT)
        stdout = io.StringIO()
        stderr = io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr), \
             mock.patch.object(socket, "socket", side_effect=AssertionError("network forbidden")), \
             mock.patch("time.time", side_effect=AssertionError("clock forbidden")):
            first = audit_camilobuilder(evaluation_instant=INSTANT, repository_root=ROOT)
            second = audit_camilobuilder(evaluation_instant=INSTANT, repository_root=ROOT)
        self.assertEqual(first, second)
        self.assertEqual(first["automated_result"], "verified")
        self.assertEqual(
            json.dumps(first, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode(),
            json.dumps(second, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode(),
        )
        self.assertEqual(stdout.getvalue(), "")
        self.assertEqual(stderr.getvalue(), "")
        self.assertEqual(before, digest(ROOT))
        serialized = json.dumps(first)
        self.assertNotIn(str(ROOT), serialized)
        audit_source = (ROOT / "constitutional_audit/api.py").read_text(encoding="utf-8")
        for forbidden in ("datetime.now(", "datetime.utcnow(", "time.time("):
            self.assertNotIn(forbidden, audit_source)


if __name__ == "__main__":
    unittest.main()
