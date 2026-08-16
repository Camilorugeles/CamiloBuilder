from __future__ import annotations

import re
from collections import Counter


SAFE_CODE = re.compile(r"^[a-z][a-z0-9-]{0,63}$")
AUDIT_FIELDS = (
    "attachments_outside_manifest", "authorized_attachment_reads", "drive_writes",
    "gmail_mutations", "label_changes", "list_requests", "manifest_reads",
    "message_metadata_reads", "messages_outside_manifest", "unread_changes",
)


class ShadowBatchSummaryError(ValueError):
    """A sanitized failure while building a content-free operational summary."""


def _warning_code(value):
    if not isinstance(value, str):
        return "sanitized-warning"
    code = value.split(":", 1)[0]
    return code if SAFE_CODE.fullmatch(code) else "sanitized-warning"


def _analysis(record):
    if not isinstance(record, dict):
        raise ShadowBatchSummaryError("shadow-summary-record-invalid")
    if record.get("proposed_actions") or record.get("executed_actions"):
        raise ShadowBatchSummaryError("shadow-summary-actions-present")
    results = record.get("results")
    if not isinstance(results, list):
        raise ShadowBatchSummaryError("shadow-summary-record-invalid")
    matches = [item.get("value") for item in results if isinstance(item, dict) and item.get("kind") == "invoice-analysis.v1"]
    if len(matches) != 1 or not isinstance(matches[0], dict):
        raise ShadowBatchSummaryError("shadow-summary-record-invalid")
    return matches[0]


def build_shadow_batch_summary(*, records, expected_attachments, audit):
    """Return only counters and sanitized codes from real Shadow Mode records."""
    if (
        not isinstance(records, (tuple, list))
        or not isinstance(expected_attachments, int) or isinstance(expected_attachments, bool)
        or expected_attachments < 0 or not isinstance(audit, dict)
    ):
        raise ShadowBatchSummaryError("shadow-summary-input-invalid")

    warning_codes = Counter()
    document_statuses = Counter()
    processed_attachments = review_required = completed_records = 0
    for record in records:
        analysis = _analysis(record)
        attachments = analysis.get("attachments")
        warnings = analysis.get("warnings")
        status = analysis.get("document_status")
        if not isinstance(attachments, list) or not isinstance(warnings, list) or not isinstance(status, str):
            raise ShadowBatchSummaryError("shadow-summary-record-invalid")
        processed_attachments += len(attachments)
        warning_codes.update(_warning_code(value) for value in warnings)
        document_statuses[status if SAFE_CODE.fullmatch(status) else "sanitized-status"] += 1
        review_required += bool(analysis.get("review_required"))
        completed_records += record.get("status") == "completed"

    safe_audit = {}
    for field in AUDIT_FIELDS:
        value = audit.get(field, 0)
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            raise ShadowBatchSummaryError("shadow-summary-audit-invalid")
        safe_audit[field] = value

    return {
        "format": "camilo-os.shadow-batch-summary", "format_version": 1,
        "records": len(records), "completed_records": completed_records,
        "review_required": review_required, "expected_attachments": expected_attachments,
        "processed_attachments": processed_attachments,
        "abstained_attachments": max(0, expected_attachments - processed_attachments),
        "document_status_counts": dict(sorted(document_statuses.items())),
        "warning_code_counts": dict(sorted(warning_codes.items())),
        "proposed_actions": 0, "executed_actions": 0, "audit": safe_audit,
    }
