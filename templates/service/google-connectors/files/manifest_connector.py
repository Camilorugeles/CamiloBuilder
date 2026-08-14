from __future__ import annotations

from services.agent_core.errors import CapabilityDenied, UnknownReference
from services.agent_core.models import ConnectorItem


class ManifestBoundGmailConnector:
    """Expose only manifest entries while delegating allowlisted attachment bytes."""

    def __init__(self, *, manifest, content_connector):
        self.connector_id = content_connector.connector_id
        self.provider_id = "google"
        self._content_connector = content_connector
        self._cases = tuple(dict(case) for case in manifest["cases"])
        self._attachment_reads = 0
        self._manifest_reads = 0

    def capabilities(self):
        return frozenset({"content.read", "item.list", "item.metadata.read"})

    def _message_cases(self, reference):
        matches = tuple(case for case in self._cases if case["message_ref"] == reference)
        if not matches:
            raise UnknownReference(provider_id=self.provider_id, connector_id=self.connector_id, message="Reference is outside the closed pilot manifest")
        return matches

    def list_items(self, *, source_id):
        items = []
        for message_ref in sorted({case["message_ref"] for case in self._cases}):
            cases = self._message_cases(message_ref)
            items.append(ConnectorItem(
                reference=message_ref,
                metadata={"manifest_case_ids": tuple(case["case_id"] for case in cases)},
                content_refs=tuple(case["attachment_ref"] for case in cases),
            ))
        return tuple(items)

    def read(self, reference):
        cases = self._message_cases(reference.reference)
        self._manifest_reads += 1
        return {
            "reference": reference.reference,
            "metadata": {"manifest_owner": cases[0]["case_id"]},
            "body": "",
            "content_refs": [case["attachment_ref"] for case in cases],
            "attachment_filenames": {
                case["attachment_ref"]: f"{case['case_id']}." + (
                    "pdf" if case["expected_media_type"] == "application/pdf" else "xml"
                )
                for case in cases
            },
        }

    def read_content(self, reference):
        if reference not in {case["attachment_ref"] for case in self._cases}:
            raise UnknownReference(provider_id=self.provider_id, connector_id=self.connector_id, message="Attachment is outside the closed pilot manifest")
        self._attachment_reads += 1
        return self._content_connector.read_content(reference)

    def execute(self, *, action_id, parameters, idempotency_key):
        raise CapabilityDenied(provider_id=self.provider_id, connector_id=self.connector_id, message="The closed pilot connector is read-only")

    def audit_summary(self):
        return {
            "manifest_reads": self._manifest_reads,
            "authorized_attachment_reads": self._attachment_reads,
            "messages_outside_manifest": 0,
            "attachments_outside_manifest": 0,
            "gmail_mutations": 0,
            "unread_changes": 0,
            "label_changes": 0,
            "drive_writes": 0,
        }
