from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation

from .candidates import EvidenceLink, FieldCandidate
from .layout import FiscalRow, IdentityBlock, LayoutCell, LayoutDocument, LayoutRow, build_layout, pair_rows
from .semantics import (
    AMOUNT_RE, COMPANY_RE, DATE_RE, DOCUMENT_MARKERS, LABELS, RATE_RE,
    TAX_ID_RE, folded, normalize_amount, normalize_date, valid_spanish_tax_id,
)


MIN_SCORE = 35
WIN_MARGIN = 12
FIELD_POLICIES = {
    "supplier": (60, 15), "recipient": (60, 15),
    "supplier_tax_id": (60, 15), "recipient_tax_id": (60, 15),
    "invoice_number": (50, 12), "total": (55, 15),
    "taxable_base": (50, 15), "vat": (50, 15),
    "issue_date": (50, 12),
}
CRITICAL_FIELDS = frozenset({
    "supplier", "recipient", "supplier_tax_id", "recipient_tax_id",
    "invoice_number", "total",
})
ABSOLUTE_TOLERANCE = Decimal("0.02")
FORBIDDEN_CONCEPT_VALUES = frozenset({"importe", "cantidad", "precio", "total", "base", "iva", "%", "% iva"})
NON_IDENTITY_VALUES = frozenset({
    "forma de pago", "importe", "importe liquido", "total", "base", "base imponible",
    "iva", "vencimiento", "concepto", "cantidad", "precio", "fecha", "cliente", "proveedor",
})
INVOICE_NUMBER_VETO_TERMS = frozenset({
    "forma de pago", "transferencia", "vencimiento", "concepto", "descripcion",
    "base imponible", "subtotal", "total", "importe", "precio", "cantidad",
})
NON_TOTAL_HEADERS = frozenset({
    "base", "base imponible", "subtotal", "precio", "precio unitario",
    "cantidad", "importe unitario", "saldo anterior", "pago anterior",
})
HEADER_FIELDS = {
    "invoice_number": ("n factura", "numero factura", "numero de factura", "factura no", "invoice no", "invoice number", "document number"),
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
    "total": ("total", "total factura", "importe total", "importe total factura", "importe liquido", "amount due", "grand total"),
    "concept": ("concepto", "descripcion", "servicio", "detalle", "description"),
    "amount_column": ("importe", "cantidad", "precio", "amount", "quantity", "price"),
}


def _candidate(field, value, document, line, rule, label, relation, score, alternatives=(), *,
               overlap=None, distance=None, geometry=None, block_id=None, table_id=None,
               positive=(), negative=(), veto=False, observation_id=None):
    row_id = getattr(line, "row_id", None)
    page = getattr(line, "page", 1)
    geometry = geometry or getattr(line, "geometry", "insufficient")
    observation_id = observation_id or "|".join((
        str(document.reference), str(page), str(row_id or getattr(line, "order", "linear")),
        str(rule), str(label or ""), str(value),
    ))
    signals = tuple(sorted(set(positive) | ({"explicit_label"} if label else set())))
    evidence = EvidenceLink(
        observation_id, page, row_id, label, str(value), relation,
        overlap, distance, geometry, block_id, table_id, signals,
        tuple(sorted(set(negative))), veto,
    )
    return FieldCandidate(
        field, value, document.reference, page, rule, label, line.text,
        relation, distance, score, tuple(alternatives), evidence,
    )


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
    if DATE_RE.fullmatch(value.strip()) or AMOUNT_RE.fullmatch(value.strip()) or RATE_RE.fullmatch(value.strip()): return False
    if TAX_ID_RE.search(value) and len(value.split()) <= 3: return False
    if any(term in normalized for term in ("forma de pago", "base imponible", "cuota iva", "total factura", "precio unitario")): return False
    return bool(COMPANY_RE.search(value) or (len(value.split()) >= 2 and any(character.isalpha() for character in value)))


def _row_is_table(row):
    fields = [_header_field(cell.text) for cell in row.cells]
    return len([field for field in fields if field]) >= 2 and any(
        field in {"taxable_base", "vat_rate", "vat", "total", "amount_column"}
        for field in fields
    )


