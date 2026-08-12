from __future__ import annotations

import re
import unicodedata
from datetime import date
from decimal import Decimal, InvalidOperation


LABELS = {
    "invoice_number": ("n factura", "numero factura", "numero de factura", "factura n", "invoice number", "invoice no"),
    "issue_date": ("fecha factura", "fecha de emision", "issue date", "invoice date"),
    "due_date": ("vencimiento", "fecha de vencimiento", "due date"),
    "supplier": ("proveedor", "emisor", "supplier", "seller"),
    "recipient": ("cliente", "destinatario", "receptor", "customer", "bill to"),
    "supplier_tax_id": ("nif proveedor", "cif proveedor", "supplier vat id", "seller tax id"),
    "recipient_tax_id": ("nif cliente", "cif cliente", "recipient tax id", "customer vat id"),
    "taxable_base": ("base imponible", "tax base", "subtotal"),
    "vat": ("cuota iva", "importe iva", "vat amount", "iva"),
    "other_taxes": ("otros impuestos", "recargo", "surcharges"),
    "withholdings": ("retencion", "retenciones", "irpf", "withholding"),
    "total": ("total factura", "importe total", "importe liquido", "amount due", "grand total", "total"),
    "currency": ("moneda", "currency"),
    "concept": ("concepto", "descripcion", "description"),
}

DOCUMENT_MARKERS = (
    ("factura rectificativa", "credit_note"), ("credit note", "credit_note"),
    ("factura simplificada", "simplified_invoice"), ("simplified invoice", "simplified_invoice"),
    ("albaran", "delivery_note"), ("delivery note", "delivery_note"),
    ("estado de pago", "payment_statement"), ("payment statement", "payment_statement"),
    ("recibo", "receipt"), ("receipt", "receipt"),
    ("factura", "invoice"), ("invoice", "invoice"),
)

DATE_RE = re.compile(r"(?<!\d)(\d{4}-\d{1,2}-\d{1,2}|\d{1,2}[/-]\d{1,2}[/-]\d{2,4})(?!\d)")
TAX_ID_RE = re.compile(r"\b(?:[A-Z]{2})?(?:[A-Z]\d{7}[A-Z0-9]|\d{8}[A-Z])\b", re.I)
AMOUNT_RE = re.compile(r"(?<![\w])[-+]?(?:\d{1,3}(?:[.,]\d{3})+|\d+)(?:[.,]\d{2})(?!\d)")
RATE_RE = re.compile(r"(?<!\d)(\d{1,2}(?:[.,]\d{1,2})?)\s*%")
COMPANY_RE = re.compile(r"\b(?:S\.?L\.?U?\.?|S\.?A\.?|COOP\.?|LLC|LTD)\b", re.I)


def folded(value: str) -> str:
    value = unicodedata.normalize("NFKD", value).lower()
    value = "".join(char for char in value if not unicodedata.combining(char))
    value = re.sub(r"[^a-z0-9%]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def normalize_date(value: str) -> str | None:
    parts = re.split(r"[/-]", value)
    try:
        if len(parts[0]) == 4: year, month, day = map(int, parts)
        else:
            day, month, year = map(int, parts)
            if year < 100: year += 2000
        return date(year, month, day).isoformat()
    except (ValueError, TypeError):
        return None


def normalize_amount(value: str) -> str | None:
    value = value.strip().replace(" ", "")
    sign = "-" if value.startswith("-") else ""
    value = value.lstrip("+-")
    if "," in value and "." in value:
        decimal = "," if value.rfind(",") > value.rfind(".") else "."
        thousands = "." if decimal == "," else ","
        value = value.replace(thousands, "").replace(decimal, ".")
    elif "," in value:
        if len(value.rsplit(",", 1)[1]) != 2: return None
        value = value.replace(".", "").replace(",", ".")
    elif "." in value:
        tail = value.rsplit(".", 1)[1]
        if len(tail) != 2: return None
        value = value.replace(",", "")
    try: return format(Decimal(sign + value), "f")
    except InvalidOperation: return None


def valid_spanish_tax_id(value: str) -> bool:
    compact = re.sub(r"[^A-Z0-9]", "", value.upper())
    if not re.fullmatch(r"[A-Z0-9]{8,12}", compact): return False
    # Syntax is always checked; checksum evidence is added for common NIFs.
    if re.fullmatch(r"\d{8}[A-Z]", compact):
        return "TRWAGMYFPDXBNJZSQVHLCKE"[int(compact[:8]) % 23] == compact[-1]
    return bool(re.fullmatch(r"[A-Z]\d{7}[A-Z0-9]", compact) or re.fullmatch(r"[A-Z]{2}[A-Z0-9]{8,10}", compact))
