from __future__ import annotations

import base64
import importlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

from builders.agent_builder import AgentBuilder
from builders.project_builder import ProjectBuilder
from builders.service_builder import ServiceBuilder
from tests.invoice_pdf_fixtures import textual_pdf


class RealPilotOperationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory()
        cls.project = ProjectBuilder(Path(cls.temporary.name) / "output").build("RealPilotSyntheticOS")
        ServiceBuilder(cls.project, "agent-core").build("agent_core")
        ServiceBuilder(cls.project, "google-connectors").build("google_connectors")
        ServiceBuilder(cls.project, "invoice-intake").build("invoice_intake")
        AgentBuilder(cls.project, "invoice-intake-shadow").build("invoice_intake")
        sys.path.insert(0, str(cls.project)); cls._purge()
        cls.models = importlib.import_module("services.agent_core.models")
        cls.memory = importlib.import_module("services.agent_core.in_memory")
        cls.runtime = importlib.import_module("services.agent_core.runtime")
        cls.validation = importlib.import_module("services.agent_core.validation")
        cls.secrets = importlib.import_module("services.agent_core.secrets")
        cls.factory = importlib.import_module("services.google_connectors.factory")
        cls.gmail_api = importlib.import_module("services.google_connectors.gmail_byte_only")
        cls.manifest_connector = importlib.import_module("services.google_connectors.manifest_connector")
        cls.manifest_loader = importlib.import_module("services.google_connectors.pilot_manifest")
        cls.duplicates = importlib.import_module("services.invoice_intake.duplicates")
        cls.operational = importlib.import_module("services.invoice_intake.operational")
        cls.behavior = importlib.import_module("agents.invoice_intake.behavior")

    @classmethod
    def tearDownClass(cls):
        cls._purge(); sys.path.remove(str(cls.project)); cls.temporary.cleanup()

    @staticmethod
    def _purge():
        for name in list(sys.modules):
            if name == "services" or name.startswith("services.") or name == "agents" or name.startswith("agents."):
                sys.modules.pop(name, None)

    def test_synthetic_byte_only_pilot_is_idempotent_and_has_zero_external_actions(self):
        case = {"case_id": "REAL-SYNTHETIC-001", "provider": "gmail", "message_ref": "gmail:message:m1", "attachment_ref": "gmail:attachment:m1:a1", "expected_media_type": "application/pdf", "purpose": "shadow_pilot", "authorized_on": "2026-08-14", "ground_truth_status": "authorized"}
        manifest = {"format": "camilo-os.real-pilot-manifest", "format_version": 1, "cases": [case]}
        manifest_path = Path(self.temporary.name) / "pilot-real-manifest.json"
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        manifest = self.manifest_loader.load_pilot_manifest(manifest_path)
        pdf = textual_pdf(["FACTURA", "Numero: SYN-REAL-001", "Fecha: 14/08/2026", "Total factura: 12,10 EUR"])
        encoded = base64.urlsafe_b64encode(pdf).decode("ascii").rstrip("=")
        requests = []

        class Response:
            def __enter__(self): return self
            def __exit__(self, *_args): pass
            def read(self, _limit): return json.dumps({"data": encoded, "size": len(pdf)}, separators=(",", ":")).encode()

        def opener(request, *, timeout): requests.append((request, timeout)); return Response()

        api_client = self.gmail_api.GmailByteOnlyAttachmentClient(
            attachment_media_types=self.manifest_loader.attachment_allowlist(manifest), opener=opener,
        )
        deployment = {"schema_version": 1, "connectors": [{"alias": "connector.gmail-pilot", "adapter": "google.gmail.readonly", "credential_ref": "secret-ref:pilot/gmail", "permissions": ["content.read"], "settings": {"account_alias": "pilot"}}]}
        credential = self.secrets.CredentialMaterial("SYNTHETIC-SECRET", frozenset({"gmail.readonly"}))
        factory = self.factory.ConnectorFactory(configuration=deployment, clients={"google.gmail.readonly": api_client}, secret_provider=self.secrets.FakeSecretProvider({"secret-ref:pilot/gmail": credential}))
        content_connector = factory.resolve("connector.gmail-pilot")
        connector = self.manifest_connector.ManifestBoundGmailConnector(manifest=manifest, content_connector=content_connector)
        configuration = {
            "format": "camilo-os.invoice-intake-pilot", "format_version": 1, "mode": "shadow",
            "gmail_connector_alias": "gmail.pilot", "drive_connector_alias": "drive.disabled",
            "selection": {"query": "manifest-only", "pilot_message_refs": [case["message_ref"]], "max_messages": 1, "max_per_supplier": 2},
            "destinations": {"classify": "drive:folder:disabled", "missing_data": "drive:folder:disabled", "pending_accounting": "drive:folder:disabled", "pending_reconciliation": "drive:folder:disabled", "activity_destinations": {}},
            "legal_entities": ["unknown"], "activities": ["unknown"], "document_types": ["invoice", "unknown"],
            "knowledge_refs": ["knowledge.synthetic"], "reviewer_refs": [],
            "execution_store_path": "runtime/executions.sqlite3", "duplicate_store_path": "runtime/duplicates.sqlite3",
            "classification_rules": {"recipient_rules": [], "activity_rules": [], "personal_terms": [], "internal_transfer_terms": [], "shared_terms": [], "arras_terms": [], "sensitive_terms": []},
        }
        definition = self.validation.load_agent_definition(self.project / "agents/invoice_intake/agent.json")
        definition["authorized_sources"][1]["connector_id"] = "connector.gmail-pilot"
        behavior = self.behavior.InvoiceIntakeShadowBehavior(configuration=configuration, duplicate_lookup=self.duplicates.InMemoryDuplicateLookup())
        store = self.memory.InMemoryExecutionRecordStore(); approvals = self.memory.InMemoryApprovalGateway()
        input_reference = self.models.InputReference("source.gmail-company-invoices", case["message_ref"])
        record = self.runtime.run_agent(definition=definition, behavior=behavior, connector=connector, approval_gateway=approvals, record_store=store, input_reference=input_reference, operation_key="real-pilot-synthetic")
        retry = self.runtime.run_agent(definition=definition, behavior=behavior, connector=connector, approval_gateway=approvals, record_store=store, input_reference=input_reference, operation_key="real-pilot-synthetic")
        self.assertEqual(record, retry)
        self.assertEqual(record["proposed_actions"], [])
        self.assertEqual(record["executed_actions"], [])
        self.assertEqual(len(requests), 1)
        self.assertEqual(connector.audit_summary(), {"manifest_reads": 2, "authorized_attachment_reads": 1, "messages_outside_manifest": 0, "attachments_outside_manifest": 0, "gmail_mutations": 0, "unread_changes": 0, "label_changes": 0, "drive_writes": 0})
        serialized = self.runtime.stable_json(record)
        self.assertNotIn(encoded, serialized)
        self.assertNotIn("SYNTHETIC-SECRET", serialized)

    def test_operational_summary_keeps_only_counts_and_sanitized_codes(self):
        record = {
            "status": "completed", "proposed_actions": [], "executed_actions": [],
            "results": [{"kind": "invoice-analysis.v1", "value": {
                "attachments": [{"reference": "gmail:attachment:private:a1"}],
                "warnings": [
                    "attachment-unreadable:gmail:attachment:private:a2",
                    "PRIVATE DOCUMENT DETAIL",
                ],
                "document_status": "needs-review", "review_required": True,
            }}],
        }
        summary = self.operational.build_shadow_batch_summary(
            records=[record], expected_attachments=2,
            audit={"authorized_attachment_reads": 2, "gmail_mutations": 0},
        )
        self.assertEqual(summary["processed_attachments"], 1)
        self.assertEqual(summary["abstained_attachments"], 1)
        self.assertEqual(summary["warning_code_counts"], {
            "attachment-unreadable": 1, "sanitized-warning": 1,
        })
        serialized = json.dumps(summary, sort_keys=True)
        self.assertNotIn("private", serialized.lower())
        self.assertNotIn("document detail", serialized.lower())

    def test_operational_summary_rejects_actions_or_invalid_audit(self):
        record = {
            "status": "completed", "proposed_actions": [{"action": "write"}],
            "executed_actions": [], "results": [],
        }
        with self.assertRaisesRegex(
            self.operational.ShadowBatchSummaryError,
            "shadow-summary-actions-present",
        ):
            self.operational.build_shadow_batch_summary(
                records=[record], expected_attachments=0, audit={},
            )
        with self.assertRaisesRegex(
            self.operational.ShadowBatchSummaryError,
            "shadow-summary-audit-invalid",
        ):
            self.operational.build_shadow_batch_summary(
                records=[], expected_attachments=0, audit={"gmail_mutations": -1},
            )


if __name__ == "__main__":
    unittest.main()