def _row_region(cells):
    return (
        min(cell.x0 for cell in cells), min(cell.y for cell in cells),
        max(cell.x1 for cell in cells), max(cell.y for cell in cells),
    )


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
                if (field == "vat" and RATE_RE.search(line.text)
                        and not any(amount_label in normalized for amount_label in ("cuota iva", "importe iva", "vat amount"))
                        and ":" not in line.text):
                    continue
                raw = _right_value(line, label)
                relation = "same_line_right"; score = 72
                if not raw and not multi_header and index + 1 < len(lines):
                    raw = lines[index + 1].text; relation = "next_line"
                    score = 32 if field in CRITICAL_FIELDS else 54
                if not raw: continue
                if relation == "next_line" and _header_field(raw) is not None: continue
                if field in {"supplier", "recipient"} and not _plausible_identity(raw): continue
                values = _normalize_for_field(field, raw)
                if not values and not multi_header and index + 1 < len(lines):
                    raw = lines[index + 1].text; relation = "next_line"
                    score = 32 if field in CRITICAL_FIELDS else 54
                    values = _normalize_for_field(field, raw)
                for value in values:
                    context_lines = lines[max(0, index-4):index+5]
                    linear_table_id = None
                    fiscal_field_names = {"taxable_base", "vat", "other_taxes", "withholdings", "total"}
                    fiscal_roles = {
                        role for item in context_lines for role in fiscal_field_names
                        if any(label in folded(item.text) for label in HEADER_FIELDS[role])
                    }
                    if field in fiscal_field_names and len(fiscal_roles) >= 2:
                        linear_table_id = f"page-{line.page}-linear-fiscal-{max(0, index//8)}"
                    found.append(_candidate(
                        field, value, document, line, f"label.{field}", label,
                        relation, score,
                        positive=("same_cell_value",) if relation == "same_line_right" else ("bounded_next_line",),
                        table_id=linear_table_id,
                        observation_id=f"{document.reference}|{line.page}|{line.order}|{field}|{value}",
                    ))
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
    exact = []
    prefix = []
    for field, labels in HEADER_FIELDS.items():
        if any(normalized == label or normalized.replace(" ", "") == label.replace(" ", "") for label in labels): exact.append(field)
        elif any(normalized.startswith(label + " ") for label in labels): prefix.append(field)
    matches = exact or prefix
    if "vencimiento" in normalized or "due date" in normalized or "servicio" in normalized or "service" in normalized:
        matches = [field for field in matches if field != "issue_date"]
    return matches[0] if len(set(matches)) == 1 else None


def _exact_header_field(text):
    normalized = folded(text)
    matches = [
        field for field, labels in HEADER_FIELDS.items()
        if any(normalized == label or normalized.replace(" ", "") == label.replace(" ", "") for label in labels)
    ]
    return matches[0] if len(set(matches)) == 1 else None


def _fiscal_header_field(text):
    field = _header_field(text)
    normalized = folded(text)
    if normalized == "cuota":
        return "vat"
    if (field == "vat" and RATE_RE.search(text)
            and not any(label in normalized for label in ("cuota iva", "importe iva", "vat amount"))):
        return "vat_rate"
    return field


def _is_semantic_header(text):
    normalized = folded(text)
    return any(normalized == label or normalized.startswith(label + " ") for labels in HEADER_FIELDS.values() for label in labels)


def _composed_header_cells(row):
    cells = list(row.cells)
    output = []
    index = 0
    while index < len(cells):
        match = None
        for width in (3, 2):
            group = cells[index:index + width]
            if len(group) != width: continue
            if any(right.x0-left.x1 > 28 for left, right in zip(group, group[1:])): continue
            variants = (" ".join(cell.text for cell in group), "".join(cell.text for cell in group))
            text = next((value for value in variants if _exact_header_field(value)), None)
            if text:
                match = LayoutCell(
                    text, row.page, row.row_id, group[0].x0, group[-1].x1, row.y,
                    tuple(fragment for cell in group for fragment in cell.fragments),
                    "observed" if all(cell.geometry == "observed" for cell in group) else "estimated",
                )
                break
        if match is not None:
            output.append(match); index += width
        else:
            output.append(cells[index]); index += 1
    return tuple(output)


