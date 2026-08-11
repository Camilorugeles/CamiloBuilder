from __future__ import annotations

from services.agent_core.errors import UnknownReference
from services.agent_core.models import ConnectorContent, ConnectorItem, InputReference

from .base import ReadOnlyGoogleAdapter


class GmailReadOnlyAdapter(ReadOnlyGoogleAdapter):
    REQUIRED_SCOPES = frozenset({"gmail.readonly"})

    def list_items(self, *, source_id):
        self._authorize("item.list")
        credential = self._credential()
        values = self._call(self._client.list_messages, access_token=credential.access_token, source_id=source_id)
        return tuple(ConnectorItem(
            reference=f"gmail:message:{item['id']}",
            metadata={key: item[key] for key in ("from", "subject") if key in item},
            content_refs=tuple(sorted(f"gmail:attachment:{item['id']}:{value}" for value in item.get("attachment_ids", ()))),
        ) for item in sorted(values, key=lambda value: value["id"]))

    def read(self, reference: InputReference):
        self._authorize("item.metadata.read")
        prefix = "gmail:message:"
        if not reference.reference.startswith(prefix):
            raise UnknownReference(provider_id=self.provider_id, connector_id=self.connector_id, message="Unknown Gmail reference")
        credential = self._credential()
        item = self._call(self._client.get_message, access_token=credential.access_token, message_id=reference.reference[len(prefix):])
        attachments = item.get("attachments", ())
        attachment_ids = item.get("attachment_ids", ()) or tuple(value["id"] for value in attachments)
        filenames = {
            f"gmail:attachment:{item['id']}:{value['id']}": value["filename"]
            for value in attachments if value.get("id") and value.get("filename")
        }
        return {
            "reference": reference.reference,
            "metadata": {key: item[key] for key in ("from", "subject") if key in item},
            "body": item.get("body", ""),
            "content_refs": sorted(f"gmail:attachment:{item['id']}:{value}" for value in attachment_ids),
            "attachment_filenames": dict(sorted(filenames.items())),
        }

    def read_content(self, reference):
        self._authorize("content.read")
        parts = reference.split(":", 3)
        if len(parts) != 4 or parts[:2] != ["gmail", "attachment"]:
            raise UnknownReference(provider_id=self.provider_id, connector_id=self.connector_id, message="Unknown Gmail content reference")
        credential = self._credential()
        value = self._call(self._client.get_attachment, access_token=credential.access_token, message_id=parts[2], attachment_id=parts[3])
        return ConnectorContent(reference, value["media_type"], bytes(value["content"]))
