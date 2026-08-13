from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation

from .candidates import FieldCandidate
from .layout import FiscalRow, IdentityBlock, LayoutDocument, build_layout, pair_rows
from .semantics import (
    AMOUNT_RE, COMPANY_RE, DATE_RE, DOCUMENT_MARKERS, LABELS, RATE_RE,
    TAX_ID_RE, folded, normalize_amount, normalize_date, valid_spanish_tax_id,
)


MIN_SCORE = 35
WIN_MARGIN = 12
ABSOLUTE_TOLERANCE = Decimal("0.02")
FORBIDDEN_CONCEPT_VALUES = frozenset({"importe", "cantidad", "precio", "total", "base", "iva", "%", "% iva"})
NON_IDENTITY_VALUES = frozenset({
    "forma de pago", "importe", "importe liquido", "total", "base", "base imponible",
    "iva", "vencimiento", "concepto", "cantidad", "precio", "fecha", "cliente", "proveedor",
})
HEADER_FIELDS = {
    "invoice_number": ("n factura", "numero factura", "numero de factura", "invoice no", "invoice number", "document number"),
    "issue_date": ("fecha", "fecha factura", "fecha emision", "issue date", "invoice date"),
    "due_date": ("vencimiento", "fecha vencimiento", "due date"),
    "service_date": ("fecha servicio", "periodo servicio", "service date", "service period"),
    "supplier": ("proveedor", "emisor", "supplier", "seller"),
    "recipient": ("cliente", "destinatario", "receptor", "customer", "bill to"),
    "supplier_tax_id": ("nif proveedor", "cif proveedor", "supplier tax id", "seller vat id"),
    "recipient_tax_id": ("nif cliente", "cif cliente", "customer tax id", "recipient vat id"),
    "taxable_base": ("base", "base imponible", "subtotal", "tax base"),
    "vat_rate": ("%", "% iva", "tipo iva", "vat rate"),
    "vat": ("cuota iva", "importe iva", "iva", "vat amount"),
    "withholdings": ("retencion", "retenciones", "withholding"),
    "other_taxes": ("otros impuestos", "recargo", "surcharges"),
    "total": ("total", "total factura", "importe total", "importe liquido", "amount due", "grand total"),
    "concept": ("concepto", "descripcion", "servicio", "detalle", "description"),
    "amount_column": ("importe", "cantidad", "precio", "amount", "quantity", "price"),
}


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
    value = " ".join(words[label_words:]).lstrip(":#.- ") or None
    if value and _header_field(value) is not None:
        return None
    return value


def _plausible_identity(value):
    normalized = folded(value).strip(" :#.-")
    if not normalized or normalized in NON_IDENTITY_VALUES or _header_field(normalized) is not None: return False
    if any(_header_field(part) is not None for part in re.split(r"\s{2,}|\||;", normalized)): return False
    return bool(COMPANY_RE.search(value) or (len(value.split()) >= 2 and any(character.isalpha() for character in value)))


def _labeled_candidates(document, layout):
    found = []
    lines = layout.lines
    geometric_multi_headers = {
        cell.text for row in layout.rows
        if sum(_is_semantic_header(item.text) for item in row.cells) >= 2
        for cell in row.cells
    }
    for index, line in enumerate(lines):
        normalized = folded(line.text)
        matched_headers = {
            "vat" if field == "vat_rate" else field
            for field, labels in HEADER_FIELDS.items()
            if any(re.search(r"(?:^|\s)" + re.escape(label) + r"(?:\s|$)", normalized) for label in labels)
        }
        if len(matched_headers) > 1:
            matched_headers.discard("amount_column")
        multi_header = layout.coordinates_reliable and (len(matched_headers) >= 2 or line.text in geometric_multi_headers)
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
                if not raw and not multi_header and index + 1 < len(lines):
                    raw = lines[index + 1].text; relation = "next_line"; score = 62
                if not raw: continue
                if relation == "next_line" and _header_field(raw) is not None: continue
                if field in {"supplier", "recipient"} and not _plausible_identity(raw): continue
                values = _normalize_for_field(field, raw)
                if not values and not multi_header and index + 1 < len(lines):
                    raw = lines[index + 1].text; relation = "next_line"; score = 62
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


def _header_field(text):
    normalized = folded(text)
    matches = []
    for field, labels in HEADER_FIELDS.items():
        if any(normalized == label or normalized.startswith(label + " ") for label in labels): matches.append(field)
    if "vencimiento" in normalized or "due date" in normalized or "servicio" in normalized or "service" in normalized:
        matches = [field for field in matches if field != "issue_date"]
    return matches[0] if len(set(matches)) == 1 else None


def _is_semantic_header(text):
    normalized = folded(text)
    return any(normalized == label or normalized.startswith(label + " ") for labels in HEADER_FIELDS.values() for label in labels)


