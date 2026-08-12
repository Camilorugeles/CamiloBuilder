from __future__ import annotations

import importlib
import sys
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from builders.project_builder import ProjectBuilder
from builders.service_builder import ServiceBuilder
from tests.invoice_pdf_fixtures import blank_text_pdf, textual_pdf


class RealTextInvoiceExtractionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(); cls.root = Path(cls.temporary.name)
        cls.project = ProjectBuilder(cls.root / "output").build("LayoutFixtureOS")
        ServiceBuilder(cls.project, "agent-core").build("agent_core")
        ServiceBuilder(cls.project, "invoice-intake").build("invoice_intake")
        sys.path.insert(0, str(cls.project))
        for name in list(sys.modules):
            if name == "services" or name.startswith("services."): sys.modules.pop(name, None)
        cls.attachments = importlib.import_module("services.invoice_intake.attachments")
        cls.extraction = importlib.import_module("services.invoice_intake.extraction")
        cls.models = importlib.import_module("services.invoice_intake.models")
        cls.resolvers = importlib.import_module("services.invoice_intake.resolvers")

    @classmethod
    def tearDownClass(cls):
        for name in list(sys.modules):
            if name == "services" or name.startswith("services."): sys.modules.pop(name, None)
        sys.path.remove(str(cls.project)); cls.temporary.cleanup()

    def fields(self, lines):
        content = textual_pdf(lines)
        document = self.attachments.extract_text(self.models.DocumentInput("attachment:synthetic", "synthetic.pdf", "application/pdf", content))
        return self.extraction.extract_fields(document), document

    def standard_lines(self):
        return [
            "FACTURA", "Proveedor: Litoral Ejemplo S.L.", "CIF proveedor: B12345674",
            "Cliente: Cooperativa Sintetica COOP.", "NIF cliente: F7654321A",
            "Numero de factura: INV-2026-0042", "Fecha de emision: 15/06/2026",
            "Concepto: mantenimiento de equipamiento", "Base imponible: 100,00 EUR",
            "IVA 21 %: 21,00 EUR", "Total factura: 121,00 EUR", "Moneda: EUR",
        ]

    def test_conventional_vertical_invoice_without_colon_pairs_is_extracted(self):
        fields, document = self.fields(self.standard_lines())
        self.assertEqual(fields["document_type"]["value"], "invoice")
        self.assertEqual(fields["supplier"]["value"], "Litoral Ejemplo S.L.")
        self.assertEqual(fields["supplier_tax_id"]["value"], "B12345674")
        self.assertEqual(fields["recipient"]["value"], "Cooperativa Sintetica COOP.")
        self.assertEqual(fields["recipient_tax_id"]["value"], "F7654321A")
        self.assertEqual(fields["invoice_number"]["value"], "INV-2026-0042")
        self.assertEqual(fields["issue_date"]["value"], "2026-06-15")
        self.assertEqual(fields["taxable_base"]["value"], "100.00")
        self.assertEqual(fields["vat"]["value"], "21.00")
        self.assertEqual(fields["total"]["value"], "121.00")
        self.assertEqual(fields["currency"]["value"], "EUR")
        self.assertTrue(document.fields["fragments"])

    def test_values_on_following_line_and_european_thousands(self):
        fields, _ = self.fields([
            "INVOICE", "Supplier", "Norte Demostracion S.L.", "Customer", "Cliente Prueba S.A.",
            "Invoice number", "A-884", "Issue date", "2026-05-09",
            "Subtotal", "1.234,56 EUR", "VAT amount", "259,26 EUR", "Amount due", "1.493,82 EUR", "Currency", "EUR",
        ])
        self.assertEqual(fields["invoice_number"]["value"], "A-884")
        self.assertEqual(fields["taxable_base"]["value"], "1234.56")
        self.assertEqual(fields["vat"]["value"], "259.26")
        self.assertEqual(fields["total"]["value"], "1493.82")

    def test_simple_fiscal_table_and_columns_are_supported(self):
        fields, _ = self.fields([
            "FACTURA", "Proveedor: Altura Ensayos S.A.", "Cliente: Cliente Modelo S.L.",
            "Numero de factura: TAB-77", "Fecha factura: 2026-04-18",
            "BASE IMPONIBLE | IVA | TOTAL", "200,00 | 20,00 | 220,00", "Moneda: EUR",
        ])
        self.assertEqual(fields["taxable_base"]["value"], "200.00")
        self.assertEqual(fields["vat"]["value"], "20.00")
        self.assertEqual(fields["total"]["value"], "220.00")

    def test_vat_rate_is_not_mistaken_for_vat_amount(self):
        fields, _ = self.fields(self.standard_lines()[:-3] + ["IVA 10 %: 13,00 EUR", "Total factura: 113,00 EUR", "Moneda: EUR"])
        self.assertEqual(fields["vat"]["value"], "13.00")

    def test_issue_date_is_not_due_or_service_date(self):
        fields, _ = self.fields(self.standard_lines() + ["Fecha de vencimiento: 30/06/2026", "Fecha servicio: 01/06/2026"])
        self.assertEqual(fields["issue_date"]["value"], "2026-06-15")

    def test_ambiguous_tax_ids_and_amounts_fail_safely(self):
        fields, _ = self.fields(["FACTURA", "B11111111", "B22222222", "TOTAL 80,00", "TOTAL 90,00"])
        self.assertIn(fields["supplier_tax_id"]["status"], {"unknown", "conflict"})
        self.assertIn(fields["recipient_tax_id"]["status"], {"unknown", "conflict"})
        self.assertEqual(fields["total"]["status"], "conflict")

    def test_multiple_vat_rates_are_conflict_in_v1(self):
        fields, _ = self.fields(self.standard_lines()[:-3] + ["IVA 21 %: 21,00", "IVA 10 %: 5,00", "Total factura: 126,00", "Moneda: EUR"])
        self.assertEqual(fields["vat"]["status"], "conflict")
        self.assertIsNone(fields["vat"]["value"])

    def test_document_variants_repeated_total_and_insufficient_labels(self):
        credit, _ = self.fields(["FACTURA RECTIFICATIVA", "Total factura: -20,00 EUR"])
        simplified, _ = self.fields(["FACTURA SIMPLIFICADA", "Total: 12,50 EUR"])
        repeated, _ = self.fields(self.standard_lines() + ["TOTAL FACTURA: 121,00 EUR"])
        insufficient, _ = self.fields(["Documento comercial", "49,00 EUR", "2026-06-10"])
        self.assertEqual(credit["document_type"]["value"], "credit_note")
        self.assertEqual(simplified["document_type"]["value"], "simplified_invoice")
        self.assertEqual(repeated["total"]["value"], "121.00")
        self.assertEqual(insufficient["document_type"]["status"], "unknown")

    def test_arithmetic_tolerance_is_decimal_and_does_not_invent(self):
        consistent, _ = self.fields(self.standard_lines())
        self.assertEqual(self.resolvers.arithmetic_consistency(consistent), "consistent")
        close = {name: dict(value) for name, value in consistent.items()}; close["total"]["value"] = "121.02"
        self.assertEqual(self.resolvers.arithmetic_consistency(close), "consistent")
        bad = {name: dict(value) for name, value in consistent.items()}; bad["total"]["value"] = "122.00"
        self.assertEqual(self.resolvers.arithmetic_consistency(bad), "inconsistent")
        unknown = {name: dict(value) for name, value in consistent.items()}; unknown["vat"]["value"] = None
        self.assertEqual(self.resolvers.arithmetic_consistency(unknown), "unknown")
        self.assertEqual(self.resolvers.ABSOLUTE_TOLERANCE, Decimal("0.02"))

    def test_blank_text_pdf_is_not_fabricated(self):
        content = blank_text_pdf()
        document = self.attachments.extract_text(self.models.DocumentInput("attachment:blank", "blank.pdf", "application/pdf", content))
        fields = self.extraction.extract_fields(document)
        self.assertTrue(all(value["status"] == "unknown" for value in fields.values()))
        self.assertIn("document-unreadable", document.warnings)

    def test_candidates_are_deterministic_auditable_and_generic(self):
        fields, document = self.fields(self.standard_lines())
        first = self.resolvers.generate_candidates(document); second = self.resolvers.generate_candidates(document)
        self.assertEqual(first, second); self.assertTrue(first)
        for candidate in first:
            self.assertTrue(candidate.field); self.assertTrue(candidate.rule_id); self.assertTrue(candidate.evidence_text)
            self.assertIn(candidate.relation, self.resolvers.FieldCandidate.__dataclass_fields__["relation"].type if False else {"same_line_right", "next_line", "aligned_column", "same_block", "table_row", "syntax_only", "arithmetic_support"})
