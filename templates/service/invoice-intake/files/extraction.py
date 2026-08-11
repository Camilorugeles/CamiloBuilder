from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation

from .models import DOCUMENT_TYPES, ExtractedDocument


ALIASES = {
    "document_type": ("document_type", "type", "documenttype"),
    "supplier": ("supplier", "seller", "vendor"),
    "supplier_tax_id": ("supplier_tax_id", "supplier_taxid", "seller_tax_id"),
    "invoice_number": ("invoice_number", "invoice_id", "number"),
    "issue_date": ("issue_date", "invoice_date", "date"),
    "recipient": ("recipient", "buyer", "customer"),
    "recipient_tax_id": ("recipient_tax_id", "buyer_tax_id", "customer_tax_id"),
    "taxable_base": ("taxable_base", "tax_base", "subtotal"),
    "vat": ("vat", "tax_amount"),
    "other_taxes": ("other_taxes",),
    "withholdings": ("withholdings",),
    "total": ("total", "invoice_total"),
    "currency": ("currency",),
    "concept": ("concept", "description"),
}


def _pairs(text):
    pairs = {}
    for line in text.splitlines():
        match = re.match(r"\s*([A-Za-z_][A-Za-z0-9_ -]{1,50})\s*:\s*(.*?)\s*$", line)
        if match: pairs[re.sub(r"[^a-z0-9]+", "_", match.group(1).lower()).strip("_")] = match.group(2)
    return pairs


def _field(value, source, status="extracted"):
    return {"confidence": "high" if value not in (None, "") else "low", "source_ref": source, "status": status, "value": value}


def extract_fields(document: ExtractedDocument):
    pairs = _pairs(str(document.fields.get("text", "")))
    output = {}
    for field, aliases in ALIASES.items():
        value = next((pairs[name] for name in aliases if name in pairs), None)
        output[field] = _field(value or None, document.reference, "extracted" if value not in (None, "") else "unknown")
    doc_type = str(output["document_type"]["value"] or "unknown").lower()
    if doc_type not in DOCUMENT_TYPES: doc_type = "unknown"
    output["document_type"] = _field(doc_type, document.reference, "extracted" if doc_type != "unknown" else "unknown")
    for name in ("taxable_base", "vat", "other_taxes", "withholdings", "total"):
        value = output[name]["value"]
        if value is not None:
            try: output[name]["value"] = format(Decimal(str(value).replace(",", ".")), "f")
            except InvalidOperation: output[name] = _field(None, document.reference, "conflict")
    if output["currency"]["value"]: output["currency"]["value"] = str(output["currency"]["value"]).upper()
    return output


def reconcile(extractions):
    fields = {}
    conflicts = []
    for name in ALIASES:
        present = [item[name] for item in extractions if item[name]["status"] != "unknown"]
        unique = {str(item["value"]) for item in present}
        if len(unique) > 1:
            fields[name] = _field(None, "multiple-attachments", "conflict"); conflicts.append(name)
        elif present:
            sources = sorted({str(item["source_ref"]) for item in present})
            fields[name] = dict(present[0]); fields[name]["source_ref"] = "|".join(sources)
        else: fields[name] = _field(None, "none", "unknown")
    return fields, tuple(sorted(conflicts))
