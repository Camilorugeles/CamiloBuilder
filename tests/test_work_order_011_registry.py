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
from capability_introspection.work_orders import discover_work_orders


ROOT = Path(__file__).resolve().parents[1]
WORK_ORDER_PATH = ROOT / "governance/work-orders/WORK-011.json"
SCHEMA_PATH = ROOT / "governance/schemas/v2/work-order.schema.json"
WORK_009_PATH = ROOT / "governance/work-orders/WORK-009.json"
EXPECTED_CREATED_AT = "2026-08-08T16:05:06+02:00"
EXPECTED_CANCELLED_AT = "2026-08-08T18:33:02+02:00"
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

    def test_cancelled_record_validates_with_published_work_order_schema_v2(self):
        validator = Draft202012Validator(
            self.schema,
            format_checker=FormatChecker(),
            registry=Registry(retrieve=lambda uri: self.fail(f"Network retrieval: {uri}")),
        )
        self.assertEqual(list(validator.iter_errors(self.document)), [])

    def test_identity_state_and_real_captured_timestamp_are_exact(self):
        self.assertEqual(self.document["schema_version"], 2)
        self.assertEqual(self.document["id"], "WORK-011")
        self.assertEqual(self.document["record_version"], "0.1.1")
        self.assertEqual(self.document["title"], "Introduce Work Order Schema v3")
        self.assertEqual(self.document["status"], "cancelled")
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
        self.assertEqual(load_json(WORK_009_PATH)["status"], "published")

    def test_cancellation_preserves_empty_implementation_and_adds_one_real_transition(self):
        self.assertEqual(self.document["implementation_commit_ids"], [])
        self.assertEqual(self.document["tests"], [])
        self.assertEqual(self.document["status_history"], [{
            "from": "proposed", "to": "cancelled", "at": EXPECTED_CANCELLED_AT,
        }])
        cancelled_at = datetime.datetime.fromisoformat(EXPECTED_CANCELLED_AT)
        self.assertIsNotNone(cancelled_at.utcoffset())
        self.assertNotIn("registry_closure_commit_id", self.document)

    def test_cancellation_reason_is_grounded_without_reinterpreting_legacy_fields(self):
        reason = (
            "Constitution 2.0 and Governance 2.0 superseded the governance model "
            "that required Work Order schema v3. No functional implementation of "
            "WORK-011 began."
        )
        self.assertIn("Constitution 2.0", reason)
        self.assertIn("Governance 2.0", reason)
        self.assertFalse((ROOT / "governance/schemas/v3/work-order.schema.json").exists())
        self.assertEqual(self.document["implementation_commit_ids"], [])
        self.assertEqual(self.document["contract_change"], "modifies")

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

    def test_directory_discovery_replaces_the_removed_legacy_index(self):
        self.assertFalse((ROOT / "governance/work-orders/index.json").exists())
        self.assertEqual(
            [item["id"] for item in discover_work_orders(ROOT)],
            ["WORK-009", "WORK-010", "WORK-011"],
        )

    def test_work_009_and_historical_schemas_are_byte_for_byte_intact(self):
        self.assertEqual(hashlib.sha256(WORK_009_PATH.read_bytes()).hexdigest(), WORK_009_SHA256)
        self.assertEqual(
            hashlib.sha256((ROOT / "governance/schemas/v1/work-order.schema.json").read_bytes()).hexdigest(),
            V1_SCHEMA_SHA256,
        )
        self.assertEqual(hashlib.sha256(SCHEMA_PATH.read_bytes()).hexdigest(), V2_SCHEMA_SHA256)

    def test_current_repository_remains_technically_verified(self):
        report = audit_camilobuilder(
            repository_root=ROOT,
        )
        self.assertEqual(report["automated_result"], "verified")
        self.assertEqual(report["automated_summary"]["failed"], 0)
        self.assertEqual(report["automated_summary"]["indeterminate"], 0)


if __name__ == "__main__":
    unittest.main()
