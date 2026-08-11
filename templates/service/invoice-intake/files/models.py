from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DocumentInput:
    reference: str
    filename: str
    media_type: str
    content: bytes


@dataclass(frozen=True)
class ExtractedDocument:
    reference: str
    filename: str
    media_type: str
    fingerprint: str
    fields: dict[str, object]
    warnings: tuple[str, ...] = ()


DOCUMENT_TYPES = frozenset({
    "invoice", "credit_note", "simplified_invoice", "receipt",
    "delivery_note", "payment_statement", "other", "unknown",
})

DOCUMENT_STATUSES = frozenset({
    "candidate", "not_an_invoice", "invoice_complete", "invoice_incomplete",
    "credit_note", "receipt_or_ticket", "duplicate_suspected",
    "personal_suspected", "internal_transfer", "needs_review",
})
