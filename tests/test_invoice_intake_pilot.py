import copy
import hashlib
import importlib
import importlib.util
import json
import re
import socket
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from builders.agent_builder import AgentBuilder
from builders.project_builder import ProjectBuilder
from builders.service_builder import ServiceBuilder
from template_system.registry import TemplateRegistry


ROOT = Path(__file__).resolve().parents[1]
PROTECTED_DEFAULTS = {path: hashlib.sha256((ROOT / path).read_bytes()).hexdigest() for path in (
    "templates/agent/default/template.json", "templates/agent/default/files/__init__.py", "templates/agent/default/files/README.md",
    "templates/service/default/template.json", "templates/service/default/files/__init__.py", "templates/service/default/files/README.md",
)}


def pdf(**values):
    text = "\n".join(f"{key}: {value}" for key, value in values.items())
    return b"%PDF-1.4\n%CAMILO-SYNTHETIC\n" + text.encode()


def xml(**values):
    body = "".join(f"<{key}>{value}</{key}>" for key, value in values.items())
    return f"<SyntheticInvoice>{body}</SyntheticInvoice>".encode()


def invoice_values(**overrides):
    values = {
        "document_type": "invoice", "supplier": "Synthetic Supplies", "supplier_tax_id": "SYN-A0001",
        "invoice_number": "SYN-001", "issue_date": "2026-08-01", "recipient": "Synthetic Trading Cooperative",
        "recipient_tax_id": "SYN-B0002", "taxable_base": "100.00", "vat": "21.00", "other_taxes": "0.00",
        "withholdings": "0.00", "total": "121.00", "currency": "EUR", "concept": "kitchen materials",
    }
    values.update(overrides); return values


class SyntheticConnector:
    connector_id = "gmail.company-invoices"; provider_id = "synthetic"
    def __init__(self, messages, contents): self.messages = messages; self.contents = contents; self.execution_count = 0
    def capabilities(self): return frozenset({"content.read", "item.metadata.read"})
    def read(self, reference): return copy.deepcopy(self.messages[reference.reference])
    def read_content(self, reference):
        from services.agent_core.models import ConnectorContent
        media, content = self.contents[reference]; return ConnectorContent(reference, media, content)
    def execute(self, **kwargs): self.execution_count += 1; raise AssertionError("Shadow mode attempted an external action")


class InvoiceIntakePilotTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(); cls.root = Path(cls.temporary.name)
        cls.project = ProjectBuilder(cls.root / "output").build("SyntheticOS")
        ServiceBuilder(cls.project, "agent-core").build("agent_core")
        ServiceBuilder(cls.project, "google-connectors").build("google_connectors")
        ServiceBuilder(cls.project, "invoice-intake").build("invoice_intake")
        AgentBuilder(cls.project, "invoice-intake-shadow").build("invoice-intake")
        sys.path.insert(0, str(cls.project)); cls._purge()
        cls.models = importlib.import_module("services.agent_core.models")
        cls.runtime = importlib.import_module("services.agent_core.runtime")
        cls.memory = importlib.import_module("services.agent_core.in_memory")
        cls.sqlite = importlib.import_module("services.agent_core.sqlite_store")
        cls.validation = importlib.import_module("services.agent_core.validation")
        cls.pilot_validation = importlib.import_module("services.invoice_intake.validation")
        cls.duplicates = importlib.import_module("services.invoice_intake.duplicates")
        behavior_path = cls.project / "agents/invoice-intake/behavior.py"
        spec = importlib.util.spec_from_file_location("invoice_shadow_behavior", behavior_path)
        cls.behavior_module = importlib.util.module_from_spec(spec); spec.loader.exec_module(cls.behavior_module)

    @classmethod
    def tearDownClass(cls):
        cls._purge(); sys.path.remove(str(cls.project)); cls.temporary.cleanup()

    @staticmethod
    def _purge():
        for name in list(sys.modules):
            if name == "services" or name.startswith("services."): sys.modules.pop(name, None)

    def config(self, refs=("gmail:message:001",)):
        return {
            "format": "camilo-os.invoice-intake-pilot", "format_version": 1, "mode": "shadow",
            "gmail_connector_alias": "gmail.company-invoices", "drive_connector_alias": "drive.finance-intake",
            "selection": {"query": "newer_than:30d has:attachment", "pilot_message_refs": list(refs), "max_messages": 15, "max_per_supplier": 2},
            "destinations": {"classify": "drive:folder:synthetic-classify", "missing_data": "drive:folder:synthetic-missing", "pending_accounting": "drive:folder:synthetic-accounting", "pending_reconciliation": "drive:folder:synthetic-reconciliation", "activity_destinations": {"synthetic_kitchen": "drive:folder:synthetic-kitchen"}},
            "legal_entities": ["not_applicable_personal", "synthetic_cooperative", "unknown"],
            "activities": ["administracion_compartida", "internal_transfer", "multiple_candidates", "personal", "synthetic_kitchen", "synthetic_property", "unknown"],
            "document_types": ["credit_note", "delivery_note", "invoice", "other", "payment_statement", "receipt", "simplified_invoice", "unknown"],
            "knowledge_refs": ["knowledge.synthetic-policy"], "reviewer_refs": [],
            "execution_store_path": "runtime/executions.sqlite3", "duplicate_store_path": "runtime/duplicates.sqlite3",
            "classification_rules": {
                "recipient_rules": [{"evidence": "synthetic trading cooperative", "value": "synthetic_cooperative"}],
                "activity_rules": [{"evidence": "kitchen", "value": "synthetic_kitchen"}, {"evidence": "property", "value": "synthetic_property"}],
                "personal_terms": ["personal trip"], "internal_transfer_terms": ["internal transfer"],
                "shared_terms": ["shared administration"], "arras_terms": ["deposit agreement"],
                "sensitive_terms": ["payroll"],
            },
        }

    def validate_config(self, config):
        path = self.root / "pilot-config.json"; path.write_text(json.dumps(config), encoding="utf-8")
        return self.pilot_validation.load_pilot_configuration(path)

    def execute_case(self, attachments, *, ref="gmail:message:001", duplicate_lookup=None, config=None, operation_key="pilot"):
        content_refs = sorted(attachments)
        connector = SyntheticConnector({ref: {"content_refs": content_refs, "attachment_filenames": {key: key.rsplit(":", 1)[-1] for key in content_refs}}}, attachments)
        definition = self.validation.load_agent_definition(self.project / "agents/invoice-intake/agent.json")
        behavior = self.behavior_module.InvoiceIntakeShadowBehavior(configuration=self.validate_config(config or self.config((ref,))), duplicate_lookup=duplicate_lookup or self.duplicates.InMemoryDuplicateLookup())
        record = self.runtime.run_agent(definition=definition, behavior=behavior, connector=connector, approval_gateway=self.memory.InMemoryApprovalGateway(), record_store=self.memory.InMemoryExecutionRecordStore(), input_reference=self.models.InputReference("source.gmail-company-invoices", ref), operation_key=operation_key)
        analysis = next(item["value"] for item in record["results"] if item["kind"] == "invoice-analysis.v1")
        review = next(item["value"] for item in record["results"] if item["kind"] == "invoice-review-card.v1")
        return record, analysis, review, connector

    def test_templates_registered_without_component_type_or_default_changes(self):
        registry = TemplateRegistry(ROOT / "templates")
        self.assertEqual([m.name for _, m in registry.list("service")], ["agent-core", "default", "google-connectors", "invoice-intake"])
        self.assertEqual([m.name for _, m in registry.list("agent")], ["camilo-os-agent", "default", "invoice-intake-shadow"])
        self.assertEqual(sorted(path.name for path in (ROOT / "templates").iterdir()), ["agent", "department", "project", "service"])
        for path, digest in PROTECTED_DEFAULTS.items(): self.assertEqual(hashlib.sha256((ROOT / path).read_bytes()).hexdigest(), digest)

    def test_generation_is_idempotent_and_non_overwriting(self):
        target = self.project / "services/invoice_intake/README.md"; target.write_text("custom\n", encoding="utf-8")
        before = sorted(path.relative_to(self.project) for path in self.project.rglob("*"))
        ServiceBuilder(self.project, "invoice-intake").build("invoice_intake")
        self.assertEqual(before, sorted(path.relative_to(self.project) for path in self.project.rglob("*")))
        self.assertEqual(target.read_text(), "custom\n")

    def test_configuration_closed_shadow_bounded_sorted_and_secret_free(self):
        self.assertEqual(self.validate_config(self.config())["mode"], "shadow")
        cases = []
        invalid = self.config(); invalid["mode"] = "execute"; cases.append(invalid)
        invalid = self.config(tuple(f"gmail:message:{i:02d}" for i in range(16))); cases.append(invalid)
        invalid = self.config(("gmail:message:002", "gmail:message:001")); cases.append(invalid)
        invalid = self.config(); invalid["token"] = "SECRET"; cases.append(invalid)
        for value in cases:
            with self.subTest(value=value):
                with self.assertRaises(self.pilot_validation.InvoiceIntakeConfigurationError): self.validate_config(value)
        schemas = "".join(path.read_text() for path in (self.project / "services/invoice_intake/schemas").iterdir())
        self.assertNotRegex(schemas, r"[A-Za-z0-9_-]{30,}")
        self.assertNotIn("@gmail.com", schemas.lower())

    def test_complete_invoice_is_deterministic_and_has_no_actions(self):
        attachment = {"gmail:attachment:001:invoice.pdf": ("application/pdf", pdf(**invoice_values()))}
        first = self.execute_case(attachment); second = self.execute_case(attachment)
        record, analysis, review, connector = first
        self.assertEqual(analysis["document_status"], "invoice_complete")
        self.assertEqual(analysis["global_confidence"], "high")
        self.assertEqual(record["status"], "completed")
        self.assertEqual(record["proposed_actions"], []); self.assertEqual(record["executed_actions"], [])
        self.assertEqual(connector.execution_count, 0); self.assertEqual(first[2], second[2])
        self.assertEqual(self.runtime.stable_json(first[0]), self.runtime.stable_json(second[0]))

    def test_pdf_xml_matching_and_conflicting(self):
        values = invoice_values()
        matching = {"gmail:attachment:001:a.pdf": ("application/pdf", pdf(**values)), "gmail:attachment:001:b.xml": ("application/xml", xml(**values))}
        _, analysis, _, _ = self.execute_case(matching); self.assertEqual(analysis["document_status"], "invoice_complete")
        conflict = copy.deepcopy(matching); conflict["gmail:attachment:001:b.xml"] = ("application/xml", xml(**invoice_values(total="999.00")))
        _, analysis, _, _ = self.execute_case(conflict); self.assertEqual(analysis["document_status"], "needs_review"); self.assertIn("attachment-conflict", analysis["review_reasons"])

    def test_document_types_and_required_review_cases(self):
        cases = {
            "payment_statement": "not_an_invoice", "delivery_note": "not_an_invoice", "receipt": "receipt_or_ticket",
            "simplified_invoice": "receipt_or_ticket", "credit_note": "credit_note",
        }
        for document_type, expected in cases.items():
            with self.subTest(document_type=document_type):
                _, analysis, _, _ = self.execute_case({f"gmail:attachment:001:{document_type}.pdf": ("application/pdf", pdf(**invoice_values(document_type=document_type)))})
                self.assertEqual(analysis["document_status"], expected); self.assertTrue(analysis["review_required"])

    def test_missing_attachment_unreadable_octet_stream_and_mime_mismatch(self):
        _, missing, _, _ = self.execute_case({}); self.assertEqual(missing["document_status"], "needs_review")
        _, unreadable, _, _ = self.execute_case({"gmail:attachment:001:scan.pdf": ("application/pdf", b"%PDF-1.4\n")}); self.assertEqual(unreadable["document_status"], "needs_review")
        _, octet, _, _ = self.execute_case({"gmail:attachment:001:blob": ("application/octet-stream", pdf(**invoice_values()))}); self.assertEqual(octet["fields"]["invoice_number"]["value"], "SYN-001")
        _, mismatch, _, _ = self.execute_case({"gmail:attachment:001:bad.pdf": ("application/pdf", b"<xml/>")}); self.assertEqual(mismatch["document_status"], "needs_review")

    def test_xml_entities_and_limits_are_blocked(self):
        malicious = b'<!DOCTYPE x [<!ENTITY e SYSTEM "file:///etc/passwd">]><x>&e;</x>'
        _, analysis, _, _ = self.execute_case({"gmail:attachment:001:e.xml": ("application/xml", malicious)})
        self.assertEqual(analysis["document_status"], "needs_review")
        huge = b"%PDF-1.4\n" + b"x" * (8 * 1024 * 1024 + 1)
        _, analysis, _, _ = self.execute_case({"gmail:attachment:001:huge.pdf": ("application/pdf", huge)})
        self.assertEqual(analysis["document_status"], "needs_review")

    def test_business_classification_cases_are_reviewed(self):
        cases = [
            ({"concept": "personal trip"}, "personal_suspected", "personal"),
            ({"concept": "internal transfer"}, "internal_transfer", "internal_transfer"),
            ({"concept": "kitchen property"}, "invoice_incomplete", "multiple_candidates"),
            ({"concept": "shared administration"}, "invoice_incomplete", "administracion_compartida"),
            ({"concept": "deposit agreement"}, "invoice_incomplete", "unknown"),
            ({"concept": "payroll"}, "invoice_incomplete", "unknown"),
            ({"concept": "supermarket"}, "invoice_incomplete", "unknown"),
        ]
        for overrides, status, activity in cases:
            with self.subTest(overrides=overrides):
                _, analysis, _, _ = self.execute_case({"gmail:attachment:001:x.pdf": ("application/pdf", pdf(**invoice_values(**overrides)))})
                self.assertEqual(analysis["document_status"], status); self.assertEqual(analysis["activity"], activity); self.assertTrue(analysis["review_required"])

    def test_non_eur_arithmetic_and_unknown_recipient_require_review(self):
        for overrides, reason in (({"currency": "USD"}, "non-eur-currency"), ({"total": "120.00"}, "arithmetic-inconsistency"), ({"recipient": ""}, "missing-or-conflicting:recipient")):
            with self.subTest(overrides=overrides):
                _, analysis, _, _ = self.execute_case({"gmail:attachment:001:x.pdf": ("application/pdf", pdf(**invoice_values(**overrides)))})
                self.assertIn(reason, analysis["review_reasons"])

    def test_duplicate_key_content_fallback_sqlite_reopen_and_retry(self):
        path = self.root / "duplicates.sqlite3"; lookup = self.duplicates.SQLiteDuplicateLookup(path)
        content = pdf(**invoice_values())
        _, first, _, _ = self.execute_case({"gmail:attachment:001:x.pdf": ("application/pdf", content)}, duplicate_lookup=lookup)
        self.assertFalse(first["duplicate_refs"]); lookup.close()
        reopened = self.duplicates.SQLiteDuplicateLookup(path)
        _, duplicate, _, _ = self.execute_case({"gmail:attachment:002:x.pdf": ("application/pdf", content)}, ref="gmail:message:002", config=self.config(("gmail:message:002",)), duplicate_lookup=reopened)
        self.assertEqual(duplicate["document_status"], "duplicate_suspected")
        before = reopened.find(next(iter(reopened._connection.execute("SELECT fingerprint FROM invoice_fingerprints").fetchone())))
        self.execute_case({"gmail:attachment:002:x.pdf": ("application/pdf", content)}, ref="gmail:message:002", config=self.config(("gmail:message:002",)), duplicate_lookup=reopened)
        after = reopened.find(next(iter(reopened._connection.execute("SELECT fingerprint FROM invoice_fingerprints").fetchone())))
        self.assertEqual(before, after); reopened.close()

    def test_shadow_execution_record_persists_reopens_and_retry_is_idempotent(self):
        ref = "gmail:message:restart"; attachments = {"gmail:attachment:restart:x.pdf": ("application/pdf", pdf(**invoice_values()))}
        connector = SyntheticConnector({ref: {"content_refs": sorted(attachments), "attachment_filenames": {next(iter(attachments)): "invoice.pdf"}}}, attachments)
        definition = self.validation.load_agent_definition(self.project / "agents/invoice-intake/agent.json")
        behavior = self.behavior_module.InvoiceIntakeShadowBehavior(configuration=self.validate_config(self.config((ref,))), duplicate_lookup=self.duplicates.InMemoryDuplicateLookup())
        path = self.root / "execution-records.sqlite3"; store = self.sqlite.SQLiteExecutionRecordStore(path)
        first = self.runtime.run_agent(definition=definition, behavior=behavior, connector=connector, approval_gateway=self.memory.InMemoryApprovalGateway(), record_store=store, input_reference=self.models.InputReference("source.gmail-company-invoices", ref), operation_key="restart-safe")
        store.close(); reopened = self.sqlite.SQLiteExecutionRecordStore(path)
        retry = self.runtime.run_agent(definition=definition, behavior=behavior, connector=connector, approval_gateway=self.memory.InMemoryApprovalGateway(), record_store=reopened, input_reference=self.models.InputReference("source.gmail-company-invoices", ref), operation_key="restart-safe")
        self.assertEqual(first, retry); self.assertEqual(connector.execution_count, 0)
        self.assertEqual(reopened._connection.execute("SELECT COUNT(*) FROM execution_records").fetchone()[0], 1); reopened.close()

    def test_invoice_without_tax_identity_uses_content_fingerprint(self):
        values = invoice_values(supplier_tax_id="", invoice_number="")
        lookup = self.duplicates.InMemoryDuplicateLookup(); content = pdf(**values)
        self.execute_case({"gmail:attachment:001:x.pdf": ("application/pdf", content)}, duplicate_lookup=lookup)
        _, duplicate, _, _ = self.execute_case({"gmail:attachment:002:x.pdf": ("application/pdf", content)}, ref="gmail:message:002", config=self.config(("gmail:message:002",)), duplicate_lookup=lookup)
        self.assertEqual(duplicate["document_status"], "duplicate_suspected")

    def test_factura_and_delivery_note_remain_separate_and_reviewed(self):
        attachments = {"gmail:attachment:001:invoice.pdf": ("application/pdf", pdf(**invoice_values())), "gmail:attachment:001:delivery.pdf": ("application/pdf", pdf(**invoice_values(document_type="delivery_note", invoice_number="DN-1")))}
        _, analysis, _, _ = self.execute_case(attachments)
        self.assertEqual(analysis["document_status"], "needs_review"); self.assertIn("attachment-conflict", analysis["review_reasons"])

    def test_forwarded_same_attachment_is_duplicate_suspected(self):
        lookup = self.duplicates.InMemoryDuplicateLookup(); content = pdf(**invoice_values())
        self.execute_case({"gmail:attachment:001:forward.pdf": ("application/pdf", content)}, duplicate_lookup=lookup)
        _, analysis, _, _ = self.execute_case({"gmail:attachment:002:forward.pdf": ("application/pdf", content)}, ref="gmail:message:002", config=self.config(("gmail:message:002",)), duplicate_lookup=lookup)
        self.assertEqual(analysis["document_status"], "duplicate_suspected")

    def test_closed_batch_and_shadow_mode_fail_safely(self):
        with self.assertRaises(ValueError): self.behavior_module.InvoiceIntakeShadowBehavior(configuration={"mode": "execute"}, duplicate_lookup=self.duplicates.InMemoryDuplicateLookup())
        config = self.config(("gmail:message:999",))
        connector = SyntheticConnector({"gmail:message:001": {"content_refs": []}}, {})
        behavior = self.behavior_module.InvoiceIntakeShadowBehavior(configuration=self.validate_config(config), duplicate_lookup=self.duplicates.InMemoryDuplicateLookup())
        with self.assertRaises(ValueError): behavior.analyze(input_reference=self.models.InputReference("source.gmail-company-invoices", "gmail:message:001"), connector=connector)

    def test_closed_batch_enforces_two_messages_per_supplier_without_mutation(self):
        pipeline = importlib.import_module("services.invoice_intake.pipeline")
        refs = ("gmail:message:001", "gmail:message:002", "gmail:message:003")
        messages = {ref: {"metadata": {"from": "same@synthetic.invalid"}, "content_refs": []} for ref in refs}
        connector = SyntheticConnector(messages, {})
        with self.assertRaisesRegex(ValueError, "per-supplier"):
            pipeline.validate_closed_batch(configuration=self.validate_config(self.config(refs)), connector=connector)
        self.assertEqual(connector.execution_count, 0)

    def test_duplicate_store_rejects_symlink_paths(self):
        real = self.root / "real-store"; real.mkdir(exist_ok=True)
        link = self.root / "linked-store"
        if not link.exists(): link.symlink_to(real, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "Unsafe"):
            self.duplicates.SQLiteDuplicateLookup(link / "duplicates.sqlite3")

    def test_record_contains_only_references_derived_fields_and_no_full_content(self):
        private_body = "SYNTHETIC-DOCUMENT-CONTENT-NEVER-PERSIST"
        content = pdf(**invoice_values()) + ("\n" + private_body).encode()
        record, analysis, _, _ = self.execute_case({"gmail:attachment:001:x.pdf": ("application/pdf", content)})
        serialized = self.runtime.stable_json(record)
        self.assertNotIn(private_body, serialized); self.assertNotIn(content.decode(), serialized)
        self.assertTrue(analysis["content_fingerprints"]); self.assertEqual(record["proposed_actions"], []); self.assertEqual(record["executed_actions"], [])

    def test_suite_is_offline_and_repository_contains_no_real_markers(self):
        with mock.patch.object(socket, "socket", side_effect=AssertionError("network forbidden")):
            self.execute_case({"gmail:attachment:001:x.pdf": ("application/pdf", pdf(**invoice_values()))})
        template_text = "".join(path.read_text(encoding="utf-8", errors="ignore") for path in (ROOT / "templates/service/invoice-intake").rglob("*") if path.is_file())
        template_text += "".join(path.read_text(encoding="utf-8", errors="ignore") for path in (ROOT / "templates/agent/invoice-intake-shadow").rglob("*") if path.is_file())
        self.assertNotIn("@gmail.com", template_text.lower())
        self.assertIsNone(re.search(r"(?<!sha256:)[A-Za-z0-9_-]{35,}", template_text))

    def test_execution_record_v1_and_agent_definition_v1_remain_sufficient(self):
        definition = self.validation.load_agent_definition(self.project / "agents/invoice-intake/agent.json")
        self.assertEqual(definition["schema_version"], 1); self.assertFalse(definition["limits"]["external_writes"])
        self.assertEqual(definition["authorized_actions"], [{"action_id": "action.generate-review-card", "approval": "none"}])
        record, _, _, _ = self.execute_case({"gmail:attachment:001:x.pdf": ("application/pdf", pdf(**invoice_values()))})
        self.assertEqual((record["schema_version"], record["record_version"]), (1, "1.0.0"))
        self.assertFalse(list(self.project.rglob("*v2*")))
