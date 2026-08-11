from __future__ import annotations


def build_review_card(analysis):
    fields = analysis["fields"]
    value = lambda name: fields[name]["value"]
    return {
        "activity": analysis["activity"],
        "attachment_refs": analysis["attachment_refs"],
        "attachments": analysis["attachments"],
        "confidence": analysis["global_confidence"],
        "destination_status": analysis["destination_status"],
        "document_status": analysis["document_status"],
        "document_type": value("document_type"),
        "duplicate_suspected": bool(analysis["duplicate_refs"]),
        "gmail_message_ref": analysis["gmail_message_ref"],
        "invoice_number": value("invoice_number"),
        "issue_date": value("issue_date"),
        "legal_entity": analysis["legal_entity"],
        "other_taxes": value("other_taxes"),
        "proposed_destination_ref": analysis["proposed_destination_ref"],
        "recipient": value("recipient"),
        "review_reasons": analysis["review_reasons"],
        "supplier": value("supplier"),
        "supplier_tax_id": value("supplier_tax_id"),
        "taxable_base": value("taxable_base"),
        "total": value("total"),
        "unknown_fields": analysis["unknown_fields"],
        "vat": value("vat"),
        "warnings": analysis["warnings"],
        "withholdings": value("withholdings"),
        "currency": value("currency"),
    }
