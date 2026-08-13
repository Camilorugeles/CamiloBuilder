from __future__ import annotations

import importlib
import sys
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from builders.project_builder import ProjectBuilder
from builders.service_builder import ServiceBuilder
from tests.invoice_pdf_fixtures import blank_text_pdf, operation_pdf, positioned_pdf, textual_pdf, visual_order_pdf


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
        cls.layout = importlib.import_module("services.invoice_intake.layout")

    @classmethod
    def tearDownClass(cls):
        for name in list(sys.modules):
            if name == "services" or name.startswith("services."): sys.modules.pop(name, None)
        sys.path.remove(str(cls.project)); cls.temporary.cleanup()

    def fields(self, lines):
        content = textual_pdf(lines)
        document = self.attachments.extract_text(self.models.DocumentInput("attachment:synthetic", "synthetic.pdf", "application/pdf", content))
        return self.extraction.extract_fields(document), document

    def positioned_fields(self, rows):
        content = positioned_pdf(rows)
        document = self.attachments.extract_text(self.models.DocumentInput("attachment:geometry", "geometry.pdf", "application/pdf", content))
        return self.extraction.extract_fields(document), document

    def content_fields(self, content):
        document = self.attachments.extract_text(self.models.DocumentInput("attachment:advanced", "advanced.pdf", "application/pdf", content))
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

    def test_contextual_invoice_date_requires_document_corroboration(self):
        fields, _ = self.fields(["FACTURA COMERCIAL", "14/09/2026", "Referencia general"])
        self.assertEqual(fields["issue_date"]["value"], "2026-09-14")
        isolated, _ = self.fields(["Documento comercial", "14/09/2026", "Referencia general"])
        self.assertEqual(isolated["issue_date"]["status"], "unknown")

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
        delivery, _ = self.fields(["ALBARAN", "Numero: ALB-42"])
        referenced, _ = self.fields(["FACTURA", "Referencia albaran: ALB-42"])
        mixed, _ = self.fields([
            "Resumen factura emitida", "Datos factura disponibles",
            "Referencia de factura registrada", "ALBARAN",
        ])
        repeated, _ = self.fields(self.standard_lines() + ["TOTAL FACTURA: 121,00 EUR"])
        insufficient, _ = self.fields(["Documento comercial", "49,00 EUR", "2026-06-10"])
        self.assertEqual(credit["document_type"]["value"], "credit_note")
        self.assertEqual(simplified["document_type"]["value"], "simplified_invoice")
        self.assertEqual(delivery["document_type"]["value"], "delivery_note")
        self.assertEqual(referenced["document_type"]["value"], "invoice")
        self.assertEqual(mixed["document_type"]["status"], "conflict")
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
            self.assertIn(candidate.relation, {"same_line_right", "next_line", "aligned_column", "same_block", "table_row", "syntax_only", "arithmetic_support", "table_header_value", "aligned_below_header", "aligned_above_label", "paired_column"})

    def test_horizontal_headers_resolve_number_date_and_customer(self):
        fields, document = self.positioned_fields([
            [(45, "FACTURA")],
            [(45, "N FACTURA"), (210, "FECHA EMISION"), (360, "CLIENTE")],
            [(45, "DOC-458"), (210, "09/03/2026"), (360, "Comercio Modelo S.L.")],
        ])
        self.assertEqual(fields["invoice_number"]["value"], "DOC-458")
        self.assertEqual(fields["issue_date"]["value"], "2026-03-09")
        self.assertEqual(fields["recipient"]["value"], "Comercio Modelo S.L.")
        self.assertTrue(document.fields["fragments"])

    def test_factura_no_is_a_geometric_number_header_only(self):
        fields, _ = self.positioned_fields([
            [(45, "FACTURA NO"), (210, "FECHA EMISION")],
            [(45, "SYN-8804"), (210, "09/03/2026")],
        ])
        self.assertEqual(fields["invoice_number"]["value"], "SYN-8804")

        unavailable, _ = self.fields(["Factura no disponible"])
        self.assertEqual(unavailable["invoice_number"]["status"], "unknown")

    def test_opposed_identity_blocks_associate_each_company_and_tax_id(self):
        fields, _ = self.positioned_fields([
            [(45, "PROVEEDOR"), (330, "CLIENTE")],
            [(45, "Servicios Delta S.L."), (330, "Cooperativa Horizonte COOP.")],
            [(45, "CIF B87654321"), (330, "NIF F1234567B")],
        ])
        self.assertEqual(fields["supplier"]["value"], "Servicios Delta S.L.")
        self.assertEqual(fields["supplier_tax_id"]["value"], "B87654321")
        self.assertEqual(fields["recipient"]["value"], "Cooperativa Horizonte COOP.")
        self.assertEqual(fields["recipient_tax_id"]["value"], "F1234567B")

    def test_fiscal_table_maps_base_rate_vat_and_total(self):
        fields, _ = self.positioned_fields([
            [(45, "BASE IMPONIBLE"), (185, "% IVA"), (285, "CUOTA IVA"), (420, "TOTAL")],
            [(45, "300,00"), (185, "10 %"), (285, "30,00"), (420, "330,00")],
        ])
        self.assertEqual(fields["taxable_base"]["value"], "300.00")
        self.assertEqual(fields["vat"]["value"], "30.00")
        self.assertEqual(fields["total"]["value"], "330.00")

    def test_inline_vat_percentage_header_is_rate_not_amount(self):
        fields, _ = self.positioned_fields([
            [(45, "IVA 10 %"), (220, "120,00")],
        ])
        self.assertEqual(fields["vat"]["status"], "unknown")
        explicit, _ = self.positioned_fields([
            [(45, "CUOTA IVA 10 %"), (220, "12,00")],
        ])
        self.assertEqual(explicit["vat"]["value"], "12.00")

    def test_footer_total_and_repeated_total_resolve_without_max_heuristic(self):
        fields, _ = self.positioned_fields([
            [(45, "Subtotal"), (430, "400,00")],
            [(45, "TOTAL FACTURA"), (430, "484,00")],
            [(45, "IMPORTE TOTAL"), (430, "484,00")],
        ])
        self.assertEqual(fields["total"]["value"], "484.00")
        conflicting, _ = self.positioned_fields([
            [(45, "TOTAL FACTURA"), (430, "484,00")],
            [(45, "IMPORTE TOTAL"), (430, "499,00")],
        ])
        self.assertEqual(conflicting["total"]["status"], "conflict")

    def test_importe_header_is_not_a_concept(self):
        fields, _ = self.positioned_fields([
            [(45, "CONCEPTO"), (420, "IMPORTE")],
            [(45, "Revision preventiva"), (420, "75,00")],
        ])
        self.assertEqual(fields["concept"]["value"], "Revision preventiva")
        missing, _ = self.positioned_fields([[(45, "CONCEPTO"), (420, "IMPORTE")]])
        self.assertEqual(missing["concept"]["status"], "unknown")

    def test_due_and_service_dates_do_not_replace_horizontal_issue_date(self):
        fields, _ = self.positioned_fields([
            [(45, "FECHA EMISION"), (220, "VENCIMIENTO"), (390, "FECHA SERVICIO")],
            [(45, "2026-02-11"), (220, "2026-03-11"), (390, "2026-02-01")],
        ])
        self.assertEqual(fields["issue_date"]["value"], "2026-02-11")

    def test_ambiguous_geometry_fails_safely_and_linear_fallback_remains(self):
        ambiguous, _ = self.positioned_fields([
            [(45, "N FACTURA"), (150, "FECHA")],
            [(98, "AMB-7"), (105, "2026-01-02")],
        ])
        self.assertIn(ambiguous["invoice_number"]["status"], {"unknown", "conflict"})
        fallback, _ = self.fields(["Invoice number", "LIN-9", "Issue date", "2026-01-03"])
        self.assertEqual(fallback["invoice_number"]["value"], "LIN-9")

    def test_multi_rate_fiscal_table_remains_v1_conflict(self):
        fields, _ = self.positioned_fields([
            [(45, "BASE"), (180, "% IVA"), (285, "CUOTA IVA")],
            [(45, "100,00"), (180, "10 %"), (285, "10,00")],
            [(45, "50,00"), (180, "4 %"), (285, "2,00")],
        ])
        # Only an unambiguous header/value row is automatically consumed;
        # additional plausible VAT evidence prevents a fabricated aggregate.
        self.assertIn(fields["vat"]["status"], {"unknown", "conflict"})

    def test_layout_document_is_neutral_and_visual_order_wins(self):
        fields, document = self.content_fields(visual_order_pdf([
            (45, 742, "410,00"), (45, 766, "BASE IMPONIBLE"),
            (220, 742, "86,10"), (220, 766, "CUOTA IVA"),
            (400, 742, "496,10"), (400, 766, "TOTAL FACTURA"),
        ]))
        layout = document.fields["layout"]
        self.assertEqual(layout.geometry, "observed")
        self.assertEqual([cell.text for cell in layout.rows[0].cells], ["BASE IMPONIBLE", "CUOTA IVA", "TOTAL FACTURA"])
        self.assertNotEqual(layout.reading_order, tuple(range(len(layout.fragments))))
        self.assertEqual(fields["taxable_base"]["value"], "410.00")
        self.assertEqual(fields["vat"]["value"], "86.10")
        self.assertEqual(fields["total"]["value"], "496.10")

    def test_transformed_matrix_and_tj_fragments_keep_observed_geometry(self):
        content = operation_pdf([
            "q", "1 0 0 1 30 20 cm", "BT", "/F1 10 Tf",
            "1 0 0 1 20 760 Tm", "[(N ) -20 (FACTURA)] TJ",
            "1 0 0 1 190 760 Tm", "(FECHA EMISION) Tj",
            "1 0 0 1 20 736 Tm", "(SYN-730) Tj",
            "1 0 0 1 190 736 Tm", "(17-07-2026) Tj", "ET", "Q",
        ])
        fields, document = self.content_fields(content)
        self.assertEqual(document.fields["layout"].geometry, "observed")
        self.assertEqual(fields["invoice_number"]["value"], "SYN-730")
        self.assertEqual(fields["issue_date"]["value"], "2026-07-17")

    def test_monetary_header_after_customer_is_not_an_identity(self):
        fields, _ = self.positioned_fields([
            [(45, "CLIENTE"), (300, "FORMA DE PAGO"), (430, "IMPORTE")],
            [(300, "TRANSFERENCIA"), (430, "75,00")],
        ])
        self.assertEqual(fields["recipient"]["status"], "unknown")
        self.assertEqual(fields["supplier"]["status"], "unknown")

    def test_tax_ids_follow_identity_geometry_not_appearance_order(self):
        fields, _ = self.content_fields(visual_order_pdf([
            (330, 720, "NIF F2345678C"), (45, 720, "CIF B23456789"),
            (330, 744, "Cooperativa Aurora COOP."), (45, 744, "Talleres Ficticios S.L."),
            (330, 768, "CLIENTE"), (45, 768, "PROVEEDOR"),
        ]))
        self.assertEqual(fields["supplier_tax_id"]["value"], "B23456789")
        self.assertEqual(fields["recipient_tax_id"]["value"], "F2345678C")

    def test_tabular_issue_date_beats_due_date_without_global_boost(self):
        fields, _ = self.positioned_fields([
            [(45, "N FACTURA"), (190, "FECHA"), (340, "CLIENTE")],
            [(45, "SYN-91"), (190, "11/08/2026"), (340, "Empresa Demostracion S.L.")],
            [(45, "VENCIMIENTO"), (190, "30/08/2026")],
        ])
        self.assertEqual(fields["issue_date"]["value"], "2026-08-11")

    def test_isolated_tax_id_and_ambiguous_geometry_fail_safely(self):
        isolated, _ = self.positioned_fields([
            [(45, "PROVEEDOR"), (330, "CLIENTE")],
            [(45, "Empresa Norte S.L."), (330, "Empresa Sur S.A.")],
            [(190, "B34567890")],
        ])
        self.assertEqual(isolated["supplier_tax_id"]["status"], "unknown")
        self.assertEqual(isolated["recipient_tax_id"]["status"], "unknown")
        ambiguous, _ = self.positioned_fields([
            [(45, "TOTAL FACTURA"), (330, "IMPORTE TOTAL")],
            [(180, "99,00")],
        ])
        self.assertIn(ambiguous["total"]["status"], {"unknown", "conflict"})

    def test_estimated_and_insufficient_geometry_are_explicit(self):
        estimated = self.layout.build_layout("", [
            {"text": "N FACTURA", "page": 1, "x": 40, "y": 700, "x1": 80, "y1": 710, "font_size": 10, "order": 0, "geometry": "estimated"},
            {"text": "FECHA", "page": 1, "x": 180, "y": 700, "x1": 210, "y1": 710, "font_size": 10, "order": 1, "geometry": "estimated"},
            {"text": "SYN-4", "page": 1, "x": 40, "y": 676, "x1": 75, "y1": 686, "font_size": 10, "order": 2, "geometry": "estimated"},
            {"text": "2026-08-04", "page": 1, "x": 180, "y": 676, "x1": 235, "y1": 686, "font_size": 10, "order": 3, "geometry": "estimated"},
        ])
        self.assertEqual(estimated.geometry, "estimated")
        self.assertTrue(all(row.geometry == "estimated" for row in estimated.rows))
        self.assertIn("geometry-estimated", estimated.warnings)
        insufficient = self.layout.build_layout("N FACTURA\nSYN-4")
        self.assertEqual(insufficient.geometry, "insufficient")
        self.assertFalse(insufficient.coordinates_reliable)

    def test_evidence_links_are_complete_deterministic_and_deduplicated(self):
        fields, document = self.positioned_fields([
            [(45, "FACTURA")],
            [(45, "TOTAL FACTURA")],
            [(45, "73,00")],
        ])
        first = self.resolvers.generate_candidates(document)
        second = self.resolvers.generate_candidates(document)
        self.assertEqual(first, second)
        total_candidates = [item for item in first if item.field == "total" and item.value == "73.00"]
        self.assertTrue(total_candidates)
        self.assertTrue(all(item.evidence and item.evidence.observation_id for item in total_candidates))
        self.assertEqual(len({item.evidence.observation_id for item in total_candidates}), 1)
        self.assertEqual(fields["total"]["status"], "unknown")

    def test_bounded_header_search_skips_spacer_but_not_interposed_headers(self):
        fields, _ = self.positioned_fields([
            [(45, "N FACTURA"), (210, "FECHA"), (360, "CLIENTE")],
            [(520, "NOTA")],
            [(45, "SYN-SPACE-8"), (210, "12/08/2026"), (360, "Comercio Imaginario S.L.")],
        ])
        self.assertEqual(fields["invoice_number"]["value"], "SYN-SPACE-8")
        self.assertEqual(fields["issue_date"]["value"], "2026-08-12")
        blocked, blocked_document = self.positioned_fields([
            [(45, "N FACTURA"), (210, "FECHA")],
            [(45, "N FACTURA"), (210, "VENCIMIENTO")],
            [(45, "SYN-WRONG-4"), (210, "28/08/2026")],
        ])
        self.assertEqual(blocked["invoice_number"].get("value"), "SYN-WRONG-4")
        matching = [
            item for item in self.resolvers.generate_candidates(blocked_document)
            if item.field == "invoice_number" and item.value == "SYN-WRONG-4" and item.evidence.table_id
        ]
        self.assertTrue(matching)
        self.assertTrue(all(item.evidence.table_id.endswith("table-1") for item in matching))

    def test_unlabelled_identity_blocks_conflict_instead_of_using_page_order(self):
        fields, _ = self.positioned_fields([
            [(45, "Talleres Imaginarios S.L.")],
            [(45, "CIF B23456789")],
            [(330, "Cooperativa Inventada COOP.")],
            [(330, "NIF F2345678C")],
        ])
        self.assertEqual(fields["supplier"]["status"], "conflict")
        self.assertEqual(fields["recipient"]["status"], "conflict")

    def test_company_like_text_inside_item_table_is_not_an_identity(self):
        fields, _ = self.positioned_fields([
            [(45, "CONCEPTO"), (400, "IMPORTE")],
            [(45, "Servicios Inventados S.L."), (400, "80,00")],
        ])
        self.assertEqual(fields["supplier"]["status"], "unknown")
        self.assertEqual(fields["recipient"]["status"], "unknown")

    def test_multiline_fiscal_header_preserves_columns_and_observed_values(self):
        fields, document = self.positioned_fields([
            [(45, "BASE IMPONIBLE"), (180, "% IVA")],
            [(285, "CUOTA IVA"), (420, "TOTAL FACTURA")],
            [(45, "250,00"), (180, "10 %"), (285, "25,00"), (420, "275,00")],
        ])
        self.assertEqual(fields["taxable_base"]["value"], "250.00")
        self.assertEqual(fields["vat"]["value"], "25.00")
        self.assertEqual(fields["total"]["value"], "275.00")
        fiscal = [item for item in self.resolvers.generate_candidates(document) if item.evidence and item.evidence.table_id]
        self.assertTrue(fiscal)
        self.assertTrue(all(item.evidence.row_id for item in fiscal))

    def test_subtotal_and_larger_amount_do_not_replace_labeled_final_total(self):
        fields, _ = self.positioned_fields([
            [(45, "SUBTOTAL"), (420, "900,00")],
            [(45, "PRECIO"), (420, "1.200,00")],
            [(45, "TOTAL FACTURA"), (420, "120,00")],
        ])
        self.assertEqual(fields["total"]["value"], "120.00")
        self.assertNotEqual(fields["total"]["value"], "1200.00")

    def test_arithmetic_support_does_not_cross_tables_or_create_missing_vat(self):
        fields, document = self.positioned_fields([
            [(45, "BASE"), (180, "CUOTA IVA"), (330, "TOTAL FACTURA")],
            [(45, "100,00"), (180, "20,00"), (330, "500,00")],
            [(45, "BASE"), (180, "CUOTA IVA"), (330, "TOTAL FACTURA")],
            [(45, "300,00"), (180, "60,00"), (330, "120,00")],
        ])
        cross_total = [
            item for item in self.resolvers.generate_candidates(document)
            if item.field == "total" and item.value == "120.00"
        ]
        self.assertTrue(cross_total)
        self.assertTrue(all(item.relation != "arithmetic_support" for item in cross_total))
        self.assertIn(fields["total"]["status"], {"unknown", "conflict"})
        missing, _ = self.positioned_fields([
            [(45, "BASE IMPONIBLE"), (330, "TOTAL FACTURA")],
            [(45, "100,00"), (330, "121,00")],
        ])
        self.assertEqual(missing["vat"]["status"], "unknown")
