import copy
import base64
import hashlib
import importlib
import json
import socket
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from jsonschema import Draft202012Validator

from builders.agent_builder import AgentBuilder
from builders.project_builder import ProjectBuilder
from builders.service_builder import ServiceBuilder
from template_system.registry import TemplateRegistry
from tests.invoice_pdf_fixtures import textual_pdf


ROOT = Path(__file__).resolve().parents[1]
PROTECTED_DEFAULTS = {
    path: hashlib.sha256((ROOT / path).read_bytes()).hexdigest()
    for path in (
        "templates/agent/default/template.json", "templates/agent/default/files/__init__.py",
        "templates/agent/default/files/README.md", "templates/service/default/template.json",
        "templates/service/default/files/__init__.py", "templates/service/default/files/README.md",
    )
}


class GmailClient:
    def __init__(self): self.calls = []
    def list_messages(self, **kwargs): self.calls.append(("list", kwargs)); return [{"id": "m1", "from": "synthetic@example.invalid", "subject": "Invoice", "attachment_ids": ["a1"]}]
    def get_message(self, **kwargs): self.calls.append(("get", kwargs)); return {"id": "m1", "from": "synthetic@example.invalid", "subject": "Invoice", "body": "Synthetic", "attachment_ids": ["a1"], "attachments": [{"id": "a1", "filename": "synthetic-invoice.pdf"}]}
    def get_attachment(self, **kwargs): self.calls.append(("attachment", kwargs)); return {"media_type": "application/pdf", "content": b"synthetic-pdf"}
    def send(self, **kwargs): raise AssertionError("mutator called")


class DriveClient:
    def __init__(self): self.calls = []
    def list_files(self, **kwargs): self.calls.append(("list", kwargs)); return [{"id": "f1", "name": "synthetic.pdf", "media_type": "application/pdf"}]
    def get_file(self, **kwargs): self.calls.append(("get", kwargs)); return {"id": "f1", "name": "synthetic.pdf", "media_type": "application/pdf", "size": 13}
    def get_content(self, **kwargs): self.calls.append(("content", kwargs)); return {"media_type": "application/pdf", "content": b"synthetic-drive"}
    def create(self, **kwargs): raise AssertionError("mutator called")


class ConnectorBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.project = ProjectBuilder(Path(self.temporary.name) / "output").build("SyntheticOS")
        ServiceBuilder(self.project, "agent-core").build("agent_core")
        ServiceBuilder(self.project, "google-connectors").build("google_connectors")
        ServiceBuilder(self.project, "invoice-intake").build("invoice_intake")
        AgentBuilder(self.project, "camilo-os-agent").build("invoice-intake")
        sys.path.insert(0, str(self.project)); self._purge()
        self.models = importlib.import_module("services.agent_core.models")
        self.errors = importlib.import_module("services.agent_core.errors")
        self.secrets = importlib.import_module("services.agent_core.secrets")
        self.sqlite = importlib.import_module("services.agent_core.sqlite_store")
        self.runtime = importlib.import_module("services.agent_core.runtime")
        self.memory = importlib.import_module("services.agent_core.in_memory")
        self.validation = importlib.import_module("services.agent_core.validation")
        self.deployment = importlib.import_module("services.google_connectors.deployment")
        self.factory_module = importlib.import_module("services.google_connectors.factory")
        self.gmail_client, self.drive_client = GmailClient(), DriveClient()
        self.gmail_byte_only = importlib.import_module("services.google_connectors.gmail_byte_only")
        self.gmail_discovery = importlib.import_module("services.google_connectors.gmail_discovery")
        self.pilot_manifest = importlib.import_module("services.google_connectors.pilot_manifest")
        self.integrity = importlib.import_module("services.invoice_intake.integrity")
        self.credential = self.secrets.CredentialMaterial("SYNTHETIC-SECRET", frozenset({"gmail.readonly", "drive.readonly"}))
        self.secret_provider = self.secrets.FakeSecretProvider({"secret-ref:test/google": self.credential})
        self.config = {"schema_version": 1, "connectors": [
            {"alias": "connector.drive-test", "adapter": "google.drive.readonly", "credential_ref": "secret-ref:test/google", "permissions": ["content.read", "item.list", "item.metadata.read"], "settings": {"root_reference": "synthetic-root"}},
            {"alias": "connector.gmail-test", "adapter": "google.gmail.readonly", "credential_ref": "secret-ref:test/google", "permissions": ["content.read", "item.list", "item.metadata.read"], "settings": {"account_alias": "synthetic"}},
        ]}

    def tearDown(self):
        self._purge(); sys.path.remove(str(self.project)); self.temporary.cleanup()

    @staticmethod
    def _purge():
        for name in list(sys.modules):
            if name == "services" or name.startswith("services."): sys.modules.pop(name, None)

    def _factory(self, config=None, provider=None):
        return self.factory_module.ConnectorFactory(configuration=self.config if config is None else config, clients={"google.gmail.readonly": self.gmail_client, "google.drive.readonly": self.drive_client}, secret_provider=self.secret_provider if provider is None else provider)

    def test_templates_are_registered_without_new_component_type_and_defaults_unchanged(self):
        registry = TemplateRegistry(ROOT / "templates")
        self.assertEqual([m.name for _, m in registry.list("service")], ["agent-core", "default", "google-connectors", "invoice-intake"])
        self.assertEqual(sorted(path.name for path in (ROOT / "templates").iterdir()), ["agent", "department", "project", "service"])
        for path, digest in PROTECTED_DEFAULTS.items(): self.assertEqual(hashlib.sha256((ROOT / path).read_bytes()).hexdigest(), digest)

    def test_generation_is_idempotent_and_does_not_overwrite(self):
        readme = self.project / "services/google_connectors/README.md"; readme.write_text("custom\n", encoding="utf-8")
        before = sorted(p.relative_to(self.project) for p in self.project.rglob("*"))
        ServiceBuilder(self.project, "google-connectors").build("google_connectors")
        self.assertEqual(before, sorted(p.relative_to(self.project) for p in self.project.rglob("*")))
        self.assertEqual(readme.read_text(encoding="utf-8"), "custom\n")

    def test_deployment_configuration_schema_is_closed_and_secret_free(self):
        path = self.project / "deployment.json"; path.write_text(json.dumps(self.config), encoding="utf-8")
        self.assertEqual(self.deployment.load_deployment_configuration(path), self.config)
        invalid = copy.deepcopy(self.config); invalid["token"] = "forbidden"
        path.write_text(json.dumps(invalid), encoding="utf-8")
        with self.assertRaises(self.deployment.DeploymentConfigurationError): self.deployment.load_deployment_configuration(path)
        schema = (self.project / "services/google_connectors/schemas/deployment-connectors.schema.json").read_text()
        self.assertNotIn('"token"', schema); self.assertNotIn('"client_secret"', schema)

    def test_gmail_and_drive_read_only_return_opaque_minimal_values(self):
        factory = self._factory(); gmail = factory.resolve("connector.gmail-test"); drive = factory.resolve("connector.drive-test")
        self.assertEqual(gmail.list_items(source_id="source.synthetic")[0].reference, "gmail:message:m1")
        message = gmail.read(self.models.InputReference("source.synthetic", "gmail:message:m1"))
        self.assertEqual(message["content_refs"], ["gmail:attachment:m1:a1"])
        self.assertEqual(message["attachment_filenames"], {"gmail:attachment:m1:a1": "synthetic-invoice.pdf"})
        self.assertEqual(gmail.read_content("gmail:attachment:m1:a1").content, b"synthetic-pdf")
        self.assertEqual(drive.list_items(source_id="source.synthetic")[0].reference, "drive:file:f1")
        self.assertEqual(drive.read(self.models.InputReference("source.synthetic", "drive:file:f1"))["content_refs"], ["drive:content:f1"])
        self.assertEqual(drive.read_content("drive:content:f1").content, b"synthetic-drive")
        for adapter, client in ((gmail, self.gmail_client), (drive, self.drive_client)):
            before = list(client.calls)
            with self.assertRaises(self.errors.CapabilityDenied): adapter.execute(action_id="action.write", parameters={}, idempotency_key="key")
            self.assertEqual(client.calls, before)

    def test_gmail_base64url_boundary_returns_exact_original_bytes(self):
        original = b"%PDF-1.7\nsynthetic bytes only\n%%EOF\n"
        encoded = base64.urlsafe_b64encode(original).decode("ascii").rstrip("=")
        self.gmail_client.get_attachment = mock.Mock(return_value={"media_type": "application/pdf", "data": encoded})
        content = self._factory().resolve("connector.gmail-test").read_content("gmail:attachment:m1:a1")
        self.assertEqual(content.content, original)
        self.assertFalse(content.content.startswith(b"Content-Type:"))

    def test_closed_manifest_and_byte_only_client_prove_content_free_integrity(self):
        case = {
            "case_id": "REAL-SYNTHETIC-001", "provider": "gmail",
            "message_ref": "gmail:message:m1", "attachment_ref": "gmail:attachment:m1:a1",
            "expected_media_type": "application/pdf", "purpose": "shadow_pilot",
            "authorized_on": "2026-08-14", "ground_truth_status": "authorized",
        }
        path = Path(self.temporary.name) / "pilot-real-manifest.json"
        path.write_text(json.dumps({"format": "camilo-os.real-pilot-manifest", "format_version": 1, "cases": [case]}), encoding="utf-8")
        manifest = self.pilot_manifest.load_pilot_manifest(path)
        schema = json.loads((self.project / "services/google_connectors/schemas/real-pilot-manifest.schema.json").read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
        self.assertEqual(list(Draft202012Validator(schema).iter_errors(manifest)), [])
        allowlist = self.pilot_manifest.attachment_allowlist(manifest)
        pdf = textual_pdf(["FACTURA", "Numero: SYN-001", "Total: 12,10 EUR"])
        encoded = base64.urlsafe_b64encode(pdf).decode("ascii").rstrip("=")
        calls = []

        class Response:
            def __enter__(self): return self
            def __exit__(self, *_args): pass
            def read(self, _limit): return json.dumps({"data": encoded, "size": len(pdf)}, separators=(",", ":")).encode()

        def opener(request, *, timeout):
            calls.append((request, timeout)); return Response()

        client = self.gmail_byte_only.GmailByteOnlyAttachmentClient(attachment_media_types=allowlist, opener=opener)
        factory = self.factory_module.ConnectorFactory(
            configuration=self.config,
            clients={"google.gmail.readonly": client, "google.drive.readonly": self.drive_client},
            secret_provider=self.secret_provider,
        )
        content = factory.resolve("connector.gmail-test").read_content(case["attachment_ref"])
        report = self.integrity.build_integrity_report(
            case=case, raw_observation=client.observation(case["attachment_ref"]), connector_content=content,
        )
        self.assertEqual(content.content, pdf)
        self.assertEqual(report["equalities"], {"B_equals_C": True, "C_equals_D": True, "D_equals_E": True})
        self.assertEqual(report["stages"]["D"]["validation"], "strict-valid")
        self.assertEqual(report["stages"]["D"]["pages"], 1)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][0].get_method(), "GET")
        self.assertTrue(calls[0][0].full_url.endswith("/messages/m1/attachments/a1"))
        serialized = json.dumps(report, sort_keys=True)
        self.assertNotIn(encoded, serialized)
        self.assertNotIn("SYNTHETIC-SECRET", serialized)
        self.assertNotIn("SYN-001", serialized)

    def test_gmail_discovery_builds_a_bounded_content_free_manifest(self):
        calls = []

        class Response:
            def __init__(self, value): self.value = value
            def __enter__(self): return self
            def __exit__(self, *_args): pass
            def read(self, _limit): return json.dumps(self.value, separators=(",", ":")).encode()

        def opener(request, *, timeout):
            calls.append((request, timeout))
            if "?q=" in request.full_url:
                return Response({"messages": [{"id": "m1"}]})
            return Response({"id": "m1", "payload": {"parts": [
                {"filename": "invoice.pdf", "mimeType": "application/pdf", "body": {"attachmentId": "a1"}},
                {"filename": "body.txt", "mimeType": "text/plain", "body": {}},
                {"filename": "nested", "mimeType": "multipart/mixed", "body": {}, "parts": [
                    {"filename": "invoice.xml", "mimeType": "application/xml", "body": {"attachmentId": "a2"}},
                ]},
            ]}})

        client = self.gmail_discovery.GmailInvoiceDiscoveryClient(opener=opener)
        manifest = client.discover(access_token="SYNTHETIC-SECRET", max_messages=5, authorized_on="2026-08-15")
        self.assertEqual(len(manifest["cases"]), 2)
        self.assertEqual({case["attachment_ref"] for case in manifest["cases"]}, {
            "gmail:attachment:m1:a1", "gmail:attachment:m1:a2",
        })
        self.assertEqual({case["ground_truth_status"] for case in manifest["cases"]}, {"pending"})
        serialized = json.dumps(manifest, sort_keys=True)
        self.assertNotIn("invoice.pdf", serialized)
        self.assertNotIn("body.txt", serialized)
        self.assertNotIn("SYNTHETIC-SECRET", serialized)
        self.assertEqual(client.audit_summary(), {
            "list_requests": 1, "message_metadata_reads": 1, "gmail_mutations": 0,
            "unread_changes": 0, "label_changes": 0, "drive_writes": 0,
        })
        self.assertTrue(all(call[0].get_method() == "GET" for call in calls))
        self.assertIn("messages%2Fid", calls[0][0].full_url)
        self.assertIn("fields=", calls[1][0].full_url)
        self.assertNotIn("snippet", calls[1][0].full_url)

    def test_gmail_discovery_rejects_unbounded_or_contaminated_responses(self):
        client = self.gmail_discovery.GmailInvoiceDiscoveryClient(opener=lambda *_args, **_kwargs: None)
        with self.assertRaisesRegex(self.gmail_discovery.GmailDiscoveryError, "gmail-discovery-limit-invalid"):
            client.discover(access_token="secret", max_messages=16)

        class Response:
            def __enter__(self): return self
            def __exit__(self, *_args): pass
            def read(self, _limit): return b'{"messages":[{"id":"m1","snippet":"forbidden"}]}'

        client = self.gmail_discovery.GmailInvoiceDiscoveryClient(opener=lambda *_args, **_kwargs: Response())
        with self.assertRaisesRegex(self.gmail_discovery.GmailDiscoveryError, "gmail-discovery-response-invalid"):
            client.discover(access_token="secret")

    def test_manifest_allowlist_and_byte_only_response_fail_closed(self):
        cases = [
            {"case_id": "REAL-SYNTHETIC-002", "provider": "gmail", "message_ref": "gmail:message:m2", "attachment_ref": "gmail:attachment:m2:a2", "expected_media_type": "application/pdf", "purpose": "integrity_check", "authorized_on": "2026-08-14", "ground_truth_status": "pending"},
            {"case_id": "REAL-SYNTHETIC-001", "provider": "gmail", "message_ref": "gmail:message:m1", "attachment_ref": "gmail:attachment:m1:a1", "expected_media_type": "application/pdf", "purpose": "shadow_pilot", "authorized_on": "2026-08-14", "ground_truth_status": "authorized"},
        ]
        path = Path(self.temporary.name) / "pilot-real-manifest.json"
        path.write_text(json.dumps({"format": "camilo-os.real-pilot-manifest", "format_version": 1, "cases": cases}), encoding="utf-8")
        with self.assertRaisesRegex(self.pilot_manifest.PilotManifestError, "pilot-manifest-order-invalid"):
            self.pilot_manifest.load_pilot_manifest(path)
        cases.sort(key=lambda value: value["case_id"])
        cases[0]["attachment_ref"] = "gmail:attachment:other:a1"
        path.write_text(json.dumps({"format": "camilo-os.real-pilot-manifest", "format_version": 1, "cases": cases}), encoding="utf-8")
        with self.assertRaisesRegex(self.pilot_manifest.PilotManifestError, "pilot-manifest-invalid"):
            self.pilot_manifest.load_pilot_manifest(path)
        cases[0]["message_ref"] = "gmail:message:m1"
        cases[0]["attachment_ref"] = "gmail:attachment:m1:a1"
        cases[0]["authorized_on"] = "2026-02-31"
        path.write_text(json.dumps({"format": "camilo-os.real-pilot-manifest", "format_version": 1, "cases": cases}), encoding="utf-8")
        with self.assertRaisesRegex(self.pilot_manifest.PilotManifestError, "pilot-manifest-invalid"):
            self.pilot_manifest.load_pilot_manifest(path)
        calls = []
        client = self.gmail_byte_only.GmailByteOnlyAttachmentClient(
            attachment_media_types={"gmail:attachment:m1:a1": "application/pdf"},
            opener=lambda *_args, **_kwargs: calls.append(True),
        )
        with self.assertRaisesRegex(self.gmail_byte_only.GmailByteOnlyError, "gmail-attachment-not-authorized"):
            client.get_attachment(access_token="SYNTHETIC-SECRET", message_id="m9", attachment_id="a9")
        self.assertEqual(calls, [])

        class InvalidResponse:
            def __enter__(self): return self
            def __exit__(self, *_args): pass
            def read(self, _limit): return b'{"data":"c2VjcmV0","preview":"forbidden"}'

        client = self.gmail_byte_only.GmailByteOnlyAttachmentClient(
            attachment_media_types={"gmail:attachment:m1:a1": "application/pdf"},
            opener=lambda *_args, **_kwargs: InvalidResponse(),
        )
        with self.assertRaisesRegex(self.gmail_byte_only.GmailByteOnlyError, "gmail-attachment-response-invalid") as caught:
            client.get_attachment(access_token="SYNTHETIC-SECRET", message_id="m1", attachment_id="a1")
        self.assertNotIn("SYNTHETIC-SECRET", str(caught.exception))
        self.assertNotIn("c2VjcmV0", str(caught.exception))

        content = self.models.ConnectorContent("gmail:attachment:m1:a1", "application/pdf", textual_pdf(["SYNTHETIC"]))
        contaminated = {
            "representation": "gmail-base64url", "response_size_bytes": 10,
            "encoded_size_bytes": 8, "encoded_sha256": "0" * 64,
            "declared_decoded_size": len(content.content), "expected_media_type": "application/pdf",
            "data": "forbidden",
        }
        valid_case = {
            "case_id": "REAL-SYNTHETIC-001", "attachment_ref": "gmail:attachment:m1:a1",
            "expected_media_type": "application/pdf",
        }
        with self.assertRaisesRegex(ValueError, "integrity-raw-observation-invalid"):
            self.integrity.build_integrity_report(case=valid_case, raw_observation=contaminated, connector_content=content)

    def test_gmail_rejects_invalid_ambiguous_and_oversized_payloads_safely(self):
        gmail = self._factory().resolve("connector.gmail-test")
        invalid = (
            {"media_type": "application/pdf", "data": "%%%"},
            {"media_type": "application/pdf", "content": b"one", "data": "dHdv"},
            {"media_type": "application/pdf", "content": b"one", "size": 4},
            {"media_type": "application/pdf", "data": "A" * 11_184_817},
        )
        for payload in invalid:
            with self.subTest(keys=sorted(payload)):
                self.gmail_client.get_attachment = mock.Mock(return_value=payload)
                with self.assertRaises(self.errors.ProviderRejected) as caught:
                    gmail.read_content("gmail:attachment:m1:a1")
                self.assertEqual(str(caught.exception), "provider-rejected: Provider attachment payload is invalid")

    def test_unknown_alias_reference_and_adapter_fail_safely(self):
        with self.assertRaises(self.errors.UnknownReference): self._factory().resolve("connector.missing")
        malformed = copy.deepcopy(self.config); malformed["connectors"][0]["adapter"] = "unknown"
        with self.assertRaises(self.errors.UnknownReference): self._factory(malformed).resolve("connector.drive-test")
        gmail = self._factory().resolve("connector.gmail-test")
        with self.assertRaises(self.errors.UnknownReference): gmail.read(self.models.InputReference("source.synthetic", "drive:file:f1"))

    def test_deployment_permission_and_provider_errors_fail_safely(self):
        restricted = copy.deepcopy(self.config); restricted["connectors"][1]["permissions"] = ["item.metadata.read"]
        with self.assertRaises(self.errors.CapabilityDenied): self._factory(restricted).resolve("connector.gmail-test").list_items(source_id="source.synthetic")
        self.gmail_client.list_messages = mock.Mock(side_effect=TimeoutError("SYNTHETIC-SECRET"))
        with self.assertRaises(self.errors.ProviderUnavailable) as unavailable:
            self._factory().resolve("connector.gmail-test").list_items(source_id="source.synthetic")
        self.assertTrue(unavailable.exception.retryable); self.assertNotIn("SYNTHETIC-SECRET", str(unavailable.exception))
        self.gmail_client.list_messages = mock.Mock(side_effect=RuntimeError("SYNTHETIC-SECRET"))
        with self.assertRaises(self.errors.ProviderRejected) as rejected:
            self._factory().resolve("connector.gmail-test").list_items(source_id="source.synthetic")
        self.assertFalse(rejected.exception.retryable); self.assertNotIn("SYNTHETIC-SECRET", str(rejected.exception))

    def test_missing_expired_and_insufficient_credentials_are_sanitized(self):
        cases = [
            (self.secrets.FakeSecretProvider(), self.errors.AuthenticationRequired),
            (self.secrets.FakeSecretProvider({"secret-ref:test/google": self.secrets.CredentialMaterial("SECRET-A", frozenset({"gmail.readonly"}), expired=True)}), self.errors.CredentialExpired),
            (self.secrets.FakeSecretProvider({"secret-ref:test/google": self.secrets.CredentialMaterial("SECRET-B", frozenset())}), self.errors.InsufficientScope),
        ]
        for provider, error_type in cases:
            with self.subTest(error=error_type.__name__):
                adapter = self._factory(provider=provider).resolve("connector.gmail-test")
                with self.assertRaises(error_type) as caught: adapter.list_items(source_id="source.synthetic")
                text = f"{caught.exception!r} {caught.exception}"
                self.assertNotIn("SECRET", text)
        self.assertEqual(repr(self.credential), "CredentialMaterial(<redacted>)")
        self.assertNotIn("SYNTHETIC-SECRET", str(self.credential))

    def test_triple_permission_intersection_denies_each_missing_layer(self):
        definition = self.validation.load_agent_definition(self.project / "agents/invoice-intake/agent.json")
        source = definition["authorized_sources"][0]; source["permissions"] = ["content.read"]
        for kwargs in (
            {"operation": "item.list", "deployment_permissions": {"item.list"}, "adapter_capabilities": {"item.list"}},
            {"operation": "content.read", "deployment_permissions": set(), "adapter_capabilities": {"content.read"}},
            {"operation": "content.read", "deployment_permissions": {"content.read"}, "adapter_capabilities": set()},
        ):
            with self.assertRaises(self.errors.CapabilityDenied): self.runtime.authorize_connector_operation(definition=definition, source_id=source["source_id"], **kwargs)
        self.runtime.authorize_connector_operation(definition=definition, source_id=source["source_id"], operation="content.read", deployment_permissions={"content.read"}, adapter_capabilities={"content.read"})

    def test_resolver_enforces_the_three_permission_layers_before_provider(self):
        definition = self.validation.load_agent_definition(self.project / "agents/invoice-intake/agent.json")
        source = definition["authorized_sources"][0]
        source["connector_id"] = "connector.gmail-test"
        source["permissions"] = ["item.metadata.read"]
        connector = self._factory().resolve_for_agent(definition=definition, source_id=source["source_id"])
        connector.read(self.models.InputReference(source["source_id"], "gmail:message:m1"))
        before = list(self.gmail_client.calls)
        with self.assertRaises(self.errors.CapabilityDenied): connector.read_content("gmail:attachment:m1:a1")
        with self.assertRaises(self.errors.CapabilityDenied): connector.execute(action_id="action.write", parameters={}, idempotency_key="key")
        self.assertEqual(self.gmail_client.calls, before)

    def test_sqlite_create_cas_reopen_and_restart_idempotency(self):
        path = Path(self.temporary.name) / "records.sqlite3"
        definition = self.validation.load_agent_definition(self.project / "agents/invoice-intake/agent.json")
        connector = self.memory.InMemoryConnector({"fixture:input": {"ambiguous": True}})
        approvals = self.memory.InMemoryApprovalGateway()
        behavior_path = self.project / "agents/invoice-intake/behavior.py"
        spec = importlib.util.spec_from_file_location("behavior_restart", behavior_path); behavior_module = importlib.util.module_from_spec(spec); spec.loader.exec_module(behavior_module)
        store = self.sqlite.SQLiteExecutionRecordStore(path)
        record = self.runtime.run_agent(definition=definition, behavior=behavior_module.InvoiceIntakeBehavior(), connector=connector, approval_gateway=approvals, record_store=store, input_reference=self.models.InputReference("source.synthetic-inbox", "fixture:input"), operation_key="restart")
        with self.assertRaises(self.errors.DuplicateRunError): store.create(record)
        stale = copy.deepcopy(record); store.replace(stale, expected_revision=1)
        with self.assertRaises(self.errors.ConcurrentUpdateError): store.replace(stale, expected_revision=1)
        store.close(); reopened = self.sqlite.SQLiteExecutionRecordStore(path)
        repeated = self.runtime.run_agent(definition=definition, behavior=behavior_module.InvoiceIntakeBehavior(), connector=connector, approval_gateway=approvals, record_store=reopened, input_reference=self.models.InputReference("source.synthetic-inbox", "fixture:input"), operation_key="restart")
        self.assertEqual(repeated["run_id"], record["run_id"]); self.assertEqual(len(reopened._connection.execute("SELECT run_id FROM execution_records").fetchall()), 1); reopened.close()
        self.assertNotIn("SYNTHETIC-SECRET", path.read_bytes().decode("latin1"))

    def test_external_approval_structure_does_not_expand_permissions(self):
        decision = self.models.ApprovalDecision("approved", actor_reference="actor:declared", decision_ref="external:decision-1", notes="note", decided_at="2026-08-11T10:00:00Z")
        self.assertEqual(decision.as_dict()["decided_by"], "actor:declared")
        self.assertNotIn("decided_at", decision.as_dict())
        definition = self.validation.load_agent_definition(self.project / "agents/invoice-intake/agent.json")
        with self.assertRaises(self.errors.CapabilityDenied): self.runtime.authorize_connector_operation(definition=definition, source_id="source.synthetic-inbox", operation="content.write", deployment_permissions={"content.write"}, adapter_capabilities={"content.write"})

    def test_connector_suite_is_offline_and_secret_free(self):
        with mock.patch.object(socket, "socket", side_effect=AssertionError("network forbidden")):
            self._factory().resolve("connector.gmail-test").list_items(source_id="source.synthetic")
        serialized = json.dumps(self.config, sort_keys=True)
        self.assertNotIn("SYNTHETIC-SECRET", serialized)

    def test_records_and_technical_errors_cannot_leak_sensitive_material(self):
        definition = self.validation.load_agent_definition(self.project / "agents/invoice-intake/agent.json")
        connector = self.memory.InMemoryConnector({"fixture:secret-error": {}})
        approvals = self.memory.InMemoryApprovalGateway(); store = self.memory.InMemoryExecutionRecordStore()

        class FailingBehavior:
            def analyze(self, **_kwargs): raise RuntimeError("SYNTHETIC-SECRET")

        record = self.runtime.run_agent(definition=definition, behavior=FailingBehavior(), connector=connector, approval_gateway=approvals, record_store=store, input_reference=self.models.InputReference("source.synthetic-inbox", "fixture:secret-error"), operation_key="secret-error")
        self.assertNotIn("SYNTHETIC-SECRET", self.runtime.stable_json(record))
        contaminated = copy.deepcopy(record); contaminated["results"] = [{"result_id": "result.secret", "kind": "test", "value": {"access_token": "SYNTHETIC-SECRET"}}]
        with self.assertRaises(self.errors.RecordError): self.validation.validate_execution_record(contaminated)

    def test_generated_technical_pilot_persists_reopens_and_retries_without_external_writes(self):
        factory = self._factory()
        gmail = factory.resolve("connector.gmail-test"); drive = factory.resolve("connector.drive-test")
        with mock.patch.object(socket, "socket", side_effect=AssertionError("network forbidden")):
            message = gmail.read(self.models.InputReference("source.synthetic", "gmail:message:m1"))
            attachment = gmail.read_content(message["content_refs"][0])
            drive_file = drive.read(self.models.InputReference("source.synthetic", "drive:file:f1"))
            drive_content = drive.read_content(drive_file["content_refs"][0])
        self.assertEqual((attachment.content, drive_content.content), (b"synthetic-pdf", b"synthetic-drive"))

        behavior_path = self.project / "agents/invoice-intake/behavior.py"
        spec = importlib.util.spec_from_file_location("pilot_behavior", behavior_path); behavior_module = importlib.util.module_from_spec(spec); spec.loader.exec_module(behavior_module)
        definition = self.validation.load_agent_definition(self.project / "agents/invoice-intake/agent.json")
        action_connector = self.memory.InMemoryConnector({"fixture:pilot": {"attachment_ref": message["content_refs"][0], "invoice_fields": {"invoice_number": "SYN-PILOT", "total": "10.00", "currency": "EUR"}}})
        approvals = self.memory.InMemoryApprovalGateway(); path = Path(self.temporary.name) / "pilot.sqlite3"
        store = self.sqlite.SQLiteExecutionRecordStore(path)
        pending = self.runtime.run_agent(definition=definition, behavior=behavior_module.InvoiceIntakeBehavior(), connector=action_connector, approval_gateway=approvals, record_store=store, input_reference=self.models.InputReference("source.synthetic-inbox", "fixture:pilot"), operation_key="pilot")
        self.assertEqual(pending["status"], "pending_approval"); store.close()
        reopened = self.sqlite.SQLiteExecutionRecordStore(path); proposal_id = pending["proposed_actions"][0]["proposal_id"]
        approvals.decide(proposal_id, self.models.ApprovalDecision("approved", actor_reference="actor:synthetic-reviewer", decision_ref="fixture:decision"))
        completed = self.runtime.resume_agent(run_id=pending["run_id"], definition=definition, connector=action_connector, approval_gateway=approvals, record_store=reopened)
        retried = self.runtime.resume_agent(run_id=pending["run_id"], definition=definition, connector=action_connector, approval_gateway=approvals, record_store=reopened)
        self.assertEqual(completed, retried); self.assertEqual(action_connector.execution_count, 1)
        with self.assertRaises(self.errors.CapabilityDenied): gmail.execute(action_id="action.gmail.modify", parameters={}, idempotency_key="pilot-write")
        reopened.close(); persisted = path.read_bytes().decode("latin1")
        self.assertNotIn("SYNTHETIC-SECRET", persisted)
        self.assertEqual(len(self.gmail_client.calls), 2); self.assertEqual(len(self.drive_client.calls), 2)


if __name__ == "__main__": unittest.main()
