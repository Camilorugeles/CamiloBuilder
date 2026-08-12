from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation

from .candidates import FieldCandidate
from .layout import build_layout
from .semantics import (
    AMOUNT_RE, COMPANY_RE, DATE_RE, DOCUMENT_MARKERS, LABELS, RATE_RE,
    TAX_ID_RE, folded, normalize_amount, normalize_date, valid_spanish_tax_id,
)


MIN_SCORE = 35
WIN_MARGIN = 12
ABSOLUTE_TOLERANCE = Decimal("0.02")


def _candidate(field, value, document, line, rule, label, relation, score, alternatives=()):
    return FieldCandidate(field, value, document.reference, line.page, rule, label, line.text, relation, None, score, tuple(alternatives))


def _right_value(line, label):
    normalized = folded(line.text); position = normalized.find(label)
    if position < 0: return None
    # Use original punctuation/spacing conservatively after a matching prefix.
    pattern = re.compile(re.escape(label).replace(r"\ ", r"\s+") + r"\s*[:#.-]?\s*(.+)$", re.I)
    match = pattern.search(folded(line.text))
    if not match: return None
    words = line.text.split()
    label_words = len(label.split())
    return " ".join(words[label_words:]).lstrip(":#.- ") or None


def _labeled_candidates(document, layout):
    found = []
    lines = layout.lines
    for index, line in enumerate(lines):
        normalized = folded(line.text)
        fiscal_header = all(term in normalized for term in ("base imponible", "iva", "total"))
        for field, labels in LABELS.items():
            if fiscal_header and field in {"taxable_base", "vat", "total"}:
                continue
            for label in labels:
                if not re.search(r"(?:^|\s)" + re.escape(label) + r"(?:\s|$)", normalized): continue
                if field in {"supplier", "recipient"} and any(token in normalized for token in ("nif", "cif", "vat id", "tax id")):
                    continue
                raw = _right_value(line, label)
                relation = "same_line_right"; score = 72
                if not raw and index + 1 < len(lines):
                    raw = lines[index + 1].text; relation = "next_line"; score = 62
                if not raw: continue
                values = _normalize_for_field(field, raw)
                for value in values:
                    found.append(_candidate(field, value, document, line, f"label.{field}", label, relation, score))
    return found


def _normalize_for_field(field, raw):
    if field == "issue_date":
        return [value for value in (normalize_date(item) for item in DATE_RE.findall(raw)) if value]
    if field in {"taxable_base", "vat", "other_taxes", "withholdings", "total"}:
        if field == "vat" and "%" in raw:
            raw = RATE_RE.sub("", raw)
        return [value for value in (normalize_amount(item) for item in AMOUNT_RE.findall(raw)) if value]
    if field in {"supplier_tax_id", "recipient_tax_id"}:
        return [re.sub(r"[^A-Z0-9]", "", item.upper()) for item in TAX_ID_RE.findall(raw) if valid_spanish_tax_id(item)]
    if field == "currency":
        upper = raw.upper()
        if "EUR" in upper or "€" in raw: return ["EUR"]
        return [code for code in ("USD", "GBP", "CHF") if code in upper]
    return [raw.strip()] if raw.strip() else []


