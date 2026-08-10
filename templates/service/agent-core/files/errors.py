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
