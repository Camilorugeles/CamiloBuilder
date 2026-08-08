import datetime
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "governance/MAINTAINERS.md"


class MaintainersDocumentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.document = PATH.read_text(encoding="utf-8")

    def test_records_the_approved_human_declaration(self):
        for value in (
            "Camilo Rugeles", "@Camilorugeles", "Maintainers activos:** uno",
            "responsabilidad arquitectónica principal", "no existe actualmente",
        ):
            self.assertIn(value, self.document)

    def test_confirmation_date_is_real_rfc3339_with_timezone(self):
        marker = "**Última confirmación:** "
        line = next(line for line in self.document.splitlines() if line.startswith(marker))
        value = line.removeprefix(marker).strip()
        parsed = datetime.datetime.fromisoformat(value)
        self.assertIsNotNone(parsed.utcoffset())
        self.assertEqual(value, "2026-08-08T17:46:16+02:00")

    def test_declares_material_enforcement_and_documentary_limits(self):
        for value in (
            "GitHub", "enforcement material externo", "no crea identidad",
            "conservar su historia en Git",
        ):
            self.assertIn(value, self.document)
        self.assertRegex(
            self.document,
            r"no\s+demuestra criptográficamente autoridad o legitimidad",
        )


if __name__ == "__main__":
    unittest.main()
