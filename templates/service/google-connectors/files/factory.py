from __future__ import annotations

from services.agent_core.errors import UnknownReference

from .drive import DriveReadOnlyAdapter
from .gmail import GmailReadOnlyAdapter


ADAPTERS = {"google.drive.readonly": DriveReadOnlyAdapter, "google.gmail.readonly": GmailReadOnlyAdapter}


class ConnectorFactory:
    def __init__(self, *, configuration, clients, secret_provider):
        self._configuration = configuration
        self._clients = dict(clients)
        self._secret_provider = secret_provider

    def resolve(self, connector_id):
        entry = next((item for item in self._configuration["connectors"] if item["alias"] == connector_id), None)
        if entry is None:
            raise UnknownReference(provider_id="google", connector_id=connector_id, message="Unknown connector alias")
        adapter_type = ADAPTERS.get(entry["adapter"])
        if adapter_type is None:
            raise UnknownReference(provider_id="google", connector_id=connector_id, message="Unknown adapter")
        client = self._clients.get(entry["adapter"])
        if client is None:
            raise UnknownReference(provider_id="google", connector_id=connector_id, message="Injected client is unavailable")
        return adapter_type(connector_id=connector_id, credential_ref=entry["credential_ref"], permissions=entry["permissions"], client=client, secret_provider=self._secret_provider)

    def resolve_for_agent(self, *, definition, source_id):
        source = next((item for item in definition["authorized_sources"] if item["source_id"] == source_id), None)
        if source is None:
            raise UnknownReference(provider_id="google", connector_id="unknown", message="Unknown authorized source")
        from services.agent_core.connector_policy import AuthorizedConnector
        return AuthorizedConnector(connector=self.resolve(source["connector_id"]), definition=definition, source_id=source_id)
