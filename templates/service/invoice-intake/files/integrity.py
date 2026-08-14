from __future__ import annotations

import hashlib
import io
import xml.etree.ElementTree as ET

from .framing import canonicalize_pdf_attachment


RAW_OBSERVATION_KEYS = frozenset({
    "representation", "response_size_bytes", "encoded_size_bytes",
    "encoded_sha256", "declared_decoded_size", "expected_media_type",
})


def _raw_observation(value):
    if not isinstance(value, dict) or set(value) != RAW_OBSERVATION_KEYS:
        raise ValueError("integrity-raw-observation-invalid")
    if value["representation"] != "gmail-base64url":
        raise ValueError("integrity-raw-observation-invalid")
    for key in ("response_size_bytes", "encoded_size_bytes"):
        if not isinstance(value[key], int) or isinstance(value[key], bool) or value[key] < 1:
            raise ValueError("integrity-raw-observation-invalid")
    declared = value["declared_decoded_size"]
    if declared is not None and (not isinstance(declared, int) or isinstance(declared, bool) or declared < 1):
        raise ValueError("integrity-raw-observation-invalid")
    digest = value["encoded_sha256"]
    if not isinstance(digest, str) or len(digest) != 64 or any(character not in "0123456789abcdef" for character in digest):
        raise ValueError("integrity-raw-observation-invalid")
    if not isinstance(value["expected_media_type"], str):
        raise ValueError("integrity-raw-observation-invalid")
    return dict(value)


def _bytes_observation(content, *, representation):
    if not isinstance(content, bytes) or not content:
        raise ValueError("integrity-payload-invalid")
    return {
        "representation": representation,
        "size_bytes": len(content),
        "sha256": hashlib.sha256(content).hexdigest(),
        "pdf_signature_at_start": content.startswith(b"%PDF-"),
        "pdf_signature_offset": content.find(b"%PDF-"),
        "pdf_signature_count": content.count(b"%PDF-"),
        "has_lf": b"\n" in content,
        "has_crlf": b"\r\n" in content,
        "has_literal_backslash_n": b"\\n" in content,
    }


def build_integrity_report(*, case, raw_observation, connector_content, replay_content=None):
    """Build a content-free A-E report for one allowlisted attachment."""
    safe_raw = _raw_observation(raw_observation)
    if case["attachment_ref"] != connector_content.reference:
        raise ValueError("integrity-reference-mismatch")
    media_type = connector_content.media_type.lower().split(";", 1)[0].strip()
    if media_type != case["expected_media_type"]:
        raise ValueError("integrity-media-type-mismatch")
    content = connector_content.content
    stage_b = _bytes_observation(content, representation="decoded-bytes")
    stage_c = _bytes_observation(content, representation="connector-bytes")
    if media_type == "application/pdf":
        canonical = canonicalize_pdf_attachment(content, media_type)
        canonical_content = canonical.content
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(canonical_content), strict=True)
        pages = len(reader.pages)
        encrypted = reader.is_encrypted
        framing = canonical.framing
        validation = "strict-valid"
    elif media_type in {"application/xml", "text/xml"}:
        upper = content.upper()
        if b"<!DOCTYPE" in upper or b"<!ENTITY" in upper:
            raise ValueError("integrity-xml-unsafe")
        try:
            ET.fromstring(content)
        except ET.ParseError:
            raise ValueError("integrity-xml-unsafe") from None
        canonical_content = content
        pages = None
        encrypted = None
        framing = "none"
        validation = "xml-valid"
    else:
        raise ValueError("integrity-media-type-unsupported")
    stage_d = _bytes_observation(canonical_content, representation="canonical-document")
    replay = canonical_content if replay_content is None else replay_content
    stage_e = _bytes_observation(replay, representation="replay-bytes")
    stage_d.update({"framing": framing, "validation": validation, "pages": pages, "encrypted": encrypted})
    return {
        "case_id": case["case_id"],
        "attachment_ref": case["attachment_ref"],
        "media_type": media_type,
        "stages": {"A": safe_raw, "B": stage_b, "C": stage_c, "D": stage_d, "E": stage_e},
        "equalities": {
            "B_equals_C": stage_b["sha256"] == stage_c["sha256"],
            "C_equals_D": stage_c["sha256"] == stage_d["sha256"],
            "D_equals_E": stage_d["sha256"] == stage_e["sha256"],
        },
    }