def _table_candidates(document, layout):
    candidates = []
    fiscal_rows = []
    for index, header_row in enumerate(layout.rows[:-1]):
        fields = [_header_field(cell.text) for cell in header_row.cells]
        recognized = [(cell, field) for cell, field in zip(header_row.cells, fields) if field]
        if len(recognized) < 2: continue
        value_row = layout.rows[index + 1]
        pairs = pair_rows(header_row, value_row)
        if not pairs or len(pairs) != len(header_row.cells): continue
        mapped = {}
        for pair, field in zip(pairs, fields):
            if field is None or field in {"due_date", "service_date", "amount_column"}: continue
            values = _normalize_for_field(field if field != "vat_rate" else "vat", pair.value.text)
            if field == "vat_rate":
                rates = RATE_RE.findall(pair.value.text); values = [str(item).replace(",", ".") for item in rates]
            if field == "concept" and folded(pair.value.text) in FORBIDDEN_CONCEPT_VALUES: values = []
            for value in values:
                score = 84 if pair.confidence == "high" else 54 if pair.confidence == "medium" else 28
                if field in {"supplier", "recipient"} and not _plausible_identity(pair.value.text): continue
                candidates.append(_candidate(field, value, document, pair.value, f"table.header.{field}", pair.header.text, "table_header_value", score))
            mapped[field] = pair.value
        fiscal = FiscalRow(mapped.get("taxable_base"), mapped.get("vat_rate"), mapped.get("vat"), mapped.get("other_taxes"), mapped.get("withholdings"), mapped.get("total"), tuple(pair.header for pair in pairs) + tuple(pair.value for pair in pairs))
        if sum(value is not None for value in (fiscal.taxable_base, fiscal.vat_rate, fiscal.vat_amount, fiscal.total)) >= 2:
            fiscal_rows.append(fiscal)
            for extra_row in layout.rows[index + 2:index + 4]:
                if abs(value_row.y - extra_row.y) > 40: break
                extra_pairs = pair_rows(header_row, extra_row)
                if not extra_pairs or len(extra_pairs) != len(header_row.cells): break
                parsed = 0
                for pair, field in zip(extra_pairs, fields):
                    if field not in {"taxable_base", "vat", "total", "other_taxes", "withholdings", "vat_rate"}: continue
                    values = _normalize_for_field("vat" if field == "vat_rate" else field, pair.value.text)
                    if field == "vat_rate": values = [str(item).replace(",", ".") for item in RATE_RE.findall(pair.value.text)]
                    parsed += bool(values)
                    for value in values:
                        candidates.append(_candidate(field, value, document, pair.value, f"table.additional.{field}", pair.header.text, "aligned_below_header", 76))
                if parsed < 2: break
    return candidates, tuple(fiscal_rows)


def _identity_blocks(document, layout):
    candidates = []
    blocks = []
    for index, header_row in enumerate(layout.rows[:-1]):
        roles = [_header_field(cell.text) for cell in header_row.cells]
        if len([role for role in roles if role in {"supplier", "recipient"}]) < 2: continue
        company_row = layout.rows[index + 1]
        company_pairs = pair_rows(header_row, company_row)
        if not company_pairs: continue
        tax_row = layout.rows[index + 2] if index + 2 < len(layout.rows) else None
        tax_pairs = pair_rows(header_row, tax_row) if tax_row else ()
        for position, role in enumerate(roles):
            if role not in {"supplier", "recipient"} or position >= len(company_pairs): continue
            company = company_pairs[position].value
            tax_cell = tax_pairs[position].value if position < len(tax_pairs) else None
            tax_values = [] if tax_cell is None else [re.sub(r"[^A-Z0-9]", "", item.upper()) for item in TAX_ID_RE.findall(tax_cell.text) if valid_spanish_tax_id(item)]
            if not _plausible_identity(company.text): continue
            geometry_score = 90 if company_pairs[position].confidence == "high" else 58
            blocks.append(IdentityBlock(role, company, tax_cell if tax_values else None, (), (header_row.cells[position], company) + ((tax_cell,) if tax_cell else ()), geometry_score))
            candidates.append(_candidate(role, company.text, document, company, f"identity.{role}.company", header_row.cells[position].text, "paired_column", geometry_score))
            tax_field = f"{role}_tax_id"
            for value in tax_values:
                candidates.append(_candidate(tax_field, value, document, tax_cell, f"identity.{role}.tax-id", header_row.cells[position].text, "paired_column", geometry_score + 4))
    return candidates, tuple(blocks)


def _reject_false_concepts(candidates):
    output = []
    for candidate in candidates:
        if candidate.field == "concept" and folded(candidate.value) in FORBIDDEN_CONCEPT_VALUES: continue
        output.append(candidate)
    return output


def _strengthen_arithmetic(candidates):
    by_field = {field: [item for item in candidates if item.field == field] for field in ("taxable_base", "vat", "total")}
    supported = set()
    for base in by_field["taxable_base"]:
        for vat in by_field["vat"]:
            for total in by_field["total"]:
                try: difference = abs(Decimal(base.value) + Decimal(vat.value) - Decimal(total.value))
                except InvalidOperation: continue
                if difference <= ABSOLUTE_TOLERANCE:
                    supported.update((base, vat, total))
    return [item.strengthened(10, relation="arithmetic_support") if item in supported else item for item in candidates]


def generate_candidates(document):
    stored_layout = document.fields.get("layout")
    layout = stored_layout if isinstance(stored_layout, LayoutDocument) else build_layout(str(document.fields.get("text", "")), document.fields.get("fragments", ()))
    candidates = _labeled_candidates(document, layout)
    table_candidates, fiscal_rows = _table_candidates(document, layout)
    identity_candidates, identity_blocks = _identity_blocks(document, layout)
    candidates.extend(table_candidates); candidates.extend(identity_candidates)
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
    return tuple(_strengthen_arithmetic(_reject_false_concepts(candidates)))


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
