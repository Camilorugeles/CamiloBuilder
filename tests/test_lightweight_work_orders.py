import hashlib
import json
import shutil
import socket
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from capability_introspection import describe_camilobuilder
from capability_introspection.work_orders import (
    WorkOrderSourceError,
    discover_work_orders,
)


ROOT = Path(__file__).resolve().parents[1]
WORK_ORDERS = ROOT / "governance/work-orders"
WORK_009_SHA256 = "50edc69a50bcfd6179e68cd4a8fe0021c5e8cfcbd929b725e5f24d3d4c27ac9a"
V1_SCHEMA_SHA256 = "6e3102a7cd53b7db1d421889015aa2f978e114256edeefbb25500fec8381281d"
V2_SCHEMA_SHA256 = "3787ea3b82e11ce19fba6dea453f61a1602b28028bcd42296b51f334f474f3d6"
WORKFLOW_SHA256 = "6b004aca30c6bb78ff92b1b974d4d4b9cf57754b9cdbaf34ef7b26d54c117746"
FUNCTIONAL_COMMIT = "4a594899bc7c3fdd06f24eed388d06d341656a71"


def load_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path, document):
    path.write_text(
        json.dumps(document, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def tree_digest(path):
    digest = hashlib.sha256()
    for item in sorted(candidate for candidate in path.rglob("*") if candidate.is_file()):
        digest.update(item.relative_to(path).as_posix().encode("utf-8"))
        digest.update(item.read_bytes())
    return digest.hexdigest()


class LightweightWorkOrderTests(unittest.TestCase):
    def setUp(self):
        self.work_010 = load_json(WORK_ORDERS / "WORK-010.json")

    def _copy_governance(self, root):
        shutil.copytree(ROOT / "governance", root / "governance")

    def _mutated_root(self, mutation, *, filename="WORK-010.json"):
        temporary = tempfile.TemporaryDirectory()
        root = Path(temporary.name)
        self._copy_governance(root)
        path = root / "governance/work-orders" / filename
        document = load_json(path)
        mutation(document)
        write_json(path, document)
        return temporary, root

    def test_work_010_is_the_exact_lightweight_historical_record(self):
        self.assertEqual(self.work_010, {
            "format": "camilobuilder.work-order",
            "format_version": 1,
            "id": "WORK-010",
            "title": "Make constitutional CI history-aware",
            "objective": "Make CI provide the complete Git history required by existing historical verification controls.",
            "status": "done",
            "historical_record": True,
            "scope": ["Constitutional Audit checkout history availability"],
            "contract_impact": {"classification": "none", "surfaces": []},
            "risks": [
                "Complete checkout cost may grow with repository history",
                "Historical verification depends on canonical Git history remaining available",
            ],
            "reversal": "Revert commit:4a594899bc7c3fdd06f24eed388d06d341656a71 from a branch based on published main, then run the complete suite, compileall, git diff --check, and governance verification. Restoring shallow checkout is invalid unless an equivalent history-aware solution is provided.",
            "evidence_refs": [
                "commit:4a594899bc7c3fdd06f24eed388d06d341656a71",
                "github-actions-run:31257462852",
            ],
            "dependencies": ["WORK-009"],
            "decision_refs": [],
            "notes": [
                "Implemented and published before this lightweight record existed",
                "No proposal, approval, implementation, completion, or publication timestamps are reconstructed",
                "No retrospective approvals are asserted; Git and GitHub Actions retain the durable evidence",
            ],
        })
        for forbidden in (
            "created_at", "approved_at", "completed_at", "status_history",
            "implementation_commit_ids", "registry_closure_commit_id", "approval_ids",
        ):
            self.assertNotIn(forbidden, self.work_010)

    def test_work_010_evidence_commit_exists_locally(self):
        completed = subprocess.run(
            ["git", "cat-file", "-e", f"{FUNCTIONAL_COMMIT}^{{commit}}"],
            cwd=ROOT,
            check=False,
            capture_output=True,
        )
        self.assertEqual(completed.returncode, 0)

    def test_discovery_combines_legacy_and_lightweight_records_in_id_order(self):
        records = discover_work_orders(ROOT)
        self.assertEqual(
            [(item["id"], item["model"], item["status"]) for item in records],
            [
                ("WORK-009", "legacy", "published"),
                ("WORK-010", "lightweight", "done"),
                ("WORK-011", "legacy", "cancelled"),
            ],
        )

    def test_legacy_index_is_not_the_discovery_source(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self._copy_governance(root)
            (root / "governance/work-orders/index.json").write_text("{", encoding="utf-8")
            self.assertEqual(
                [item["id"] for item in discover_work_orders(root)],
                ["WORK-009", "WORK-010", "WORK-011"],
            )
        index = load_json(WORK_ORDERS / "index.json")
        self.assertEqual([item["id"] for item in index], ["WORK-009", "WORK-011"])
        self.assertEqual(index[1]["status"], "cancelled")

    def test_introspection_uses_directory_and_preserves_public_summary(self):
        block = describe_camilobuilder(repository_root=ROOT)["work_orders"]
        self.assertEqual(block["source"], "governance/work-orders/")
        self.assertEqual([item["id"] for item in block["items"]], [
            "WORK-009", "WORK-010", "WORK-011",
        ])
        self.assertTrue(all(set(item) == {"id", "title", "status", "path"} for item in block["items"]))

    def test_selector_rejects_corruption_ambiguity_mismatch_and_unknown_versions(self):
        cases = {
            "both-discriminators": lambda value: value.update(schema_version=2),
            "filename-id-mismatch": lambda value: value.update(id="WORK-999"),
            "unknown-format": lambda value: value.update(format_version=99),
        }
        for name, mutation in cases.items():
            with self.subTest(case=name):
                temporary, root = self._mutated_root(mutation)
                with temporary, self.assertRaises(WorkOrderSourceError):
                    discover_work_orders(root)

        temporary, root = self._mutated_root(
            lambda value: value.update(schema_version=99), filename="WORK-011.json"
        )
        with temporary, self.assertRaises(WorkOrderSourceError):
            discover_work_orders(root)

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self._copy_governance(root)
            (root / "governance/work-orders/WORK-010.json").write_text("{", encoding="utf-8")
            with self.assertRaises(WorkOrderSourceError):
                discover_work_orders(root)

    def test_validation_rejects_duplicate_ids_arrays_invalid_evidence_and_contract_impact(self):
        cases = {
            "duplicate-dependency": lambda value: value.update(dependencies=["WORK-009", "WORK-009"]),
            "invalid-evidence": lambda value: value.update(evidence_refs=["commit:short"]),
            "none-with-surface": lambda value: value.update(contract_impact={
                "classification": "none",
                "surfaces": [{"surface": "cli", "impact": "compatible"}],
            }),
            "aggregate-mismatch": lambda value: value.update(contract_impact={
                "classification": "compatible",
                "surfaces": [{"surface": "cli", "impact": "incompatible"}],
            }),
        }
        for name, mutation in cases.items():
            with self.subTest(case=name):
                temporary, root = self._mutated_root(mutation)
                with temporary, self.assertRaises(WorkOrderSourceError):
                    discover_work_orders(root)

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self._copy_governance(root)
            duplicate = load_json(root / "governance/work-orders/WORK-010.json")
            write_json(root / "governance/work-orders/WORK-012.json", duplicate)
            with self.assertRaises(WorkOrderSourceError):
                discover_work_orders(root)

    def test_discovery_is_deterministic_offline_clock_independent_and_read_only(self):
        before = tree_digest(ROOT / "governance")
        with mock.patch.object(socket, "socket", side_effect=AssertionError("network forbidden")), \
             mock.patch("time.time", side_effect=AssertionError("clock forbidden")):
            first = discover_work_orders(ROOT)
            second = discover_work_orders(ROOT)
        self.assertEqual(first, second)
        self.assertEqual(before, tree_digest(ROOT / "governance"))

    def test_legacy_artifacts_and_ci_workflow_remain_intact(self):
        self.assertEqual(hashlib.sha256((WORK_ORDERS / "WORK-009.json").read_bytes()).hexdigest(), WORK_009_SHA256)
        self.assertEqual(
            hashlib.sha256((ROOT / "governance/schemas/v1/work-order.schema.json").read_bytes()).hexdigest(),
            V1_SCHEMA_SHA256,
        )
        self.assertEqual(
            hashlib.sha256((ROOT / "governance/schemas/v2/work-order.schema.json").read_bytes()).hexdigest(),
            V2_SCHEMA_SHA256,
        )
        self.assertFalse((ROOT / "governance/schemas/v3/work-order.schema.json").exists())
        self.assertEqual(
            hashlib.sha256((ROOT / ".github/workflows/constitutional-audit.yml").read_bytes()).hexdigest(),
            WORKFLOW_SHA256,
        )


if __name__ == "__main__":
    unittest.main()
