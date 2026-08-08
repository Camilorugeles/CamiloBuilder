import hashlib
import json
import re
import unittest
from datetime import datetime
from pathlib import Path

from capability_introspection import describe_camilobuilder
from constitutional_audit import audit_camilobuilder


ROOT = Path(__file__).resolve().parents[1]
POLICY_PATH = ROOT / "governance/GOVERNANCE.md"
ARCHITECTURE_PATH = ROOT / "governance/architecture/registry.json"
WORK_009_PATH = ROOT / "governance/work-orders/WORK-009.json"
WORK_011_PATH = ROOT / "governance/work-orders/WORK-011.json"
WORK_009_SHA256 = "50edc69a50bcfd6179e68cd4a8fe0021c5e8cfcbd929b725e5f24d3d4c27ac9a"
WORK_011_SHA256 = "60e8d4be6f0d14128d97aff272aa32b24a063f6a30e428abfb83057bd9d3ce12"
EVALUATION_INSTANT = datetime.fromisoformat("2026-08-08T15:46:16+00:00")


class GovernancePolicyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.policy = POLICY_PATH.read_text(encoding="utf-8")
        cls.architecture = json.loads(ARCHITECTURE_PATH.read_text(encoding="utf-8"))

    def test_policy_is_version_two_short_and_subordinate(self):
        self.assertIn("**Versión de la política:** 2.0.0", self.policy)
        self.assertLessEqual(len(self.policy.splitlines()), 320)
        self.assertIn("subordinada a `CONSTITUTION.md`", self.policy)
        self.assertIn("Ante conflicto prevalece la\nConstitución", self.policy)

    def test_defines_exactly_four_change_categories(self):
        categories = re.findall(r"^### 4\.\d (.+)$", self.policy, re.MULTILINE)
        self.assertEqual(categories, [
            "Cambio rutinario", "Cambio gobernado", "Decisión arquitectónica",
            "Cambio incompatible",
        ])
        self.assertIn("No requiere Work Order ni ADR", self.policy)
        self.assertIn("Work Order ligera", self.policy)

    def test_small_team_model_is_honest(self):
        for statement in (
            "no se habla de mayoría", "no se simula independencia",
            "aprobación unipersonal explícita", "ausencia de revisión independiente",
        ):
            self.assertIn(statement, self.policy)
        self.assertNotIn("mayoría simple", self.policy)
        self.assertNotIn("mayoría absoluta", self.policy)

    def test_work_orders_adrs_and_contract_impact_are_minimal(self):
        for field in (
            "identificador y título", "objetivo y alcance", "impacto contractual",
            "riesgos", "reversión", "referencias a evidencia",
        ):
            self.assertIn(field, self.policy)
        for state in ("`proposed`", "`active`", "`done`", "`cancelled`"):
            self.assertIn(state, self.policy)
        for impact in ("`none`", "`compatible`", "`incompatible`", "`deprecation`"):
            self.assertIn(impact, self.policy)
        self.assertIn("No se necesita un Contract Registry", self.policy)

    def test_json_schema_git_and_audit_have_limited_roles(self):
        self.assertIn("consumidor automático", self.policy)
        self.assertIn("No se utiliza para demostrar autoridad", self.policy)
        for source in ("Git es la fuente canónica", "GitHub es la fuente externa", "CI es la fuente"):
            self.assertIn(source, self.policy)
        self.assertRegex(self.policy, r"No certifica legitimidad\s+humana total")
        self.assertIn("obligaciones no verificadas", self.policy)

    def test_architecture_document_changes_without_architecture_relationship_change(self):
        self.assertEqual(self.architecture["schema_version"], 3)
        self.assertEqual(self.architecture["record_version"], "2.0.0")
        self.assertEqual(self.architecture["architecture_version"], "1.3.0")
        self.assertNotIn("constitution_version", self.architecture)
        modules = {item["id"]: item for item in self.architecture["modules"]}
        self.assertIn("contract.governance-policy", modules["module.governance"]["provides_contract_ids"])
        self.assertIn("contract.governance-policy", modules["module.constitutional-audit"]["consumes_contract_ids"])

    def test_introspection_and_audit_remain_coherent(self):
        description = describe_camilobuilder(repository_root=ROOT)
        self.assertEqual(description["constitution_version"]["value"], "2.0.0")
        self.assertEqual(description["architecture_version"]["value"], "1.3.0")
        report = audit_camilobuilder(
            evaluation_instant=EVALUATION_INSTANT,
            repository_root=ROOT,
        )
        self.assertEqual(report["result"], "compliant")

    def test_legacy_work_orders_are_byte_for_byte_intact(self):
        self.assertEqual(hashlib.sha256(WORK_009_PATH.read_bytes()).hexdigest(), WORK_009_SHA256)
        self.assertEqual(hashlib.sha256(WORK_011_PATH.read_bytes()).hexdigest(), WORK_011_SHA256)
        work_011 = json.loads(WORK_011_PATH.read_text(encoding="utf-8"))
        self.assertEqual(
            (work_011["schema_version"], work_011["record_version"], work_011["status"]),
            (2, "0.1.0", "proposed"),
        )

    def test_policy_contains_no_derived_runtime_inventory_or_commit_hash(self):
        for value in ("create-project", "ProjectBuilder", "AgentBuilder", "ServiceBuilder"):
            self.assertNotIn(value, self.policy)
        self.assertIsNone(re.search(r"\b[0-9a-f]{40}\b", self.policy))


if __name__ == "__main__":
    unittest.main()
