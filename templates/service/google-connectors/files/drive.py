from __future__ import annotations

from services.agent_core.errors import UnknownReference
from services.agent_core.models import ConnectorContent, ConnectorItem, InputReference

from .base import ReadOnlyGoogleAdapter


class DriveReadOnlyAdapter(ReadOnlyGoogleAdapter):
    REQUIRED_SCOPES = frozenset({"drive.readonly"})

    def list_items(self, *, source_id):
        self._authorize("item.list")
        credential = self._credential()
        values = self._call(self._client.list_files, access_token=credential.access_token, source_id=source_id)
        return tuple(ConnectorItem(
            reference=f"drive:file:{item['id']}",
            metadata={key: item[key] for key in ("name", "media_type") if key in item},
            content_refs=(f"drive:content:{item['id']}",),
        ) for item in sorted(values, key=lambda value: value["id"]))

    def read(self, reference: InputReference):
        self._authorize("item.metadata.read")
        prefix = "drive:file:"
        if not reference.reference.startswith(prefix):
            raise UnknownReference(provider_id=self.provider_id, connector_id=self.connector_id, message="Unknown Drive reference")
        credential = self._credential()
        item = self._call(self._client.get_file, access_token=credential.access_token, file_id=reference.reference[len(prefix):])
        return {"reference": reference.reference, "metadata": {key: item[key] for key in ("name", "media_type", "size") if key in item}, "content_refs": [f"drive:content:{item['id']}"]}

    def read_content(self, reference):
        self._authorize("content.read")
        prefix = "drive:content:"
        if not reference.startswith(prefix):
            raise UnknownReference(provider_id=self.provider_id, connector_id=self.connector_id, message="Unknown Drive content reference")
        credential = self._credential()
        value = self._call(self._client.get_content, access_token=credential.access_token, file_id=reference[len(prefix):])
        return ConnectorContent(reference, value["media_type"], bytes(value["content"]))
