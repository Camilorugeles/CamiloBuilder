from __future__ import annotations

from dataclasses import dataclass

from .errors import AuthenticationRequired


@dataclass(frozen=True, repr=False)
class CredentialMaterial:
    access_token: str
    scopes: frozenset[str]
    expired: bool = False

    def __repr__(self): return "CredentialMaterial(<redacted>)"
    def __str__(self): return "<redacted credential>"


class FakeSecretProvider:
    def __init__(self, credentials=None):
        self._credentials = dict(credentials or {})

    def resolve(self, credential_ref):
        try:
            return self._credentials[credential_ref]
        except KeyError as error:
            raise AuthenticationRequired(
                provider_id="secrets", connector_id="secret-provider",
                message="Required credential is unavailable", retryable=False,
            ) from error
