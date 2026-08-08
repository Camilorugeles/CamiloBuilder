import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONSTITUTION = ROOT / "governance/CONSTITUTION.md"


class ConstitutionDocumentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.document = CONSTITUTION.read_text(encoding="utf-8")

    def test_declares_version_two_and_explicit_reconstitution(self):
        self.assertIn("**Versión constitucional:** 2.0.0", self.document)
        for statement in (
            "defecto de bootstrap", "sobreespecificaba", "supersede explícitamente",
            "no finge continuidad procedimental perfecta", "no reconstruye, altera ni reinterpreta",
        ):
            self.assertIn(statement, self.document)

    def test_is_brief_and_contains_the_nine_governed_principles(self):
        self.assertLessEqual(len(self.document.splitlines()), 260)
        principles = (
            "No Destrucción", "Fallo Seguro y Acceso Mínimo", "Determinismo",
            "Compatibilidad Explícita", "Trazabilidad", "Reversibilidad",
            "Evolución Incremental", "No Deriva y Autoconocimiento",
            "Simplicidad Arquitectónica",
        )
        self.assertEqual(self.document.count("### 5."), 9)
        for principle in principles:
            self.assertIn(principle, self.document)

    def test_recognizes_external_authority_and_limits_machine_verification(self):
        for statement in (
            "autoridad humana y material no es creada por JSON",
            "GitHub", "NO DEBE presentar registros internos como prueba criptográfica",
            "no crea una Root of Trust interna, un IAM ni un Approval Registry",
        ):
            self.assertIn(statement, self.document)

    def test_separates_constitution_governance_and_metagovernance(self):
        self.assertIn("Constitución gobierna garantías, invariantes, límites", self.document)
        self.assertIn("`GOVERNANCE.md` gobierna procesos operativos", self.document)
        self.assertIn("no requiere\nautomáticamente una Work Order", self.document)
        self.assertIn("mecanismos operativos de governance PUEDEN evolucionar", self.document)

    def test_contains_no_concrete_operational_formats(self):
        forbidden = (
            "schema_version", "status_history", "implementation_commit_ids",
            "registry_closure_commit_id", "argparse", "ProjectBuilder",
            "actions/checkout", "fetch-depth",
        )
        for value in forbidden:
            self.assertNotIn(value, self.document)
        self.assertIsNone(re.search(r"\b[0-9a-f]{40}\b", self.document))

    def test_preserves_legacy_without_reinterpretation(self):
        for value in (
            "WORK-009", "WORK-011", "schemas v1/v2", "No existe migración implícita",
        ):
            self.assertIn(value, self.document)
        self.assertRegex(
            self.document,
            r"no obligatorio como modelo\s+para nuevos cambios",
        )


if __name__ == "__main__":
    unittest.main()
