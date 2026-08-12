from __future__ import annotations

from decimal import Decimal, InvalidOperation

from .resolvers import ABSOLUTE_TOLERANCE


REQUIRED = ("document_type", "supplier", "issue_date", "total", "currency", "recipient")


def _value(fields, name): return fields[name]["value"]


def classify(*, fields, config, conflicts=(), duplicate_refs=(), unreadable=False):
    reasons = set(); warnings = set(conflicts)
    document_type = _value(fields, "document_type") or "unknown"
    unknown = sorted(name for name, field in fields.items() if field["status"] in {"unknown", "conflict"})
    for name in REQUIRED:
        if fields[name]["status"] in {"unknown", "conflict"}: reasons.add(f"missing-or-conflicting:{name}")
    if document_type == "invoice" and fields["invoice_number"]["status"] != "extracted": reasons.add("missing-or-conflicting:invoice_number")
    if unreadable: reasons.add("document-unreadable")
    if conflicts: reasons.add("attachment-conflict")

    concept = str(_value(fields, "concept") or "").lower()
    recipient = str(_value(fields, "recipient") or "").lower()
    rules = config.get("classification_rules", {})
    legal_entity = "unknown"; activity = "unknown"
    entity_matches = [item["value"] for item in rules.get("recipient_rules", []) if item["evidence"].lower() in recipient]
    activity_matches = [item["value"] for item in rules.get("activity_rules", []) if item["evidence"].lower() in (concept + " " + recipient)]
    if len(set(entity_matches)) == 1: legal_entity = entity_matches[0]
    if len(set(activity_matches)) == 1: activity = activity_matches[0]
    elif len(set(activity_matches)) > 1: activity = "multiple_candidates"
    if any(term in concept for term in rules.get("personal_terms", [])): legal_entity = "not_applicable_personal"; activity = "personal"
    if any(term in concept for term in rules.get("internal_transfer_terms", [])): activity = "internal_transfer"
    if any(term in concept for term in rules.get("shared_terms", [])) and activity == "unknown": activity = "administracion_compartida"
    if any(term in concept for term in rules.get("arras_terms", [])): reasons.add("possible-arras")
    if any(term in concept for term in rules.get("sensitive_terms", [])): reasons.add("sensitive-unrelated-document")
    if activity in {"unknown", "multiple_candidates", "personal", "internal_transfer"}: reasons.add(f"activity:{activity}")

    arithmetic = "unknown"
    try:
        base = Decimal(str(_value(fields, "taxable_base"))); vat = Decimal(str(_value(fields, "vat") or "0")); other = Decimal(str(_value(fields, "other_taxes") or "0")); hold = Decimal(str(_value(fields, "withholdings") or "0")); total = Decimal(str(_value(fields, "total")))
        arithmetic = "consistent" if abs(base + vat + other - hold - total) <= ABSOLUTE_TOLERANCE else "inconsistent"
    except (InvalidOperation, TypeError): pass
    if arithmetic == "inconsistent": reasons.add("arithmetic-inconsistency")
    if _value(fields, "currency") not in {None, "EUR"}: reasons.add("non-eur-currency")
    if document_type in {"credit_note", "receipt", "simplified_invoice", "delivery_note", "payment_statement", "other", "unknown"}: reasons.add(f"document-type:{document_type}")
    if duplicate_refs: reasons.add("possible-duplicate")

    destination = config["destinations"].get("activity_destinations", {}).get(activity)
    destination_status = "resolved" if destination else "unresolved"
    if not destination: reasons.add("destination-unresolved")
    if duplicate_refs: status = "duplicate_suspected"
    elif unreadable or conflicts: status = "needs_review"
    elif activity == "personal": status = "personal_suspected"
    elif activity == "internal_transfer": status = "internal_transfer"
    elif document_type == "credit_note": status = "credit_note"
    elif document_type in {"receipt", "simplified_invoice"}: status = "receipt_or_ticket"
    elif document_type in {"delivery_note", "payment_statement", "other"}: status = "not_an_invoice"
    elif document_type == "invoice" and reasons: status = "invoice_incomplete"
    elif document_type == "invoice": status = "invoice_complete"
    else: status = "needs_review"
    review = bool(reasons)
    confidence = "low" if unreadable or conflicts or len(reasons) >= 4 else ("medium" if review else "high")
    return {
        "activity": activity, "arithmetic_consistency": arithmetic,
        "destination_status": destination_status, "document_status": status,
        "duplicate_refs": list(sorted(duplicate_refs)), "global_confidence": confidence,
        "legal_entity": legal_entity, "proposed_destination_ref": destination,
        "review_required": review, "review_reasons": sorted(reasons),
        "unknown_fields": unknown, "warnings": sorted(warnings),
    }
