class AgentCoreError(RuntimeError):
    """Base error for the generated Agent Core."""


class DefinitionError(AgentCoreError):
    """Raised when an Agent Definition cannot be trusted."""


class RecordError(AgentCoreError):
    """Raised when an Execution Record cannot be trusted."""


class DuplicateRunError(AgentCoreError):
    """Raised when a store receives a duplicate run."""


class ConcurrentUpdateError(AgentCoreError):
    """Raised when a stale record revision is replaced."""


class ConnectorError(AgentCoreError):
    code = "connector-error"

    def __init__(self, *, provider_id, connector_id, message, retryable=False):
        self.provider_id = provider_id
        self.connector_id = connector_id
        self.retryable = bool(retryable)
        super().__init__(str(message))

    def __str__(self):
        return f"{self.code}: {super().__str__()}"


class AuthenticationRequired(ConnectorError): code = "authentication-required"
class CredentialExpired(ConnectorError): code = "credential-expired"
class InsufficientScope(ConnectorError): code = "insufficient-scope"
class CapabilityDenied(ConnectorError): code = "capability-denied"
class UnknownReference(ConnectorError): code = "unknown-reference"
class ProviderUnavailable(ConnectorError): code = "provider-unavailable"
class ProviderRejected(ConnectorError): code = "provider-rejected"
