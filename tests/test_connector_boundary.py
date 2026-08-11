import copy
import hashlib
import importlib
import json
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
