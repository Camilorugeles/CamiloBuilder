import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONSTITUTION = ROOT / "governance" / "CONSTITUTION.md"


class ConstitutionDocumentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.document = CONSTITUTION.read_text(encoding="utf-8")

    def test_constitution_exists_and_declares_initial_version(self):
        self.assertTrue(CONSTITUTION.is_file())
        self.assertIn("**Versión constitucional:** 1.0.0", self.document)
        self.assertIn(
            "WORK-009 — Establish CamiloBuilder Constitution", self.document
        )

    def test_contains_all_mandatory_sections(self):
        headings = (
            "## 1. Preámbulo",
            "## 2. Identidad y propósito",
            "## 3. Alcance normativo y descriptivo",
            "## 4. Autoridad y precedencia",
            "## 5. Principios constitucionales",
            "## 6. Responsabilidades",
            "## 7. Límites",
            "## 8. Contratos gobernados",
            "## 9. Compatibilidad",
            "## 10. Versionado",
            "## 11. Work Orders y trazabilidad",
            "## 12. Auditoría",
            "## 13. Conflictos entre código y Constitución",
            "## 14. Enmiendas E0–E3",
            "## 15. Excepciones temporales",
            "## 16. Incumplimiento y remediación",
            "## 17. Entrada en vigor",
            "## 18. Glosario mínimo",
        )
        for heading in headings:
            with self.subTest(heading=heading):
                self.assertIn(heading, self.document)

    def test_contains_the_ten_constitutional_principles(self):
        principles = (
            "Principio de Autoconocimiento",
            "Principio de No Deriva",
            "Principio de Trazabilidad",
            "Principio de Gobernanza de Contratos",
            "Principio de Arquitectura Viva",
            "Principio de No Destrucción",
            "Principio de Mínimo Privilegio",
            "Principio de Fallo Seguro",
            "Principio de Determinismo",
            "Principio de Evolución Incremental",
        )
        for principle in principles:
            with self.subTest(principle=principle):
                self.assertIn(principle, self.document)

    def test_defines_normative_language_and_precedence(self):
        for term in ("DEBE", "NO DEBE", "DEBERÍA", "PUEDE"):
            with self.subTest(term=term):
                self.assertIn(f"**{term}:**", self.document)
        self.assertIn(
            "Esta Constitución es la autoridad normativa superior", self.document
        )
        self.assertIn("1. Constitución vigente.", self.document)

    def test_defines_all_amendment_levels(self):
        for level in (
            "E0 — Editorial",
            "E1 — Clarificación normativa compatible",
            "E2 — Nueva norma compatible",
            "E3 — Enmienda mayor",
        ):
            with self.subTest(level=level):
                self.assertIn(level, self.document)
        self.assertIn("El quórum general es de dos tercios", self.document)

    def test_defines_temporary_exception_rules(self):
        self.assertIn("Una excepción es temporal", self.document)
        self.assertIn("fecha de expiración", self.document)
        self.assertIn("controles compensatorios", self.document)
        self.assertIn("Las excepciones expiran automáticamente", self.document)

    def test_resolves_conflict_in_favor_of_the_constitution(self):
        self.assertIn(
            "La Constitución DEBE prevalecer", self.document
        )
        self.assertIn("La publicación afectada DEBE detenerse", self.document)
        self.assertIn("DEBE abrirse una Work Order de remediación", self.document)


if __name__ == "__main__":
    unittest.main()
