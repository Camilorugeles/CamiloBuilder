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
PUBLISHED_POLICY_COMMIT = "a1e6e842cfdf653452c72a0de9ec7f14aa8aecdc"
DIAGNOSTIC_FIELDS = {
    "automated_result",
    "automated_summary",
    "declared_exceptions",
    "evaluation_instant",
    "findings",
    "manual_assertions",
    "unverified_obligations",
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

    def test_checkout_uses_default_shallow_history_without_historical_fetches(self):
        text = workflow_text()
        expected = '''      - name: Checkout repository
        uses: actions/checkout@v4
'''
        self.assertIn(expected, text)
        self.assertNotIn("fetch-depth", text)
        self.assertNotIn("git rev-parse --is-shallow-repository", text)
        self.assertNotIn("Verify complete Git history", text)
        self.assertNotRegex(text, r"(?m)^\s*(?:run:\s*)?git fetch(?:\s|$)")
        self.assertNotIn("tests/historical", text)
        self.assertNotIn("historical_*.py", text)

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
        self.assertEqual(text.count("python3 -m unittest discover -v"), 1)
        self.assertIn("python3 -m compileall -q", text)
        for target in (
            "builder.py", "builder_cli.py", "builders", "template_system",
            "capability_introspection", "constitutional_audit", "tests",
        ):
            self.assertIn(target, text)
        self.assertNotIn("Validate governance schemas", text)
        self.assertNotIn("tests.test_governance_schemas", text)
        self.assertNotIn("tests.test_constitutional_audit.AuditReportSchemaTests", text)
        self.assertIn("- name: Run governance verification", text)
        self.assertNotIn("- name: Run constitutional audit", text)
        self.assertIn("audit_camilobuilder(evaluation_instant=instant)", text)

    def test_checks_repository_state_once_at_the_end_without_repair(self):
        text = workflow_text()
        self.assertNotIn("Verify initial clean tree", text)
        self.assertNotIn("- name: Check whitespace", text)
        final = text.split("      - name: Verify final repository state\n", 1)[1]
        self.assertEqual(final.count("git diff --check"), 1)
        self.assertEqual(final.count("git diff --exit-code"), 1)
        self.assertEqual(
            final.count('test -z "$(git status --porcelain=v1 --untracked-files=all)"'),
            1,
        )
        self.assertEqual(text.count("git diff --check"), 1)
        self.assertEqual(text.count("git diff --exit-code"), 1)
        self.assertEqual(
            text.count('test -z "$(git status --porcelain=v1 --untracked-files=all)"'),
            1,
        )
        for forbidden in (
            "git add", "git commit", "git push", "git reset", "git checkout --",
            "git clean", "gh api", "gh run", "curl api.github.com",
        ):
            self.assertNotIn(forbidden, text)

    def test_workflow_has_exactly_the_eight_active_operational_steps(self):
        names = re.findall(r"(?m)^      - name: (.+)$", workflow_text())
        self.assertEqual(names, [
            "Checkout repository",
            "Set up Python",
            "Install development dependencies",
            "Capture CI evaluation instant",
            "Run active test suite",
            "Compile Python sources",
            "Run governance verification",
            "Verify final repository state",
        ])

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
        self.assertEqual(diagnostic["automated_result"], "verified")
        self.assertTrue(diagnostic["manual_assertions"])
        self.assertTrue(diagnostic["unverified_obligations"])
        self.assertNotIn(str(ROOT), first.stdout)

    def test_result_policy_fails_safe_and_conditions_exceptions(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            package = root / "constitutional_audit"
            package.mkdir()
            package.joinpath("__init__.py").write_text(self._fake_audit_module(), encoding="utf-8")
            expected = {
                "verified": 0,
                "verified_with_declared_exceptions": 0,
                "exception_without_active_id": 1,
                "exception_invalid_link": 1,
                "exception_expired": 1,
                "material_failure": 1,
                "failed": 1,
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

    def test_work_order_traceability_includes_the_published_policy_commit(self):
        document = json.loads(WORK_ORDER_PATH.read_text(encoding="utf-8"))
        self.assertEqual(document["status"], "published")
        self.assertEqual(document["implementation_commit_ids"][-1], PUBLISHED_POLICY_COMMIT)
        self.assertEqual(document["implementation_commit_ids"].count(PUBLISHED_POLICY_COMMIT), 1)
        self.assertEqual(
            document["registry_closure_commit_id"],
            "759360f02622905cba971695472ef10de4a24aa6",
        )

    @staticmethod
    def _fake_audit_module():
        return '''import os

class AuditInputError(ValueError):
    pass

def audit_camilobuilder(*, evaluation_instant, repository_root=None):
    case = os.environ["AUDIT_FAKE_CASE"]
    result = case if case in {"verified", "verified_with_declared_exceptions", "failed", "indeterminate"} else "verified_with_declared_exceptions"
    declared = [{"id": "EXCEPTION-001", "source_id": "governance/exceptions/EXCEPTION-001.json", "status": "active", "applied_finding_ids": ["finding.001"]}] if result == "verified_with_declared_exceptions" else []
    status = "passed"
    findings = []
    if result == "verified_with_declared_exceptions":
        status = "excepted"
        findings = [{"id": "finding.001", "outcome": "excepted", "severity": "error", "exception_id": "EXCEPTION-001", "code": "synthetic-exception"}]
    elif result == "failed":
        status = "failed"
        findings = [{"id": "finding.001", "outcome": "failed", "severity": "error", "exception_id": None, "code": "synthetic-failure"}]
    elif result == "indeterminate":
        status = "indeterminate"
        findings = [{"id": "finding.001", "outcome": "indeterminate", "severity": "error", "exception_id": None, "code": "synthetic-indeterminate"}]
    if case == "exception_without_active_id":
        declared = []
    if case == "exception_invalid_link":
        findings[0]["exception_id"] = "EXCEPTION-999"
    if case == "exception_expired":
        findings[0]["code"] = "expired-exception"
    if case == "material_failure":
        findings.append({"id": "finding.002", "outcome": "failed", "severity": "critical", "exception_id": None, "code": "synthetic-failure"})
    summary = {"passed": status == "passed", "failed": status == "failed", "excepted": status == "excepted", "indeterminate": status == "indeterminate"}
    if case == "contradictory_summary":
        summary["passed"] = 99
    return {
        "evaluation_instant": evaluation_instant.isoformat(),
        "automated_result": result,
        "automated_summary": summary,
        "declared_exceptions": declared,
        "findings": findings,
        "automated_controls": [{"status": status, "severity": "error"}],
        "manual_assertions": [{"id": "assertion.synthetic", "verification_scope": "presence_only"}],
        "unverified_obligations": [{"id": "obligation.synthetic"}],
    }
'''


if __name__ == "__main__":
    unittest.main()