def _table_candidates(document, layout):
    candidates = []
    fiscal_rows = []
    consumed_headers = set()
    recent_fiscal_tables = {}
    for index, first_header_row in enumerate(layout.rows):
        if index in consumed_headers: continue
        header_cells = list(_composed_header_cells(first_header_row))
        first_fields = [_header_field(cell.text) for cell in header_cells]
        if index + 1 < len(layout.rows):
            continuation = layout.rows[index + 1]
            continuation_cells = _composed_header_cells(continuation)
            continuation_fields = [_header_field(cell.text) for cell in continuation_cells]
            fiscal_roles = {"taxable_base", "vat_rate", "vat", "other_taxes", "withholdings", "total"}
            first_fiscal = {field for field in first_fields if field in fiscal_roles}
            continuation_fiscal = {field for field in continuation_fields if field in fiscal_roles}
            if (first_header_row.page == continuation.page
                    and any(field in fiscal_roles for field in first_fields)
                    and any(field in fiscal_roles for field in continuation_fields)
                    and bool(continuation_fiscal - first_fiscal)
                    and not any(AMOUNT_RE.fullmatch(cell.text.strip()) for cell in continuation.cells)):
                header_cells.extend(continuation_cells); consumed_headers.add(index + 1)
        header_cells.sort(key=lambda cell: (cell.x0, -cell.y))
        fields = [_fiscal_header_field(cell.text) for cell in header_cells]
        recognized = [(cell, field) for cell, field in zip(header_cells, fields) if field]
        if len(recognized) == 1 and len(first_header_row.cells) >= 2:
            header, field = recognized[0]
            if field == "vat" and folded(header.text) == "cuota":
                continue
            right_values = [cell for cell in first_header_row.cells if cell.x0 >= header.x1 and cell is not header]
            if right_values and field not in {"due_date", "service_date", "amount_column", "vat_rate"}:
                value_cell = sorted(right_values, key=lambda cell: (cell.x0-header.x1, cell.text))[0]
                values = _normalize_for_field(field, value_cell.text)
                if field == "concept" and folded(value_cell.text) in FORBIDDEN_CONCEPT_VALUES: values = []
                if field not in {"supplier", "recipient"} or _plausible_identity(value_cell.text):
                    for value in values:
                        inline_table_id = f"page-{first_header_row.page}-inline-{index}"
                        recent = recent_fiscal_tables.get(first_header_row.page)
                        if field == "total" and recent and index-recent[1] <= 3:
                            inline_table_id = recent[0]
                        candidates.append(_candidate(
                            field, value, document, value_cell, f"row.inline.{field}",
                            header.text, "same_line_right", 82 if value_cell.geometry == "observed" else 56,
                            geometry=value_cell.geometry,
                            table_id=inline_table_id,
                            positive=("same_row_value", "fiscal_table_closure") if inline_table_id == (recent[0] if recent else None) else ("same_row_value",),
                            observation_id=f"{document.reference}|{first_header_row.row_id}|{field}|{value}",
                        ))
        if len(recognized) < 2: continue
        header_row = LayoutRow(
            f"{first_header_row.row_id}:band", first_header_row.page,
            min(cell.y for cell in header_cells), tuple(header_cells),
            first_header_row.confidence,
            "observed" if all(cell.geometry == "observed" for cell in header_cells) else "estimated",
        )
        table_id = f"page-{header_row.page}-table-{index}"
        value_rows = []
        start = index + 1 + (1 if index + 1 in consumed_headers else 0)
        for candidate_row in layout.rows[start:start + 3]:
            if candidate_row.page != header_row.page or header_row.y - candidate_row.y > 72: break
            candidate_fields = [_header_field(cell.text) for cell in candidate_row.cells]
            if len([field for field in candidate_fields if field]) >= 2: break
            pairs = pair_rows(header_row, candidate_row)
            if pairs and len(pairs) == len(header_cells):
                value_rows.append((candidate_row, pairs))
        if not value_rows: continue
        table_has_fiscal = False
        for value_row, pairs in value_rows:
            mapped = {}
            parsed_fields = set()
            for pair, field in zip(pairs, fields):
                if field is None or field in {"due_date", "service_date", "amount_column"}: continue
                values = _normalize_for_field(field if field != "vat_rate" else "vat", pair.value.text)
                if field == "vat_rate":
                    rates = RATE_RE.findall(pair.value.text); values = [str(item).replace(",", ".") for item in rates]
                if field == "concept" and folded(pair.value.text) in FORBIDDEN_CONCEPT_VALUES: values = []
                for value in values:
                    score = 84 if pair.confidence == "high" else 54 if pair.confidence == "medium" else 28
                    if field in {"supplier", "recipient"} and not _plausible_identity(pair.value.text): continue
                    candidates.append(_candidate(
                        field, value, document, pair.value, f"table.header.{field}",
                        pair.header.text, "table_header_value", score,
                        overlap=pair.horizontal_overlap, distance=pair.vertical_distance,
                        geometry=pair.value.geometry, table_id=table_id,
                        positive=("header_column_alignment", pair.confidence),
                        observation_id=f"{document.reference}|{table_id}|{value_row.row_id}|{field}",
                    ))
                    parsed_fields.add(field)
                mapped[field] = pair.value
            fiscal = FiscalRow(
                table_id, value_row.row_id, mapped.get("taxable_base"), mapped.get("vat_rate"),
                mapped.get("vat"), mapped.get("other_taxes"), mapped.get("withholdings"),
                mapped.get("total"), tuple(pair.header for pair in pairs) + tuple(pair.value for pair in pairs),
                value_row.geometry, value_row.confidence,
            )
            if len(parsed_fields & {"taxable_base", "vat_rate", "vat", "total"}) >= 2:
                fiscal_rows.append(fiscal)
                table_has_fiscal = True
        if table_has_fiscal:
            last_value_index = max(layout.rows.index(value_row) for value_row, _ in value_rows)
            recent_fiscal_tables[header_row.page] = (table_id, last_value_index)
    return candidates, tuple(fiscal_rows)


