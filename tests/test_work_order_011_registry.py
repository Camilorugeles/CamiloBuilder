import datetime
import hashlib
import json
import unittest
from pathlib import Path

try:
    from jsonschema import Draft202012Validator, FormatChecker
    from referencing import Registry
except ModuleNotFoundError as error:
    raise RuntimeError(
        "Missing development dependency; run: "
        "python3 -m pip install -r requirements-dev.txt"
    ) from error

from constitutional_audit import audit_camilobuilder


ROOT = Path(__file__).resolve().parents[1]
WORK_ORDER_PATH = ROOT / "governance/work-orders/WORK-011.json"
INDEX_PATH = ROOT / "governance/work-orders/index.json"
SCHEMA_PATH = ROOT / "governance/schemas/v2/work-order.schema.json"
WORK_009_PATH = ROOT / "governance/work-orders/WORK-009.json"
EXPECTED_CREATED_AT = "2026-08-08T16:05:06+02:00"
WORK_009_SHA256 = "50edc69a50bcfd6179e68cd4a8fe0021c5e8cfcbd929b725e5f24d3d4c27ac9a"
V1_SCHEMA_SHA256 = "6e3102a7cd53b7db1d421889015aa2f978e114256edeefbb25500fec8381281d"
V2_SCHEMA_SHA256 = "3787ea3b82e11ce19fba6dea453f61a1602b28028bcd42296b51f334f474f3d6"


def load_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


class WorkOrder011RegistryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.document = load_json(WORK_ORDER_PATH)
        cls.schema = load_json(SCHEMA_PATH)
        cls.index = load_json(INDEX_PATH)

    def test_proposal_validates_with_published_work_order_schema_v2(self):
        validator = Draft202012Validator(
            self.schema,
            format_checker=FormatChecker(),
            registry=Registry(retrieve=lambda uri: self.fail(f"Network retrieval: {uri}")),
        )
        self.assertEqual(list(validator.iter_errors(self.document)), [])

    def test_identity_state_and_real_captured_timestamp_are_exact(self):
        self.assertEqual(self.document["schema_version"], 2)
        self.assertEqual(self.document["id"], "WORK-011")
        self.assertEqual(self.document["record_version"], "0.1.0")
        self.assertEqual(self.document["title"], "Introduce Work Order Schema v3")
        self.assertEqual(self.document["status"], "proposed")
        self.assertEqual(self.document["created_at"], EXPECTED_CREATED_AT)
        captured = datetime.datetime.fromisoformat(self.document["created_at"])
        self.assertIsNotNone(captured.utcoffset())
        self.assertEqual(self.document["constitution_version"], "1.0.0")

    def test_v2_modifies_remains_ambiguous_and_contract_scope_is_exact(self):
        self.assertEqual(self.document["contract_change"], "modifies")
        self.assertNotIn("modifies_compatible", self.document["contract_change"])
        self.assertNotIn("modifies_incompatible", self.document["contract_change"])
        self.assertEqual(self.document["affected_contract_ids"], [
            "contract.capability-introspection",
            "contract.constitutional-audit",
            "contract.governance-policy",
            "contract.governance-schema",
        ])

    def test_components_dependency_and_empty_capabilities_are_exact(self):
        self.assertEqual(self.document["affected_component_ids"], [
            "module.capability-introspection",
            "module.constitutional-audit",
            "module.governance",
        ])
        self.assertEqual(self.document["affected_capability_ids"], [])
        self.assertEqual(self.document["dependency_ids"], ["WORK-009"])
        work_009_entry = next(item for item in self.index if item["id"] == "WORK-009")
        self.assertEqual(work_009_entry["status"], "published")

    def test_proposal_contains_no_implementation_or_reconstructed_history(self):
        self.assertEqual(self.document["implementation_commit_ids"], [])
        self.assertEqual(self.document["tests"], [])
        self.assertEqual(self.document["status_history"], [])
        self.assertNotIn("registry_closure_commit_id", self.document)

    def test_risks_are_exact_and_do_not_mix_debt(self):
        self.assertEqual(self.document["risks"], [
            "Incorrect sequencing could make v3 Work Orders unreadable by introspection or constitutional audit",
            "Retrospective history support could be abused if not constrained by durable evidence",
            "Work Order schema v2 cannot represent compatibility per affected contract",
        ])
        self.assertNotIn("debt", " ".join(self.document["risks"]).lower())

    def test_reversal_is_concrete_and_limited_to_the_proposal(self):
        reversal = self.document["reversal"]
        for phrase in (
            "git revert", "restores the prior work-order index", "complete suite",
            "compileall", "git diff --check", "constitutional audit",
            "Do not modify WORK-009 or runtime", "do not rewrite Git history",
        ):
            self.assertIn(phrase, reversal)

    def test_index_is_ordered_closed_and_coherent(self):
        self.assertEqual([item["id"] for item in self.index], ["WORK-009", "WORK-011"])
        for item in self.index:
            self.assertEqual(set(item), {"id", "title", "status", "path"})
            document = load_json(ROOT / item["path"])
            self.assertEqual(
                {key: document[key] for key in ("id", "title", "status")},
                {key: item[key] for key in ("id", "title", "status")},
            )

    def test_work_009_and_historical_schemas_are_byte_for_byte_intact(self):
        self.assertEqual(hashlib.sha256(WORK_009_PATH.read_bytes()).hexdigest(), WORK_009_SHA256)
        self.assertEqual(
            hashlib.sha256((ROOT / "governance/schemas/v1/work-order.schema.json").read_bytes()).hexdigest(),
            V1_SCHEMA_SHA256,
        )
        self.assertEqual(hashlib.sha256(SCHEMA_PATH.read_bytes()).hexdigest(), V2_SCHEMA_SHA256)

    def test_current_repository_remains_constitutionally_compliant(self):
        report = audit_camilobuilder(
            evaluation_instant=datetime.datetime.fromisoformat("2026-08-08T14:05:06+00:00"),
            repository_root=ROOT,
        )
        self.assertEqual(report["result"], "compliant")
        self.assertEqual(report["summary"]["failed"], 0)
        self.assertEqual(report["summary"]["indeterminate"], 0)


if __name__ == "__main__":
    unittest.main()
