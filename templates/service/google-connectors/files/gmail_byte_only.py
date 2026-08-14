from __future__ import annotations

import hashlib
import json
from urllib.parse import quote
from urllib.request import Request, urlopen

from .gmail import BASE64URL, MAX_BASE64URL_BYTES


MAX_RESPONSE_BYTES = MAX_BASE64URL_BYTES + 1024
GMAIL_API = "https://gmail.googleapis.com/gmail/v1/users/me/messages"


class GmailByteOnlyError(ValueError):
    """A sanitized failure at the dedicated Gmail attachment boundary."""


class GmailByteOnlyAttachmentClient:
    """Fetch only explicitly allowlisted Gmail attachment resources."""

    def __init__(self, *, attachment_media_types, opener=urlopen, timeout=30):
        self._media_types = dict(attachment_media_types)
        self._opener = opener
        self._timeout = timeout
        self._observations = {}

    @staticmethod
    def _reference(message_id, attachment_id):
        return f"gmail:attachment:{message_id}:{attachment_id}"

    def get_attachment(self, *, access_token, message_id, attachment_id):
        reference = self._reference(message_id, attachment_id)
        media_type = self._media_types.get(reference)
        if media_type is None:
            raise GmailByteOnlyError("gmail-attachment-not-authorized")
        if not isinstance(access_token, str) or not access_token:
            raise GmailByteOnlyError("gmail-authentication-required")
        url = (
            f"{GMAIL_API}/{quote(message_id, safe='')}/attachments/"
            f"{quote(attachment_id, safe='')}"
        )
        request = Request(url, headers={"Authorization": f"Bearer {access_token}", "Accept": "application/json"}, method="GET")
        try:
            with self._opener(request, timeout=self._timeout) as response:
                raw = response.read(MAX_RESPONSE_BYTES + 1)
        except GmailByteOnlyError:
            raise
        except Exception:
            raise GmailByteOnlyError("gmail-attachment-unavailable") from None
        if not raw or len(raw) > MAX_RESPONSE_BYTES:
            raise GmailByteOnlyError("gmail-attachment-response-invalid")
        try:
            value = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise GmailByteOnlyError("gmail-attachment-response-invalid") from None
        if not isinstance(value, dict) or set(value) - {"data", "size"} or "data" not in value:
            raise GmailByteOnlyError("gmail-attachment-response-invalid")
        data = value["data"]
        size = value.get("size")
        if (
            not isinstance(data, str) or not data or len(data) > MAX_BASE64URL_BYTES
            or not BASE64URL.fullmatch(data)
            or (size is not None and (not isinstance(size, int) or isinstance(size, bool) or size < 1))
        ):
            raise GmailByteOnlyError("gmail-attachment-response-invalid")
        self._observations[reference] = {
            "representation": "gmail-base64url",
            "response_size_bytes": len(raw),
            "encoded_size_bytes": len(data.encode("ascii")),
            "encoded_sha256": hashlib.sha256(data.encode("ascii")).hexdigest(),
            "declared_decoded_size": size,
            "expected_media_type": media_type,
        }
        return {"data": data, "media_type": media_type}

    def observation(self, reference):
        value = self._observations.get(reference)
        if value is None:
            raise GmailByteOnlyError("gmail-attachment-not-observed")
        return dict(value)