def _identity_blocks(document, layout):
    candidates = []
    blocks = []
    claimed_companies = set()

    def aligned_cell(header, rows, *, require_company=False, require_tax=False, role_headers=()):
        ranked = []
        for row_offset, row in rows:
            if row.page != header.page or header.y - row.y > 72: break
            if _row_is_table(row): continue
            for cell in row.cells:
                if require_company and not _plausible_identity(cell.text): continue
                tax_values = [
                    re.sub(r"[^A-Z0-9]", "", item.upper())
                    for item in TAX_ID_RE.findall(cell.text) if valid_spanish_tax_id(item)
                ]
                if require_tax and not tax_values: continue
                horizontal = max(0., min(header.x1, cell.x1) - max(header.x0, cell.x0))
                horizontal /= max(1., min(header.x1-header.x0, cell.x1-cell.x0))
                distance = abs(header.center-cell.center)
                relative = distance/max(25., header.x1-header.x0)
                region_owned = False
                if len(role_headers) >= 2:
                    ownership = sorted((abs(owner.center-cell.center), owner.center, owner) for owner in role_headers)
                    owner_span = max(owner.center for owner in role_headers) - min(owner.center for owner in role_headers)
                    if len(ownership) > 1 and ownership[1][0]-ownership[0][0] <= max(12., owner_span*.05): continue
                    if ownership[0][2] is not header: continue
                    region_owned = True
                if not region_owned and horizontal < .10 and relative > 1.2: continue
                ranked.append((distance, -horizontal, row_offset, cell, tax_values))
        ranked.sort(key=lambda item: ((item[2], item[0]) if require_company else (item[0], item[2]), item[1], item[3].text))
        if not ranked: return None
        if len(ranked) > 1 and abs(ranked[1][0]-ranked[0][0]) < 8 and max(-ranked[0][1], -ranked[1][1]) < .3:
            return None
        return ranked[0]

    for index, header_row in enumerate(layout.rows[:-1]):
        if _row_is_table(header_row): continue
        composed_headers = _composed_header_cells(header_row)
        role_headers = tuple(
            cell for cell in composed_headers
            if _header_field(cell.text) in {"supplier", "recipient"}
        )
        for header in composed_headers:
            role = _header_field(header.text)
            if role not in {"supplier", "recipient"}: continue
            following = tuple(enumerate(layout.rows[index + 1:index + 4], 1))
            company_match = aligned_cell(header, following, require_company=True, role_headers=role_headers)
            if company_match is None: continue
            _, negative_overlap, company_offset, company, _ = company_match
            company_index = index + company_offset
            claimed_companies.add((company.page, company.row_id, company.text))
            tax_following = tuple(enumerate(layout.rows[company_index + 1:company_index + 4], 1))
            tax_match = aligned_cell(header, tax_following, require_tax=True, role_headers=role_headers)
            tax_cell = tax_match[3] if tax_match else None
            tax_values = tax_match[4] if tax_match else []
            nearby_cells = tuple(
                cell for row in layout.rows[company_index + 1:company_index + 3]
                for cell in row.cells
                if cell is not tax_cell and abs(cell.center-header.center) <= max(60., header.x1-header.x0)
                and not _is_semantic_header(cell.text)
                and not AMOUNT_RE.fullmatch(cell.text.strip())
            )
            block_id = f"page-{header.page}-identity-{index}-{len(blocks)}"
            geometry = "observed" if header.geometry == company.geometry == "observed" else "estimated"
            score = 90 if geometry == "observed" else 64
            positives = ["explicit_role", "company_in_column"]
            if tax_values: positives.append("tax_id_in_block")
            if nearby_cells: positives.append("address_or_descriptor")
            evidence_cells = (header, company) + ((tax_cell,) if tax_cell else ()) + nearby_cells
            blocks.append(IdentityBlock(
                block_id, role, company, tax_cell if tax_values else None, nearby_cells,
                evidence_cells, _row_region(evidence_cells), tuple(positives), (), score,
            ))

    # Unlabelled blocks may corroborate the counterpart, but never acquire a
    # role from page position alone.
    unlabelled = []
    for index, row in enumerate(layout.rows[:-1]):
        if _row_is_table(row): continue
        for company in row.cells:
            key = (company.page, company.row_id, company.text)
            if key in claimed_companies or not COMPANY_RE.search(company.text) or not _plausible_identity(company.text): continue
            tax_rows = layout.rows[index + 1:index + 3]
            matches = []
            for tax_row in tax_rows:
                if tax_row.page != company.page: continue
                for tax_cell in tax_row.cells:
                    values = [re.sub(r"[^A-Z0-9]", "", item.upper()) for item in TAX_ID_RE.findall(tax_cell.text) if valid_spanish_tax_id(item)]
                    if not values: continue
                    distance = abs(company.center-tax_cell.center)
                    overlap_value = max(0., min(company.x1, tax_cell.x1)-max(company.x0, tax_cell.x0))/max(1., min(company.x1-company.x0, tax_cell.x1-tax_cell.x0))
                    if overlap_value >= .10 or distance <= max(50., company.x1-company.x0):
                        matches.append((distance, -overlap_value, tax_cell, values))
            matches.sort(key=lambda item: (item[0], item[1], item[2].text))
            if not matches or (len(matches) > 1 and abs(matches[1][0]-matches[0][0]) < 8): continue
            _, _, tax_cell, tax_values = matches[0]
            block_id = f"page-{company.page}-identity-unlabelled-{index}-{len(unlabelled)}"
            evidence_cells = (company, tax_cell)
            unlabelled.append((IdentityBlock(
                block_id, "unknown", company, tax_cell, (), evidence_cells,
                _row_region(evidence_cells), ("company_with_tax_id",), (), 66,
            ), tax_values))

    if len(blocks) == 1 and len(unlabelled) == 1:
        inferred_role = "recipient" if blocks[0].role == "supplier" else "supplier"
        block, tax_values = unlabelled[0]
        blocks.append(IdentityBlock(
            block.block_id, inferred_role, block.company, block.tax_id, (), block.evidence_cells,
            block.region, block.positive_signals + ("explicit_opposite_counterpart",), (), 68,
        ))
    elif len(unlabelled) == 2 and not blocks:
        # Preserve both interpretations as equal candidates so each critical
        # role resolves to conflict instead of page-order guessing.
        for block, _ in unlabelled:
            for role in ("supplier", "recipient"):
                blocks.append(IdentityBlock(
                    f"{block.block_id}:{role}", role, block.company, block.tax_id, (),
                    block.evidence_cells, block.region, block.positive_signals,
                    ("role_ambiguous",), 68,
                ))

    tax_owners = {}
    for block in blocks:
        if block.tax_id is None: continue
        for value in [re.sub(r"[^A-Z0-9]", "", item.upper()) for item in TAX_ID_RE.findall(block.tax_id.text) if valid_spanish_tax_id(item)]:
            tax_owners.setdefault(value, set()).add(block.block_id.split(":", 1)[0])

    for block in blocks:
        if block.role not in {"supplier", "recipient"} or block.company is None: continue
        veto = "role_ambiguous" in block.negative_signals
        candidates.append(_candidate(
            block.role, block.company.text, document, block.company,
            f"identity.{block.role}.company", block.role, "paired_column", block.score,
            geometry=block.company.geometry, block_id=block.block_id,
            positive=block.positive_signals, negative=block.negative_signals, veto=False,
            observation_id=f"{document.reference}|{block.block_id}|company|{block.role}",
        ))
        if block.tax_id is None: continue
        for value in [re.sub(r"[^A-Z0-9]", "", item.upper()) for item in TAX_ID_RE.findall(block.tax_id.text) if valid_spanish_tax_id(item)]:
            if len(tax_owners.get(value, ())) != 1: continue
            candidates.append(_candidate(
                f"{block.role}_tax_id", value, document, block.tax_id,
                f"identity.{block.role}.tax-id", block.role, "paired_column", block.score + 4,
                geometry=block.tax_id.geometry, block_id=block.block_id,
                positive=block.positive_signals + ("unique_tax_ownership",),
                negative=block.negative_signals, veto=veto,
                observation_id=f"{document.reference}|{block.block_id}|tax-id|{block.role}",
            ))
    return candidates, tuple(blocks)


