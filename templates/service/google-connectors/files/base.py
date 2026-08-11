from __future__ import annotations

from services.agent_core.errors import (
    CapabilityDenied, ConnectorError, CredentialExpired, InsufficientScope,
    ProviderRejected, ProviderUnavailable, UnknownReference,
)


class ReadOnlyGoogleAdapter:
    REQUIRED_SCOPES = frozenset()
    READ_CAPABILITIES = frozenset({"content.read", "item.list", "item.metadata.read"})

    def __init__(self, *, connector_id, credential_ref, permissions, client, secret_provider):
        self.connector_id = connector_id
        self.provider_id = "google"
        self.credential_ref = credential_ref
        self.deployment_permissions = frozenset(permissions)
        self._client = client
        self._secret_provider = secret_provider

    def capabilities(self): return self.READ_CAPABILITIES

    def _credential(self):
        credential = self._secret_provider.resolve(self.credential_ref)
        if credential.expired:
            raise CredentialExpired(provider_id=self.provider_id, connector_id=self.connector_id, message="Credential has expired")
        if not self.REQUIRED_SCOPES.issubset(credential.scopes):
            raise InsufficientScope(provider_id=self.provider_id, connector_id=self.connector_id, message="Credential scopes are insufficient")
        return credential

    def _authorize(self, operation):
        if operation not in self.deployment_permissions or operation not in self.capabilities():
            raise CapabilityDenied(provider_id=self.provider_id, connector_id=self.connector_id, message="Connector operation is not permitted")

    def _call(self, callback, **arguments):
        try:
            return callback(**arguments)
        except ConnectorError:
            raise
        except KeyError as error:
            raise UnknownReference(provider_id=self.provider_id, connector_id=self.connector_id, message="Provider reference is unavailable") from None
        except (ConnectionError, TimeoutError, OSError) as error:
            raise ProviderUnavailable(provider_id=self.provider_id, connector_id=self.connector_id, message="Provider is unavailable", retryable=True) from None
        except Exception as error:
            raise ProviderRejected(provider_id=self.provider_id, connector_id=self.connector_id, message="Provider rejected the request") from None

    def execute(self, *, action_id, parameters, idempotency_key):
        raise CapabilityDenied(provider_id=self.provider_id, connector_id=self.connector_id, message="This adapter is read-only")