def generate_candidates(document):
    layout = build_layout(str(document.fields.get("text", "")), document.fields.get("fragments", ()))
    candidates = _labeled_candidates(document, layout)
    lines = layout.lines
    for index, line in enumerate(lines):
        normalized = folded(line.text)
        if index + 1 < len(lines) and all(term in normalized for term in ("base imponible", "iva", "total")):
            amounts = [value for value in (normalize_amount(item) for item in AMOUNT_RE.findall(lines[index + 1].text)) if value]
            if len(amounts) == 3:
                for field, value in zip(("taxable_base", "vat", "total"), amounts):
                    candidates.append(_candidate(field, value, document, line, "table.fiscal-summary", field, "table_row", 68))
        for marker, value in DOCUMENT_MARKERS:
            if marker in normalized:
                candidates.append(_candidate("document_type", value, document, line, "document.marker", marker, "same_block", 70 if normalized == marker else 52))
                break
        for raw_date in DATE_RE.findall(line.text):
            value = normalize_date(raw_date)
            context = " ".join(folded(item.text) for item in lines[max(0, index - 1):index + 2])
            if value and not any(term in context for term in ("vencimiento", "due date", "servicio", "service period")):
                score = 48 if any(term in context for term in ("fecha", "factura", "invoice", "emision")) else 24
                candidates.append(_candidate("issue_date", value, document, line, "date.context", None, "same_block", score))
        tax_ids = [re.sub(r"[^A-Z0-9]", "", item.upper()) for item in TAX_ID_RE.findall(line.text) if valid_spanish_tax_id(item)]
        context = " ".join(folded(item.text) for item in lines[max(0, index - 1):index + 1])
        for tax_id in tax_ids:
            if any(term in context for term in ("cliente", "destinatario", "customer", "bill to")):
                field, score = "recipient_tax_id", 65
            elif any(term in context for term in ("proveedor", "emisor", "supplier", "seller")):
                field, score = "supplier_tax_id", 65
            else:
                field, score = "tax_id_unassigned", 25
            if field != "tax_id_unassigned": candidates.append(_candidate(field, tax_id, document, line, "tax-id.context", None, "same_block", score + (8 if valid_spanish_tax_id(tax_id) else 0)))
        if COMPANY_RE.search(line.text):
            if any(label in normalized for label in ("proveedor", "emisor", "supplier", "seller", "cliente", "destinatario", "customer", "bill to")):
                continue
            nearby = " ".join(folded(item.text) for item in lines[max(0, index - 1):index + 2])
            if any(term in nearby for term in ("cliente", "destinatario", "customer", "bill to")): field = "recipient"
            elif any(term in nearby for term in ("proveedor", "emisor", "supplier", "seller")): field = "supplier"
            else: field = "supplier" if index < max(3, len(lines) // 3) else "recipient"
            candidates.append(_candidate(field, line.text.strip(), document, line, "company.block", None, "same_block", 48))
        if "€" in line.text or re.search(r"\bEUR\b", line.text, re.I):
            candidates.append(_candidate("currency", "EUR", document, line, "currency.marker", None, "same_block", 62))
    return tuple(candidates)


def _field(value, source, status="extracted", confidence="high"):
    return {"confidence": confidence, "source_ref": source, "status": status, "value": value}


def resolve_field(field, candidates):
    values = {}
    for candidate in candidates:
        if candidate.field == field:
            current = values.get(candidate.value)
            if current is None or candidate.score > current.score: values[candidate.value] = candidate
    ranked = sorted(values.values(), key=lambda item: (-item.score, item.value))
    if not ranked or ranked[0].score < MIN_SCORE: return _field(None, "none", "unknown", "low")
    if len(ranked) > 1 and ranked[0].score - ranked[1].score < WIN_MARGIN:
        return _field(None, "multiple-candidates", "conflict", "low")
    winner = ranked[0]
    confidence = "high" if winner.score >= 65 else "medium"
    return _field(winner.value, winner.source_ref, "extracted", confidence)


def resolve_document(document, field_names):
    candidates = list(generate_candidates(document))
    fields = {field: resolve_field(field, candidates) for field in field_names}
    return fields, tuple(candidates)


def arithmetic_consistency(fields):
    try:
        base = Decimal(str(fields["taxable_base"]["value"])); vat = Decimal(str(fields["vat"]["value"])); total = Decimal(str(fields["total"]["value"]))
    except (InvalidOperation, TypeError): return "unknown"
    optional = []
    for name in ("other_taxes", "withholdings"):
        value = fields[name]["value"]
        if value is None: optional.append(Decimal("0"))
        else:
            try: optional.append(Decimal(str(value)))
            except InvalidOperation: return "unknown"
    difference = abs(base + vat + optional[0] - optional[1] - total)
    return "consistent" if difference <= ABSOLUTE_TOLERANCE else "inconsistent"