def _reject_false_concepts(candidates):
    output = []
    for candidate in candidates:
        if candidate.field == "concept" and folded(candidate.value) in FORBIDDEN_CONCEPT_VALUES: continue
        output.append(candidate)
    return output


def _strengthen_arithmetic(candidates, fiscal_rows=()):
    by_field = {field: [item for item in candidates if item.field == field] for field in ("taxable_base", "vat", "total")}
    structured_tables = {row.table_id for row in fiscal_rows}
    supported = set()
    for base in by_field["taxable_base"]:
        for vat in by_field["vat"]:
            for total in by_field["total"]:
                table_ids = {
                    item.evidence.table_id for item in (base, vat, total)
                    if item.evidence is not None and item.evidence.table_id is not None
                }
                if len(table_ids) != 1 or any(
                    item.evidence is None or item.evidence.table_id not in table_ids
                    for item in (base, vat, total)
                ): continue
                table_id = next(iter(table_ids))
                row_ids = {item.evidence.row_id for item in (base, vat, total) if item.evidence.row_id}
                same_row = len(row_ids) == 1
                labeled_closure = total.evidence.header is not None and _header_field(total.evidence.header) == "total"
                if not same_row and not (
                    (table_id in structured_tables or "linear-fiscal" in table_id)
                    and labeled_closure
                ): continue
                try: difference = abs(Decimal(base.value) + Decimal(vat.value) - Decimal(total.value))
                except InvalidOperation: continue
                if difference <= ABSOLUTE_TOLERANCE:
                    supported.update((base, vat, total))
    return [item.strengthened(24, relation="arithmetic_support") if item in supported else item for item in candidates]


