from __future__ import annotations

import base64
import binascii
import io
import re
from dataclasses import dataclass


MAX_ATTACHMENT_BYTES = 8 * 1024 * 1024
MAX_HEADER_BYTES = 8192
MAX_PAYLOAD_BYTES = ((MAX_ATTACHMENT_BYTES + 2) // 3) * 4 + MAX_HEADER_BYTES
ALLOWED_HEADERS = frozenset({
    "content-disposition", "content-length", "content-transfer-encoding",
    "content-type", "date",
})
HEADER_NAME = re.compile(r"^[A-Za-z][A-Za-z0-9-]{0,63}$")
BASE64_BODY = re.compile(rb"^[A-Za-z0-9+/]*={0,2}$")
TRAILING_WHITESPACE = b" \t\r\n\f"


class AttachmentFramingError(ValueError):
    """A sanitized failure at the attachment framing boundary."""


@dataclass(frozen=True)
class CanonicalAttachment:
    content: bytes
    media_type: str
    framing: str
    warnings: tuple[str, ...] = ()


def _bounded(content: bytes):
    if not content or len(content) > MAX_ATTACHMENT_BYTES:
        raise AttachmentFramingError("attachment-size-unsafe")


def _validate_pdf(content: bytes):
    from pypdf import PdfReader

    _bounded(content)
    if not content.startswith(b"%PDF-"):
        raise AttachmentFramingError("attachment-framing-unsafe")
    if content.count(b"%PDF-") != 1:
        raise AttachmentFramingError("attachment-framing-unsafe")
    logical = content.rstrip(TRAILING_WHITESPACE)
    if not logical.endswith(b"%%EOF"):
        raise AttachmentFramingError("pdf-structure-unsafe")
    try:
        reader = PdfReader(io.BytesIO(content), strict=True)
        if reader.is_encrypted:
            raise AttachmentFramingError("encrypted-pdf-unsupported")
        _ = reader.trailer["/Root"]
        for page in reader.pages:
            _ = page.mediabox
    except AttachmentFramingError:
        raise
    except Exception:
        raise AttachmentFramingError("pdf-structure-unsafe") from None


def _split_envelope(payload: bytes):
    if len(payload) > MAX_PAYLOAD_BYTES:
        raise AttachmentFramingError("attachment-size-unsafe")
    positions = []
    for separator in (b"\r\n\r\n", b"\n\n"):
        position = payload.find(separator, 0, MAX_HEADER_BYTES + len(separator))
        if position >= 0:
            positions.append((position, separator))
    if not positions:
        raise AttachmentFramingError("attachment-framing-unsafe")
    position, separator = min(positions, key=lambda item: item[0])
    prefix = payload[:position]
    body = payload[position + len(separator):]
    if not prefix or not body or len(prefix) > MAX_HEADER_BYTES:
        raise AttachmentFramingError("attachment-framing-unsafe")
    if separator == b"\r\n\r\n" and b"\n" in prefix.replace(b"\r\n", b""):
        raise AttachmentFramingError("attachment-framing-unsafe")
    if separator == b"\n\n" and b"\r" in prefix:
        raise AttachmentFramingError("attachment-framing-unsafe")
    try:
        text = prefix.decode("ascii")
    except UnicodeDecodeError:
        raise AttachmentFramingError("attachment-framing-unsafe") from None
    headers = {}
    line_separator = "\r\n" if separator.startswith(b"\r") else "\n"
    for line in text.split(line_separator):
        if not line or ":" not in line:
            raise AttachmentFramingError("attachment-framing-unsafe")
        name, value = line.split(":", 1)
        normalized = name.strip().lower()
        value = value.strip()
        if not HEADER_NAME.fullmatch(name.strip()) or normalized not in ALLOWED_HEADERS:
            raise AttachmentFramingError("attachment-framing-unsafe")
        if normalized in headers or not value or "<" in value or ">" in value or any(
            (ord(character) < 32 and character != "\t") or ord(character) == 127
            for character in value
        ):
            raise AttachmentFramingError("attachment-framing-unsafe")
        headers[normalized] = value
    if headers.get("content-type", "").lower() != "application/pdf":
        raise AttachmentFramingError("attachment-framing-unsafe")
    disposition = headers.get("content-disposition")
    if disposition and disposition.split(";", 1)[0].strip().lower() not in {"attachment", "inline"}:
        raise AttachmentFramingError("attachment-framing-unsafe")
    if "content-length" in headers:
        length = headers["content-length"]
        if not length.isascii() or not length.isdecimal() or int(length) != len(body):
            raise AttachmentFramingError("attachment-framing-unsafe")
    encoding = headers.get("content-transfer-encoding", "binary").lower()
    if encoding in {"binary", "8bit"}:
        canonical = body
    elif encoding == "base64":
        compact = body.replace(b"\r\n", b"").replace(b"\n", b"")
        if not compact or not BASE64_BODY.fullmatch(compact):
            raise AttachmentFramingError("attachment-framing-unsafe")
        try:
            canonical = base64.b64decode(compact, validate=True)
        except (ValueError, binascii.Error):
            raise AttachmentFramingError("attachment-framing-unsafe") from None
    else:
        raise AttachmentFramingError("attachment-framing-unsafe")
    _bounded(canonical)
    return canonical


def canonicalize_pdf_attachment(payload: bytes, media_type: str):
    """Return exact PDF bytes or remove one closed, validated envelope."""
    if not isinstance(payload, bytes):
        raise AttachmentFramingError("attachment-framing-unsafe")
    if not payload or len(payload) > MAX_PAYLOAD_BYTES:
        raise AttachmentFramingError("attachment-size-unsafe")
    if media_type.lower().split(";", 1)[0].strip() != "application/pdf":
        raise AttachmentFramingError("attachment-framing-unsafe")
    if payload.startswith(b"%PDF-"):
        canonical = payload
        framing = "none"
        warnings = ()
    else:
        canonical = _split_envelope(payload)
        framing = "recognized-header-envelope"
        warnings = ("attachment-framing-removed",)
    _validate_pdf(canonical)
    return CanonicalAttachment(canonical, "application/pdf", framing, warnings)
