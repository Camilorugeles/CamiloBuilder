import json
import re
import unittest
from datetime import datetime
from pathlib import Path

from capability_introspection import describe_camilobuilder
from constitutional_audit import audit_camilobuilder


ROOT = Path(__file__).resolve().parents[1]
POLICY_PATH = ROOT / "governance" / "GOVERNANCE.md"
CONSTITUTION_PATH = ROOT / "governance" / "CONSTITUTION.md"
ARCHITECTURE_PATH = ROOT / "governance" / "architecture" / "registry.json"
WORK_ORDER_PATH = ROOT / "governance" / "work-orders" / "WORK-009.json"
BLOCK_8_COMMIT = "b586e24e680ca4a081b512f48858a247fe77ed2c"
EVALUATION_INSTANT = datetime.fromisoformat("2026-08-07T17:45:00+00:00")


def load_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


class GovernancePolicyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.policy = POLICY_PATH.read_text(encoding="utf-8")
        cls.architecture = load_json(ARCHITECTURE_PATH)
        cls.work_order = load_json(WORK_ORDER_PATH)

    def test_policy_exists_and_separates_normative_and_descriptive_content(self):
        self.assertTrue(POLICY_PATH.is_file())
        self.assertIn("## 3. Contenido normativo y descriptivo", self.policy)
        self.assertIn("**contenido normativo**", self.policy)
        self.assertIn("**contenido descriptivo**", self.policy)
        for term in ("DEBE", "NO DEBE", "DEBERÍA", "PUEDE"):
            self.assertIn(term, self.policy)

    def test_required_sections_are_present(self):
        headings = [
            "Propósito", "Alcance", "Autoridad y precedencia", "Roles",
            "Separación de responsabilidades", "Modelo de versiones",
            "Clasificación contractual", "Política SemVer de releases",
            "Estabilidad", "Gobierno de contratos", "Deprecaciones y retirada",
            "Migraciones", "Ciclo de Work Orders", "Aprobaciones", "Excepciones",
            "Releases", "Publicación", "Evidencia y trazabilidad",
            "Auditoría y aplicación", "Conflictos y remediación",
            "Modificación de esta política", "Entrada en vigor y glosario",
        ]
        for heading in headings:
            with self.subTest(heading=heading):
                self.assertRegex(self.policy, rf"(?m)^## \d+\. {re.escape(heading)}$")

    def test_policy_is_explicitly_subordinate_to_constitution(self):
        self.assertTrue(CONSTITUTION_PATH.is_file())
        required = [
            "Esta política está subordinada a `governance/CONSTITUTION.md`.",
            "`GOVERNANCE.md` NO modifica la Constitución.",
            "`GOVERNANCE.md` NO DEBE reducir garantías constitucionales.",
            "Ante cualquier conflicto, DEBE prevalecer `CONSTITUTION.md`.",
            "bloquear la publicación y la release",
        ]
        for statement in required:
            self.assertIn(statement, self.policy)

    def test_roles_and_version_families_are_complete(self):
        values = [
            "Arquitecto Responsable", "Maintainer", "Revisor independiente",
            "Autor de Work Order", "Aprobador", "Responsable de release",
            "constitution_version", "architecture_version", "record_version",
            "schema_version", "contract_version", "release_version",
        ]
        for value in values:
            with self.subTest(value=value):
                self.assertIn(value, self.policy)
        self.assertIn("Un cambio en una familia NO DEBE", self.policy)

    def test_semver_stability_deprecation_and_migration_are_governed(self):
        for level in ("PATCH", "MINOR", "MAJOR"):
            self.assertRegex(self.policy, rf"(?m)^### 9\.\d {level}$")
        for state in ("experimental", "provisional", "stable", "deprecated", "removed"):
            self.assertIn(f"`{state}`", self.policy)
        requirements = (
            "alternativa recomendada", "ventana de compatibilidad",
            "pruebas del comportamiento antiguo y nuevo", "procedimiento de migración",
            "explícita", "idempotente", "probada con fixtures",
            "reversible o respaldada", "separada de consultas",
        )
        for requirement in requirements:
            self.assertIn(requirement, self.policy)
        self.assertIn("NO DEBE degradarse", self.policy)

    def test_work_order_v2_limitation_is_explicit_and_non_retroactive(self):
        section = self.policy.split(
            "### 8.1 Limitación gobernada de Work Order schema v2", 1
        )[1].split("## 9.", 1)[0]
        self.assertIn("`modifies compatible`", self.policy)
        self.assertIn("`modifies incompatible`", self.policy)
        self.assertIn("solo representa el valor `modifies`", section)
        self.assertIn("ninguna **nueva** Work Order", section)
        self.assertIn("PUEDE pasar a\n`approved`", section)
        self.assertIn("NO DEBEN reinterpretarse\nretroactivamente", section)
        self.assertIn("versión futura del schema de Work Orders", section)
        self.assertIn("La versión v2 NO DEBE modificarse", section)
        self.assertIn("NO es\nuna excepción implícita", section)

    def test_work_orders_releases_and_publication_are_unambiguous(self):
        states = (
            "`proposed`", "`approved`", "`in_progress`", "`completed`",
            "`published`", "`reverted`", "`cancelled`",
        )
        for state in states:
            self.assertIn(state, self.policy)
        self.assertIn("`completed` NO equivale a `published`", self.policy)
        self.assertIn("`published` NO equivale a una release", self.policy)
        for gate in (
            "la CI constitucional pasa", "el árbol de trabajo está limpio",
            "las Work Orders incluidas están `published`",
            "`release_version` está determinada", "existe rollback conocido",
        ):
            self.assertIn(gate, self.policy)
        self.assertIn("Un `push` NO convierte automáticamente", self.policy)

    def test_governance_policy_is_the_single_approved_contract_change(self):
        contracts = self.architecture["contract_ids"]
        self.assertEqual(contracts.count("contract.governance-policy"), 1)
        modules = {module["id"]: module for module in self.architecture["modules"]}
        self.assertEqual(self.architecture["record_version"], "1.3.0")
        self.assertEqual(self.architecture["architecture_version"], "1.3.0")
        self.assertEqual(self.architecture["constitution_version"], "1.0.0")
        self.assertIn(
            "contract.governance-policy",
            modules["module.governance"]["provides_contract_ids"],
        )
        self.assertIn(
            "contract.governance-policy",
            modules["module.constitutional-audit"]["consumes_contract_ids"],
        )

    def test_introspection_and_audit_remain_coherent_and_compliant(self):
        description = describe_camilobuilder(repository_root=ROOT)
        self.assertEqual(description["architecture_version"]["value"], "1.3.0")
        self.assertIn("contract.governance-policy", description["contracts"]["items"])
        report = audit_camilobuilder(
            evaluation_instant=EVALUATION_INSTANT,
            repository_root=ROOT,
        )
        self.assertEqual(report["result"], "compliant")

    def test_work_order_traceability_has_no_self_reference(self):
        commits = self.work_order["implementation_commit_ids"]
        self.assertEqual(commits[-1], BLOCK_8_COMMIT)
        self.assertEqual(commits.count(BLOCK_8_COMMIT), 1)
        self.assertEqual(self.work_order["status"], "in_progress")
        self.assertNotIn("registry_closure_commit_id", self.work_order)

    def test_policy_has_no_derived_inventories_or_concrete_records(self):
        forbidden = (
            "create-project", "create-agent", "create-department", "create-service",
            "ProjectBuilder", "AgentBuilder", "DepartmentBuilder", "ServiceBuilder",
        )
        for value in forbidden:
            self.assertNotIn(value, self.policy)
        self.assertIsNone(re.search(r"\b[0-9a-f]{40}\b", self.policy))
        self.assertNotIn("EXCEPTION-", self.policy)


if __name__ == "__main__":
    unittest.main()