def generate_candidates(document):
    stored_layout = document.fields.get("layout")
    layout = stored_layout if isinstance(stored_layout, LayoutDocument) else build_layout(str(document.fields.get("text", "")), document.fields.get("fragments", ()))
    candidates = _labeled_candidates(document, layout)
    table_candidates, fiscal_rows = _table_candidates(document, layout)
    identity_candidates, identity_blocks = _identity_blocks(document, layout)
    candidates.extend(table_candidates); candidates.extend(identity_candidates)
    lines = layout.lines
    table_texts = {cell.text for row in layout.rows if _row_is_table(row) for cell in row.cells}
    for index, line in enumerate(lines):
        normalized = folded(line.text)
        if index + 1 < len(lines) and all(term in normalized for term in ("base imponible", "iva", "total")):
            amounts = [value for value in (normalize_amount(item) for item in AMOUNT_RE.findall(lines[index + 1].text)) if value]
            if len(amounts) == 3:
                for field, value in zip(("taxable_base", "vat", "total"), amounts):
                    candidates.append(_candidate(
                        field, value, document, line, "table.fiscal-summary", field,
                        "table_row", 68, table_id=f"page-{line.page}-linear-summary-{index}",
                        positive=("complete_fiscal_summary",),
                    ))
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
            if field != "tax_id_unassigned": candidates.append(_candidate(
                field, tax_id, document, line, "tax-id.context", None, "same_block",
                score + (8 if valid_spanish_tax_id(tax_id) else 0),
                positive=("explicit_role_context", "valid_tax_id"),
                observation_id=f"{document.reference}|{line.page}|{line.order}|tax-id|{tax_id}",
            ))
        if COMPANY_RE.search(line.text):
            if line.text in table_texts: continue
            if any(label in normalized for label in ("proveedor", "emisor", "supplier", "seller", "cliente", "destinatario", "customer", "bill to")):
                continue
            nearby = " ".join(folded(item.text) for item in lines[max(0, index - 1):index + 2])
            if any(term in nearby for term in ("cliente", "destinatario", "customer", "bill to")):
                field, score, negative = "recipient", 46, ("unstructured_identity",)
            elif any(term in nearby for term in ("proveedor", "emisor", "supplier", "seller")):
                field, score, negative = "supplier", 46, ("unstructured_identity",)
            else:
                # Page position alone is retained only as diagnostic evidence.
                field = "supplier" if index < max(3, len(lines) // 3) else "recipient"
                score, negative = 24, ("role_inferred_from_page_position",)
            candidates.append(_candidate(
                field, line.text.strip(), document, line, "company.block", None,
                "same_block", score, negative=negative,
            ))
        if "€" in line.text or re.search(r"\bEUR\b", line.text, re.I):
            candidates.append(_candidate("currency", "EUR", document, line, "currency.marker", None, "same_block", 62))
    return tuple(_strengthen_arithmetic(_reject_false_concepts(candidates), fiscal_rows))


def _field(value, source, status="extracted", confidence="high"):
    return {"confidence": confidence, "source_ref": source, "status": status, "value": value}


def _evidence_provenance(candidate):
    evidence = candidate.evidence
    if evidence is None:
        return ("legacy", candidate.rule_id, candidate.evidence_text)
    if evidence.row_id is None:
        return ("observation", evidence.observation_id)
    return (
        "physical", evidence.page, evidence.row_id,
        evidence.block_id, evidence.table_id, evidence.value,
    )


def _semantic_veto(field, candidate):
    value = str(candidate.value).strip()
    normalized = folded(value)
    raw_header = candidate.evidence.header if candidate.evidence and candidate.evidence.header else candidate.label or ""
    header = folded(raw_header)
    if field == "invoice_number":
        compact_tax_id = re.sub(r"[^A-Z0-9]", "", value.upper())
        return (
            not any(character.isdigit() for character in value)
            or DATE_RE.fullmatch(value) is not None
            or AMOUNT_RE.fullmatch(value) is not None
            or RATE_RE.fullmatch(value) is not None
            or (TAX_ID_RE.fullmatch(value) is not None and valid_spanish_tax_id(compact_tax_id))
            or normalized in INVOICE_NUMBER_VETO_TERMS
            or any(normalized.startswith(term + " ") for term in INVOICE_NUMBER_VETO_TERMS)
        )
    if field == "total":
        return header in NON_TOTAL_HEADERS or any(header.startswith(term + " ") for term in NON_TOTAL_HEADERS)
    if field in {"supplier", "recipient"}:
        return not _plausible_identity(value)
    if field in {"supplier_tax_id", "recipient_tax_id"}:
        return not valid_spanish_tax_id(value)
    return False


def resolve_field(field, candidates):
    if field == "document_type":
        strong = [
            candidate for candidate in candidates
            if candidate.field == field
            and candidate.rule_id == "document.marker"
            and candidate.score >= 52
        ]
        strong_types = {candidate.value for candidate in strong}
        invoice_family = {"invoice", "credit_note", "simplified_invoice"}
        if len(strong_types) > 1 and not strong_types <= invoice_family:
            observations = {
                value: {
                    candidate.evidence.observation_id
                    for candidate in strong
                    if candidate.value == value and candidate.evidence
                }
                for value in strong_types
            }
            exact_types = {
                candidate.value for candidate in strong if candidate.score >= 70
            }
            if len(exact_types) > 1:
                return _field(None, "multiple-document-types", "conflict", "low")
            if len(exact_types) == 1:
                exact_type = next(iter(exact_types))
                if any(
                    len(links) >= 3 and len(links) > len(observations[exact_type])
                    for value, links in observations.items() if value != exact_type
                ):
                    return _field(None, "multiple-document-types", "conflict", "low")
    grouped = {}
    for candidate in candidates:
        if candidate.field == field:
            grouped.setdefault(candidate.value, []).append(candidate)
    ranked = []
    for value, value_candidates in grouped.items():
        observations = {}
        for candidate in value_candidates:
            observation = candidate.evidence.observation_id if candidate.evidence else f"legacy:{candidate.rule_id}:{candidate.evidence_text}"
            current = observations.get(observation)
            if current is None or candidate.score > current.score: observations[observation] = candidate
        independent = tuple(observations.values())
        if (any(candidate.evidence and candidate.evidence.veto for candidate in independent)
                or any(_semantic_veto(field, candidate) for candidate in independent)):
            continue
        winner = sorted(independent, key=lambda item: (-item.score, item.rule_id, item.value))[0]
        provenance = {}
        for candidate in independent:
            key = _evidence_provenance(candidate)
            current = provenance.get(key)
            if current is None or candidate.score > current.score:
                provenance[key] = candidate
        negatives = {
            signal for candidate in independent if candidate.evidence
            for signal in candidate.evidence.negative_signals
        }
        score = winner.score + min(16, 8 * (len(provenance)-1)) - min(24, 8 * len(negatives))
        if field == "invoice_number" and any(
            candidate.field == "document_type" and candidate.score >= 52 for candidate in candidates
        ):
            score += 18
        if (field == "issue_date" and winner.rule_id == "date.context"
                and any(candidate.field == "document_type" and candidate.score >= 52 for candidate in candidates)):
            score += 4
        links = tuple(candidate.evidence for candidate in independent if candidate.evidence)
        if field in {"supplier", "recipient"} and not any(
            link.block_id or (link.relation == "same_line_right" and "explicit_label" in link.positive_signals)
            for link in links
        ): continue
        if field in {"supplier_tax_id", "recipient_tax_id"} and not any(
            link.block_id or (link.relation == "same_line_right" and "explicit_label" in link.positive_signals)
            or "explicit_label" in link.positive_signals
            for link in links
        ): continue
        ranked.append((score, winner, links))
    threshold, margin = FIELD_POLICIES.get(field, (MIN_SCORE, WIN_MARGIN))
    ranked.sort(key=lambda item: (-item[0], item[1].value))
    if (len(ranked) > 1 and ranked[0][0] - ranked[1][0] < margin
            and ranked[0][0] >= min(threshold, 32)
            and ranked[1][0] >= min(threshold, 32)):
        return _field(None, "multiple-candidates", "conflict", "low")
    if not ranked or ranked[0][0] < threshold: return _field(None, "none", "unknown", "low")
    if len(ranked) > 1 and ranked[0][0] - ranked[1][0] < margin:
        return _field(None, "multiple-candidates", "conflict", "low")
    score, winner, _ = ranked[0]
    confidence = "high" if score >= 65 else "medium"
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
