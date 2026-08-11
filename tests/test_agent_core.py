import copy
import importlib
import json
import shutil
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
DEFAULT_HASHES = {
    "templates/agent/default/template.json": "a21453c96e47a9175fdce36dafb86c9d7ab5304b386790f66acbb838b0a5a058",
    "templates/agent/default/files/__init__.py": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    "templates/agent/default/files/README.md": "4d61a9b92edf3212a8a3d1349837a03f518f0cbd1ad066bd4f6b041b421f14c5",
    "templates/service/default/template.json": "476fad2a2ccea18acefee47241550a40cf3d347603e7debf64b652f59d61cb7f",
    "templates/service/default/files/__init__.py": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    "templates/service/default/files/README.md": "5e74056ec76be5639e10efa51f22640f2fe1fd54d62dabb138d5947beda5c3ea",
}


class GeneratedAgentCoreTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.output = Path(self.temporary.name) / "output"
        self.project = ProjectBuilder(self.output).build("SyntheticOS")
        ServiceBuilder(self.project, "agent-core").build("agent_core")
        AgentBuilder(self.project, "camilo-os-agent").build("invoice-intake")
        sys.path.insert(0, str(self.project))
        self._purge_modules()
        self.runtime = importlib.import_module("services.agent_core.runtime")
        self.models = importlib.import_module("services.agent_core.models")
        self.memory = importlib.import_module("services.agent_core.in_memory")
        self.validation = importlib.import_module("services.agent_core.validation")
        behavior_path = self.project / "agents/invoice-intake/behavior.py"
        spec = importlib.util.spec_from_file_location("synthetic_invoice_behavior", behavior_path)
        self.behavior_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.behavior_module)
        self.definition_path = self.project / "agents/invoice-intake/agent.json"
        self.definition = self.validation.load_agent_definition(self.definition_path)
        self.input_reference = self.models.InputReference(
            "source.synthetic-inbox", "fixture:invoice-message-001"
        )
        self.item = {
            "attachment_ref": "fixture:invoice-attachment-001",
            "invoice_fields": {
                "currency": "EUR", "invoice_number": "SYN-001", "total": "121.00"
            },
        }

    def tearDown(self):
        self._purge_modules()
        if str(self.project) in sys.path:
            sys.path.remove(str(self.project))
        self.temporary.cleanup()

    @staticmethod
    def _purge_modules():
        for name in list(sys.modules):
            if name == "services" or name.startswith("services.agent_core"):
                sys.modules.pop(name, None)

    def _dependencies(self, item=None):
        connector = self.memory.InMemoryConnector({
            self.input_reference.reference: self.item if item is None else item
        })
        approvals = self.memory.InMemoryApprovalGateway()
        store = self.memory.InMemoryExecutionRecordStore()
        behavior = self.behavior_module.InvoiceIntakeBehavior()
        return connector, approvals, store, behavior

    def _run(self, *, definition=None, behavior=None, item=None, operation_key="message-001"):
        connector, approvals, store, default_behavior = self._dependencies(item)
        record = self.runtime.run_agent(
            definition=self.definition if definition is None else definition,
            behavior=default_behavior if behavior is None else behavior,
            connector=connector,
            approval_gateway=approvals,
            record_store=store,
            input_reference=self.input_reference,
            operation_key=operation_key,
        )
        return record, connector, approvals, store

    def test_registered_templates_are_opt_in_and_defaults_are_intact(self):
        registry = TemplateRegistry(ROOT / "templates")
        self.assertEqual(
            [manifest.name for _path, manifest in registry.list("agent")],
            ["camilo-os-agent", "default"],
        )
        self.assertEqual(
            [manifest.name for _path, manifest in registry.list("service")],
            ["agent-core", "default", "google-connectors"],
        )
        import hashlib
        for relative, expected in DEFAULT_HASHES.items():
            self.assertEqual(hashlib.sha256((ROOT / relative).read_bytes()).hexdigest(), expected)

    def test_generation_is_idempotent_and_does_not_overwrite(self):
        readme = self.project / "agents/invoice-intake/README.md"
        readme.write_text("Customized\n", encoding="utf-8")
        before = sorted(path.relative_to(self.project) for path in self.project.rglob("*"))
        ServiceBuilder(self.project, "agent-core").build("agent_core")
        AgentBuilder(self.project, "camilo-os-agent").build("invoice-intake")
        after = sorted(path.relative_to(self.project) for path in self.project.rglob("*"))
        self.assertEqual(before, after)
        self.assertEqual(readme.read_text(encoding="utf-8"), "Customized\n")

    def test_definition_and_record_schemas_are_real_local_consumers(self):
        self.assertEqual(self.definition["schema_version"], 1)
        schemas = self.project / "services/agent_core/schemas"
        self.assertEqual(
            sorted(path.name for path in schemas.glob("*.schema.json")),
            ["agent-definition.schema.json", "execution-record.schema.json"],
        )
        record, *_ = self._run()
        self.assertEqual(self.validation.validate_execution_record(record), record)

    def test_definition_rejects_unknown_properties_and_unordered_actions(self):
        invalid = copy.deepcopy(self.definition)
        invalid["unknown"] = True
        with self.assertRaises(self.validation.DefinitionError):
            self.validation.validate_agent_definition(invalid)
        invalid = copy.deepcopy(self.definition)
        invalid["authorized_actions"] = list(reversed(invalid["authorized_actions"]))
        with self.assertRaisesRegex(self.validation.DefinitionError, "sorted and unique"):
            self.validation.validate_agent_definition(invalid)

    def test_required_action_produces_one_pending_proposal(self):
        record, connector, approvals, _store = self._run()
        self.assertEqual(record["status"], "pending_approval")
        self.assertEqual(len(record["proposed_actions"]), 1)
        self.assertEqual(connector.execution_count, 0)
        self.assertEqual(len(approvals.requests), 1)

    def test_none_action_executes_without_human_approval(self):
        models = self.models

        class Behavior:
            def analyze(self, **_kwargs):
                return models.AgentAnalysis(proposed_actions=({
                    "action_id": "action.classify-document", "parameters": {}
                },))

        record, connector, approvals, _store = self._run(
            behavior=Behavior(), operation_key="classify-only"
        )
        self.assertEqual(record["status"], "completed")
        self.assertEqual(connector.execution_count, 1)
        self.assertEqual(approvals.requests, {})

    def test_approval_executes_once_and_retry_is_idempotent(self):
        record, connector, approvals, store = self._run()
        proposal_id = record["proposed_actions"][0]["proposal_id"]
        approvals.decide(proposal_id, self.models.ApprovalDecision(
            "approved", "human:fixture-reviewer", "fixture:approval-001", "Synthetic approval"
        ))
        approved = self.runtime.resume_agent(
            run_id=record["run_id"], definition=self.definition, connector=connector,
            approval_gateway=approvals, record_store=store,
        )
        retried = self.runtime.resume_agent(
            run_id=record["run_id"], definition=self.definition, connector=connector,
            approval_gateway=approvals, record_store=store,
        )
        self.assertEqual(approved, retried)
        self.assertEqual(approved["status"], "completed")
        self.assertEqual(len(approved["executed_actions"]), 1)
        self.assertEqual(connector.execution_count, 1)

    def test_rejection_records_decision_without_execution(self):
        record, connector, approvals, store = self._run()
        proposal_id = record["proposed_actions"][0]["proposal_id"]
        approvals.decide(proposal_id, self.models.ApprovalDecision(
            "rejected", "human:fixture-reviewer", "fixture:rejection-001"
        ))
        rejected = self.runtime.resume_agent(
            run_id=record["run_id"], definition=self.definition, connector=connector,
            approval_gateway=approvals, record_store=store,
        )
        self.assertEqual(rejected["status"], "completed")
        self.assertEqual(rejected["human_decision"]["decision"], "rejected")
        self.assertEqual(rejected["executed_actions"], [])
        self.assertEqual(connector.execution_count, 0)

    def test_undeclared_and_forbidden_actions_fail_before_connector(self):
        models = self.models

        class Behavior:
            def __init__(self, action_id): self.action_id = action_id
            def analyze(self, **_kwargs):
                return models.AgentAnalysis(proposed_actions=({
                    "action_id": self.action_id, "parameters": {}
                },))
        for action_id, code in (
            ("action.not-declared", "undeclared-action"),
            ("action.delete-source", "forbidden-action"),
        ):
            record, connector, _approvals, _store = self._run(
                behavior=Behavior(action_id), operation_key=action_id
            )
            with self.subTest(action=action_id):
                self.assertEqual(record["status"], "failed")
                self.assertEqual(record["errors"][0]["code"], code)
                self.assertEqual(connector.execution_count, 0)

    def test_forbidden_action_blocks_the_entire_proposal_batch(self):
        models = self.models

        class Behavior:
            def analyze(self, **_kwargs):
                return models.AgentAnalysis(proposed_actions=(
                    {"action_id": "action.classify-document", "parameters": {}},
                    {"action_id": "action.delete-source", "parameters": {}},
                ))

        record, connector, _approvals, _store = self._run(
            behavior=Behavior(), operation_key="mixed-forbidden"
        )
        self.assertEqual(record["status"], "failed")
        self.assertEqual(record["errors"][0]["code"], "forbidden-action")
        self.assertEqual(connector.execution_count, 0)

    def test_ambiguity_and_technical_error_fail_safely(self):
        ambiguous, *_ = self._run(item={"ambiguous": True}, operation_key="ambiguous")
        failed, *_ = self._run(item={"technical_failure": True}, operation_key="failure")
        self.assertEqual(ambiguous["status"], "needs_review")
        self.assertEqual(failed["status"], "failed")
        self.assertEqual(failed["errors"][0]["code"], "technical-error")

    def test_run_and_json_are_deterministic_without_duplicate_records(self):
        record, connector, approvals, store = self._run()
        repeated = self.runtime.run_agent(
            definition=self.definition,
            behavior=self.behavior_module.InvoiceIntakeBehavior(),
            connector=connector,
            approval_gateway=approvals,
            record_store=store,
            input_reference=self.input_reference,
            operation_key="message-001",
        )
        self.assertEqual(record, repeated)
        self.assertEqual(self.runtime.stable_json(record), self.runtime.stable_json(repeated))
        self.assertEqual(len(store._records), 1)
        self.assertEqual(len(record["proposed_actions"]), 1)

    def test_duplicate_behavior_proposals_collapse_to_one_stable_proposal(self):
        models = self.models
        proposal = {
            "action_id": "action.propose-drive-destination",
            "parameters": {"destination_ref": "destination.synthetic-finance"},
        }

        class Behavior:
            def analyze(self, **_kwargs):
                return models.AgentAnalysis(proposed_actions=(proposal, proposal))

        record, connector, approvals, _store = self._run(
            behavior=Behavior(), operation_key="duplicate-proposal"
        )
        self.assertEqual(record["status"], "pending_approval")
        self.assertEqual(len(record["proposed_actions"]), 1)
        self.assertEqual(len(approvals.requests), 1)
        self.assertEqual(connector.execution_count, 0)

    def test_synthetic_pilot_is_offline_secret_free_and_does_not_copy_documents(self):
        with mock.patch.object(socket, "socket", side_effect=AssertionError("network forbidden")):
            record, connector, _approvals, _store = self._run()
        serialized = self.runtime.stable_json(record)
        self.assertEqual(connector.execution_count, 0)
        for forbidden in ("oauth", "token", "password", "gmail", "drive.google", "Grupo Kanui"):
            self.assertNotIn(forbidden.lower(), serialized.lower())
        self.assertNotIn("document_content", serialized)
        self.assertEqual(record["evidence_refs"], [
            "fixture:invoice-attachment-001", "fixture:invoice-message-001"
        ])


if __name__ == "__main__":
    unittest.main()
