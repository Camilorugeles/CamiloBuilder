from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path


MAX_MANIFEST_BYTES = 64 * 1024
CASE_ID = re.compile(r"^[A-Z][A-Z0-9-]{2,63}$")
OPAQUE_ID = re.compile(r"^[A-Za-z0-9_-]{1,4096}$")
DATE = re.compile(r"^[0-9]{4}-(0[1-9]|1[0-2])-([0-2][0-9]|3[01])$")
MEDIA_TYPES = frozenset({"application/pdf", "application/xml", "text/xml"})
PURPOSES = frozenset({"integrity_check", "shadow_pilot"})
GROUND_TRUTH = frozenset({"authorized", "pending", "not_available"})
ROOT_KEYS = frozenset({"format", "format_version", "cases"})
CASE_KEYS = frozenset({
    "case_id", "provider", "message_ref", "attachment_ref",
    "expected_media_type", "purpose", "authorized_on", "ground_truth_status",
})


class PilotManifestError(ValueError):
    """A sanitized failure while loading a closed real-pilot manifest."""


def _opaque_reference(value, prefix):
    if not isinstance(value, str) or not value.startswith(prefix):
        raise PilotManifestError("pilot-manifest-invalid")
    identifier = value[len(prefix):]
    if not OPAQUE_ID.fullmatch(identifier):
        raise PilotManifestError("pilot-manifest-invalid")
    return identifier


def load_pilot_manifest(path):
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        raise PilotManifestError("pilot-manifest-unsafe")
    try:
        if path.stat().st_size > MAX_MANIFEST_BYTES:
            raise PilotManifestError("pilot-manifest-unsafe")
        document = json.loads(path.read_text(encoding="utf-8"))
    except PilotManifestError:
        raise
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        raise PilotManifestError("pilot-manifest-invalid") from None
    if not isinstance(document, dict) or set(document) != ROOT_KEYS:
        raise PilotManifestError("pilot-manifest-invalid")
    if document["format"] != "camilo-os.real-pilot-manifest" or document["format_version"] != 1:
        raise PilotManifestError("pilot-manifest-invalid")
    cases = document["cases"]
    if not isinstance(cases, list) or not 1 <= len(cases) <= 15:
        raise PilotManifestError("pilot-manifest-invalid")
    normalized = []
    for case in cases:
        if not isinstance(case, dict) or set(case) != CASE_KEYS:
            raise PilotManifestError("pilot-manifest-invalid")
        message_id = _opaque_reference(case["message_ref"], "gmail:message:")
        attachment_prefix = f"gmail:attachment:{message_id}:"
        _opaque_reference(case["attachment_ref"], attachment_prefix)
        if (
            not isinstance(case["case_id"], str) or not CASE_ID.fullmatch(case["case_id"])
            or case["provider"] != "gmail"
            or case["expected_media_type"] not in MEDIA_TYPES
            or case["purpose"] not in PURPOSES
            or not isinstance(case["authorized_on"], str) or not DATE.fullmatch(case["authorized_on"])
            or case["ground_truth_status"] not in GROUND_TRUTH
        ):
            raise PilotManifestError("pilot-manifest-invalid")
        try:
            date.fromisoformat(case["authorized_on"])
        except ValueError:
            raise PilotManifestError("pilot-manifest-invalid") from None
        normalized.append(dict(case))
    case_ids = [case["case_id"] for case in normalized]
    attachment_refs = [case["attachment_ref"] for case in normalized]
    if case_ids != sorted(set(case_ids)) or len(attachment_refs) != len(set(attachment_refs)):
        raise PilotManifestError("pilot-manifest-order-invalid")
    return {"format": document["format"], "format_version": 1, "cases": normalized}


def attachment_allowlist(manifest):
    return {
        case["attachment_ref"]: case["expected_media_type"]
        for case in manifest["cases"]
    }
