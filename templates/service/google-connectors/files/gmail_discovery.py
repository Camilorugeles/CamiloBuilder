from __future__ import annotations

import hashlib
import json
import re
from datetime import date
from urllib.parse import urlencode
from urllib.request import Request, urlopen


GMAIL_MESSAGES = "https://gmail.googleapis.com/gmail/v1/users/me/messages"
DEFAULT_QUERY = "has:attachment {filename:pdf filename:xml} newer_than:30d"
MAX_MESSAGES = 15
MAX_METADATA_BYTES = 2 * 1024 * 1024
MEDIA_TYPES = {
    "application/pdf": "application/pdf",
    "application/xml": "application/xml",
    "text/xml": "text/xml",
}
OPAQUE_ID = re.compile(r"^[A-Za-z0-9_-]{1,4096}$")
PART_FIELDS = "filename,mimeType,body(attachmentId)"
MESSAGE_FIELDS = (
    "id,payload(parts(" + PART_FIELDS + ",parts(" + PART_FIELDS
    + ",parts(" + PART_FIELDS + ",parts(" + PART_FIELDS + ")))))"
)


class GmailDiscoveryError(ValueError):
    """A sanitized failure during bounded read-only Gmail discovery."""


class GmailInvoiceDiscoveryClient:
    """Discover only bounded PDF/XML attachment references without message content."""

    def __init__(self, *, opener=urlopen, timeout=30):
        self._opener = opener
        self._timeout = timeout
        self._list_requests = 0
        self._metadata_reads = 0

    def _json_get(self, url, access_token):
        if not isinstance(access_token, str) or not access_token:
            raise GmailDiscoveryError("gmail-authentication-required")
        request = Request(url, headers={"Authorization": f"Bearer {access_token}", "Accept": "application/json"}, method="GET")
        try:
            with self._opener(request, timeout=self._timeout) as response:
                raw = response.read(MAX_METADATA_BYTES + 1)
        except Exception:
            raise GmailDiscoveryError("gmail-discovery-unavailable") from None
        if not raw or len(raw) > MAX_METADATA_BYTES:
            raise GmailDiscoveryError("gmail-discovery-response-invalid")
        try:
            value = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise GmailDiscoveryError("gmail-discovery-response-invalid") from None
        if not isinstance(value, dict):
            raise GmailDiscoveryError("gmail-discovery-response-invalid")
        return value

    @staticmethod
    def _parts(payload):
        pending = list(payload.get("parts", ())) if isinstance(payload, dict) else []
        while pending:
            part = pending.pop()
            if not isinstance(part, dict):
                raise GmailDiscoveryError("gmail-discovery-response-invalid")
            nested = part.get("parts", [])
            if not isinstance(nested, list):
                raise GmailDiscoveryError("gmail-discovery-response-invalid")
            pending.extend(nested)
            body = part.get("body", {})
            if not isinstance(body, dict):
                raise GmailDiscoveryError("gmail-discovery-response-invalid")
            attachment_id = body.get("attachmentId")
            media_type = MEDIA_TYPES.get(part.get("mimeType"))
            filename = part.get("filename", "")
            if (
                isinstance(attachment_id, str) and OPAQUE_ID.fullmatch(attachment_id)
                and media_type and isinstance(filename, str)
                and filename.lower().endswith((".pdf", ".xml"))
            ):
                yield attachment_id, media_type

    def discover(self, *, access_token, max_messages=10, authorized_on=None):
        if not isinstance(max_messages, int) or isinstance(max_messages, bool) or not 1 <= max_messages <= MAX_MESSAGES:
            raise GmailDiscoveryError("gmail-discovery-limit-invalid")
        query = urlencode({"q": DEFAULT_QUERY, "maxResults": max_messages, "fields": "messages/id"})
        listing = self._json_get(f"{GMAIL_MESSAGES}?{query}", access_token)
        self._list_requests += 1
        messages = listing.get("messages", [])
        if not isinstance(messages, list) or len(messages) > max_messages:
            raise GmailDiscoveryError("gmail-discovery-response-invalid")
        cases = []
        seen = set()
        for message in messages:
            if (
                not isinstance(message, dict) or set(message) != {"id"}
                or not isinstance(message["id"], str) or not OPAQUE_ID.fullmatch(message["id"])
            ):
                raise GmailDiscoveryError("gmail-discovery-response-invalid")
            message_id = message["id"]
            params = urlencode({"format": "full", "fields": MESSAGE_FIELDS})
            metadata = self._json_get(f"{GMAIL_MESSAGES}/{message_id}?{params}", access_token)
            self._metadata_reads += 1
            if metadata.get("id") != message_id or "payload" not in metadata:
                raise GmailDiscoveryError("gmail-discovery-response-invalid")
            for attachment_id, media_type in self._parts(metadata["payload"]):
                reference = f"gmail:attachment:{message_id}:{attachment_id}"
                if reference in seen:
                    continue
                seen.add(reference)
                digest = hashlib.sha256(reference.encode("ascii")).hexdigest()[:20].upper()
                cases.append({
                    "case_id": f"AUTO-{digest}",
                    "provider": "gmail",
                    "message_ref": f"gmail:message:{message_id}",
                    "attachment_ref": reference,
                    "expected_media_type": media_type,
                    "purpose": "shadow_pilot",
                    "authorized_on": authorized_on or date.today().isoformat(),
                    "ground_truth_status": "pending",
                })
                if len(cases) >= MAX_MESSAGES:
                    break
            if len(cases) >= MAX_MESSAGES:
                break
        cases.sort(key=lambda item: item["case_id"])
        return {"format": "camilo-os.real-pilot-manifest", "format_version": 1, "cases": cases}

    def audit_summary(self):
        return {
            "list_requests": self._list_requests,
            "message_metadata_reads": self._metadata_reads,
            "gmail_mutations": 0,
            "unread_changes": 0,
            "label_changes": 0,
            "drive_writes": 0,
        }
