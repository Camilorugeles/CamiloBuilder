import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_PATH = ROOT / ".github/workflows/constitutional-audit.yml"
WORK_ORDER_PATH = ROOT / "governance/work-orders/WORK-009.json"
MANUAL_INSTANT = "2026-08-07T17:45:00+00:00"
PUBLISHED_BLOCK_8_COMMIT = "b586e24e680ca4a081b512f48858a247fe77ed2c"
DIAGNOSTIC_FIELDS = {
    "evaluation_instant",
    "result",
    "summary",
    "active_exception_ids",
    "findings",
}


def workflow_text():
    return WORKFLOW_PATH.read_text(encoding="utf-8")


def audit_adapter():
    lines = workflow_text().splitlines()
    start = next(
        index for index, line in enumerate(lines) if "python3 - <<'PY'" in line
    )
    end = next(
        index for index in range(start + 1, len(lines))
        if lines[index].strip() == "PY"
    )
    indentation = len(lines[start]) - len(lines[start].lstrip())
    return "\n".join(line[indentation:] for line in lines[start + 1:end]) + "\n"


def run_adapter(*, cwd=ROOT, pythonpath=None, case=None):
    environment = os.environ.copy()
    environment["AUDIT_EVALUATION_INSTANT"] = MANUAL_INSTANT
    if pythonpath is not None:
        environment["PYTHONPATH"] = str(pythonpath)
    if case is not None:
        environment["AUDIT_FAKE_CASE"] = case
    return subprocess.run(
        [sys.executable, "-c", audit_adapter()],
        cwd=cwd,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )


class ConstitutionalAuditWorkflowTests(unittest.TestCase):
    def test_workflow_identity_triggers_job_and_permissions_are_exact(self):
        text = workflow_text()
        self.assertTrue(WORKFLOW_PATH.is_file())
        self.assertIn("name: Constitutional Audit\n", text)
        self.assertRegex(text, r"(?m)^  pull_request:$")
        self.assertRegex(text, r"(?m)^  push:$")
        self.assertRegex(text, r"(?m)^      - main$")
        self.assertRegex(text, r"(?m)^  workflow_dispatch:$")
        permissions = text.split("permissions:\n", 1)[1].split("\njobs:\n", 1)[0]
        permission_lines = [line.strip() for line in permissions.splitlines() if line.strip() and not line.lstrip().startswith("#")]
        self.assertEqual(permission_lines, ["contents: read"])
        self.assertRegex(text, r"(?m)^  constitutional-audit:$")
        self.assertIn("# Constitutional Audit / constitutional-audit", text)

    def test_uses_only_approved_official_actions_and_python(self):
        text = workflow_text()
        actions = re.findall(r"(?m)^\s+uses:\s+([^\s]+)$", text)
        self.assertEqual(actions, ["actions/checkout@v4", "actions/setup-python@v5"])
        self.assertEqual(re.findall(r'python-version:\s+"([^"]+)"', text), ["3.13"])
        self.assertNotIn("${{ secrets.", text)

    def test_installs_only_the_versioned_development_requirements(self):
        text = workflow_text()
        installs = re.findall(r"(?m)^\s+run:\s+(python3 -m pip install[^\n]+)$", text)
        self.assertEqual(
            installs,
            ["python3 -m pip install --requirement requirements-dev.txt"],
        )
        self.assertNotRegex(text, r"pip install (?!.*requirements-dev\.txt)")

    def test_captures_the_runner_clock_once_as_rfc3339_utc_and_exports_it(self):
        text = workflow_text()
        capture = 'audit_evaluation_instant="$(date -u \'+%Y-%m-%dT%H:%M:%SZ\')"'
        self.assertIn(capture, text)
        self.assertEqual(text.count("date -u"), 1)
        self.assertIn("AUDIT_EVALUATION_INSTANT=%s", text)
        self.assertIn('>> "$GITHUB_ENV"', text)
        self.assertNotIn("git show", text)
        self.assertNotIn("%cI", text)
        for path in (
            ROOT / "constitutional_audit/api.py",
            ROOT / "capability_introspection/api.py",
        ):
            source = path.read_text(encoding="utf-8")
            for forbidden in ("datetime.now(", "datetime.utcnow(", "time.time("):
                self.assertNotIn(forbidden, source)

    def test_runs_all_required_validations(self):
        text = workflow_text()
        self.assertIn("python3 -m unittest discover -v", text)
        self.assertIn("python3 -m compileall -q", text)
        for target in (
            "builder.py", "builder_cli.py", "builders", "template_system",
            "capability_introspection", "constitutional_audit", "tests",
        ):
            self.assertIn(target, text)
        self.assertIn("git diff --check", text)
        self.assertIn("tests.test_governance_schemas", text)
        self.assertIn("tests.test_constitutional_audit.AuditReportSchemaTests", text)
        self.assertIn("audit_camilobuilder(evaluation_instant=instant)", text)

    def test_checks_the_complete_tree_before_and_after_without_repair(self):
        text = workflow_text()
        self.assertEqual(text.count("git diff --exit-code"), 2)
        self.assertEqual(
            text.count('test -z "$(git status --porcelain=v1 --untracked-files=all)"'),
            2,
        )
        for forbidden in (
            "git add", "git commit", "git push", "git reset", "git checkout --",
            "git clean",
        ):
            self.assertNotIn(forbidden, text)

    def test_adapter_emits_one_stable_json_and_is_locally_reproducible(self):
        first = run_adapter()
        second = run_adapter()
        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertEqual(first.stdout, second.stdout)
        self.assertEqual(first.stderr, "")
        lines = first.stdout.splitlines()
        self.assertEqual(len(lines), 1)
        diagnostic = json.loads(lines[0])
        self.assertEqual(set(diagnostic), DIAGNOSTIC_FIELDS)
        self.assertEqual(diagnostic["evaluation_instant"], MANUAL_INSTANT)
        self.assertEqual(diagnostic["result"], "compliant")
        self.assertNotIn(str(ROOT), first.stdout)

    def test_result_policy_fails_safe_and_conditions_exceptions(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            package = root / "constitutional_audit"
            package.mkdir()
            package.joinpath("__init__.py").write_text(self._fake_audit_module(), encoding="utf-8")
            expected = {
                "compliant": 0,
                "compliant_with_exceptions": 0,
                "exception_without_active_id": 1,
                "exception_invalid_link": 1,
                "exception_expired": 1,
                "material_failure": 1,
                "non_compliant": 1,
                "indeterminate": 1,
                "contradictory_summary": 1,
            }
            for case, returncode in expected.items():
                with self.subTest(case=case):
                    completed = run_adapter(cwd=root, pythonpath=root, case=case)
                    self.assertEqual(completed.returncode, returncode, completed.stderr)
                    self.assertEqual(completed.stderr, "")
                    lines = completed.stdout.splitlines()
                    self.assertEqual(len(lines), 1)
                    self.assertEqual(set(json.loads(lines[0])), DIAGNOSTIC_FIELDS)

    def test_work_order_traceability_includes_the_published_block_8_commit(self):
        document = json.loads(WORK_ORDER_PATH.read_text(encoding="utf-8"))
        self.assertEqual(document["status"], "in_progress")
        self.assertEqual(document["implementation_commit_ids"][-1], PUBLISHED_BLOCK_8_COMMIT)
        self.assertEqual(document["implementation_commit_ids"].count(PUBLISHED_BLOCK_8_COMMIT), 1)
        self.assertNotIn("registry_closure_commit_id", document)

    @staticmethod
    def _fake_audit_module():
        return '''import os

class AuditInputError(ValueError):
    pass

def audit_camilobuilder(*, evaluation_instant, repository_root=None):
    case = os.environ["AUDIT_FAKE_CASE"]
    result = case if case in {"compliant", "compliant_with_exceptions", "non_compliant", "indeterminate"} else "compliant_with_exceptions"
    active_ids = ["EXCEPTION-001"] if result == "compliant_with_exceptions" else []
    status = "passed"
    findings = []
    if result == "compliant_with_exceptions":
        status = "excepted"
        findings = [{"outcome": "excepted", "severity": "error", "exception_id": "EXCEPTION-001", "code": "synthetic-exception"}]
    elif result == "non_compliant":
        status = "failed"
        findings = [{"outcome": "failed", "severity": "error", "exception_id": None, "code": "synthetic-failure"}]
    elif result == "indeterminate":
        status = "indeterminate"
        findings = [{"outcome": "indeterminate", "severity": "error", "exception_id": None, "code": "synthetic-indeterminate"}]
    if case == "exception_without_active_id":
        active_ids = []
    if case == "exception_invalid_link":
        findings[0]["exception_id"] = "EXCEPTION-999"
    if case == "exception_expired":
        findings[0]["code"] = "expired-exception"
    if case == "material_failure":
        findings.append({"outcome": "failed", "severity": "critical", "exception_id": None, "code": "synthetic-failure"})
    summary = {"passed": status == "passed", "failed": status == "failed", "excepted": status == "excepted", "indeterminate": status == "indeterminate"}
    if case == "contradictory_summary":
        summary["passed"] = 99
    return {
        "evaluation_instant": evaluation_instant.isoformat(),
        "result": result,
        "summary": summary,
        "active_exception_ids": active_ids,
        "findings": findings,
        "controls": [{"status": status, "severity": "error"}],
    }
'''


if __name__ == "__main__":
    unittest.main()
