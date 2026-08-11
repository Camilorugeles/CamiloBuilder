from __future__ import annotations

from .runtime import authorize_connector_operation


class AuthorizedConnector:
    """Applies Agent, deployment, and adapter permissions before delegation."""

    def __init__(self, *, connector, definition, source_id):
        self._connector = connector
        self._definition = definition
        self._source_id = source_id
        self.connector_id = connector.connector_id
        self.provider_id = connector.provider_id

    def capabilities(self): return self._connector.capabilities()

    def _authorize(self, operation):
        authorize_connector_operation(
            definition=self._definition, source_id=self._source_id, operation=operation,
            deployment_permissions=self._connector.deployment_permissions,
            adapter_capabilities=self._connector.capabilities(),
        )

    def list_items(self, *, source_id):
        self._authorize("item.list")
        return self._connector.list_items(source_id=source_id)

    def read(self, reference):
        self._authorize("item.metadata.read")
        return self._connector.read(reference)

    def read_content(self, reference):
        self._authorize("content.read")
        return self._connector.read_content(reference)

    def execute(self, *, action_id, parameters, idempotency_key):
        self._authorize("action.execute")
        return self._connector.execute(action_id=action_id, parameters=parameters, idempotency_key=idempotency_key)
