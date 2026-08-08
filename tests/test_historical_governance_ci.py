import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/historical-governance.yml"
HISTORICAL_DIR = ROOT / "tests/historical"
ACTIVE_WORKFLOW = ROOT / ".github/workflows/constitutional-audit.yml"


class HistoricalGovernanceWorkflowTests(unittest.TestCase):
    def test_workflow_is_manual_read_only_and_independent(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("name: Historical Governance Audit\n", text)
        self.assertRegex(text, r"(?m)^  workflow_dispatch:$")
        self.assertNotRegex(text, r"(?m)^  (?:push|pull_request):$")
        self.assertRegex(text, r"(?m)^  historical-governance:$")
        permissions = text.split("permissions:\n", 1)[1].split("\njobs:\n", 1)[0]
        self.assertEqual(
            [line.strip() for line in permissions.splitlines() if line.strip()],
            ["contents: read"],
        )

    def test_workflow_requires_complete_history_and_runs_only_historical_tests(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertEqual(re.findall(r"(?m)^\s+fetch-depth:\s*(\d+)\s*$", text), ["0"])
        self.assertEqual(text.count("git rev-parse --is-shallow-repository"), 1)
        self.assertIn("-s tests/historical", text)
        self.assertIn("-p 'historical_*.py'", text)
        self.assertNotIn("python3 -m unittest discover -v", text)
        self.assertNotRegex(text, r"(?m)^\s*(?:run:\s*)?git fetch(?:\s|$)")

    def test_workflow_uses_only_approved_actions_dependencies_and_clean_tree_checks(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertEqual(
            re.findall(r"(?m)^\s+uses:\s+([^\s]+)$", text),
            ["actions/checkout@v4", "actions/setup-python@v5"],
        )
        self.assertEqual(re.findall(r'python-version:\s+"([^"]+)"', text), ["3.13"])
        self.assertEqual(
            re.findall(r"(?m)^\s+run:\s+(python3 -m pip install[^\n]+)$", text),
            ["python3 -m pip install --requirement requirements-dev.txt"],
        )
        self.assertNotIn("${{ secrets.", text)
        self.assertIn("git diff --check", text)
        self.assertIn("git diff --exit-code", text)
        self.assertIn('git status --porcelain=v1 --untracked-files=all', text)
        for forbidden in ("git add", "git commit", "git push", "git reset", "git clean", "gh api", "curl"):
            self.assertNotIn(forbidden, text)

    def test_active_discovery_cannot_execute_historical_modules(self):
        active = ACTIVE_WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("python3 -m unittest discover -v", active)
        historical_modules = sorted(HISTORICAL_DIR.glob("historical_*.py"))
        self.assertTrue(historical_modules)
        self.assertEqual(list(HISTORICAL_DIR.glob("test*.py")), [])
        self.assertNotIn("tests/historical", active)
        self.assertNotIn("historical_*.py", active)


if __name__ == "__main__":
    unittest.main()
