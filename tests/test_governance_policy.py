import hashlib
import json
import re
import unittest
from pathlib import Path

from capability_introspection import describe_camilobuilder
from constitutional_audit import audit_camilobuilder


ROOT = Path(__file__).resolve().parents[1]
POLICY_PATH = ROOT / "governance/GOVERNANCE.md"
ARCHITECTURE_PATH = ROOT / "governance/architecture/registry.json"
WORK_009_PATH = ROOT / "governance/work-orders/WORK-009.json"
WORK_010_PATH = ROOT / "governance/work-orders/WORK-010.json"
WORK_011_PATH = ROOT / "governance/work-orders/WORK-011.json"
WORK_009_SHA256 = "50edc69a50bcfd6179e68cd4a8fe0021c5e8cfcbd929b725e5f24d3d4c27ac9a"


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
        for category in ("`automated_controls`", "`manual_assertions`", "`unverified_obligations`"):
            self.assertIn(category, self.policy)
        self.assertIn("resultado `verified` significa únicamente", self.policy)
        self.assertNotIn("El modelo futuro separará", self.policy)
        self.assertNotIn("La nomenclatura `compliant`", self.policy)

    def test_policy_describes_the_active_exception_boundary(self):
        self.assertIn("no dispone actualmente de un mecanismo ejecutable activo", self.policy)
        self.assertIn("la verificación activa no admite excepciones", self.policy)
        self.assertIn("cambio gobernado\nexplícito", self.policy)
        self.assertNotIn("No se crea EXCEPTION-001", self.policy)

    def test_architecture_document_changes_without_architecture_relationship_change(self):
        self.assertEqual(self.architecture["schema_version"], 3)
        self.assertEqual(self.architecture["record_version"], "2.0.1")
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
            repository_root=ROOT,
        )
        self.assertEqual(report["automated_result"], "verified")

    def test_work_009_is_intact_and_work_011_remains_a_legacy_record(self):
        self.assertEqual(hashlib.sha256(WORK_009_PATH.read_bytes()).hexdigest(), WORK_009_SHA256)
        work_011 = json.loads(WORK_011_PATH.read_text(encoding="utf-8"))
        self.assertEqual(
            (work_011["schema_version"], work_011["record_version"], work_011["status"]),
            (2, "0.1.1", "cancelled"),
        )

    def test_policy_describes_current_work_order_states(self):
        work_010 = json.loads(WORK_010_PATH.read_text(encoding="utf-8"))
        work_011 = json.loads(WORK_011_PATH.read_text(encoding="utf-8"))
        self.assertEqual(work_010["status"], "done")
        self.assertEqual(work_011["status"], "cancelled")
        self.assertIn("WORK-010 existe", self.policy)
        self.assertIn("estado `done`", self.policy)
        self.assertIn("WORK-011 permanece", self.policy)
        self.assertIn("estado `cancelled`", self.policy)
        self.assertNotIn("WORK-010 podrá", self.policy)
        self.assertNotIn("permanece `proposed`", self.policy)

    def test_policy_contains_no_derived_runtime_inventory_or_commit_hash(self):
        for value in ("create-project", "ProjectBuilder", "AgentBuilder", "ServiceBuilder"):
            self.assertNotIn(value, self.policy)
        self.assertIsNone(re.search(r"\b[0-9a-f]{40}\b", self.policy))


if __name__ == "__main__":
    unittest.main()
