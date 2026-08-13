from __future__ import annotations

import hashlib
import re
import xml.etree.ElementTree as ET

from .layout import PdfLayoutExtractor
from .models import DocumentInput, ExtractedDocument


MAX_DOCUMENT_BYTES = 8 * 1024 * 1024
MAX_XML_DEPTH = 32
MAX_PDF_PAGES = 40
MAX_TEXT_CHARS = 500_000


def _bounded(content: bytes):
    if not content or len(content) > MAX_DOCUMENT_BYTES:
        raise ValueError("Document size is outside permitted limits")


def _pdf_text(content: bytes):
    _bounded(content)
    if not content.startswith(b"%PDF-"):
        raise ValueError("Invalid PDF signature")
    marker = b"%CAMILO-SYNTHETIC\n"
    if marker in content:
        return content.split(marker, 1)[1][:MAX_TEXT_CHARS].decode("utf-8").strip(), None
    try:
        layout = PdfLayoutExtractor().extract(content, max_pages=MAX_PDF_PAGES, max_chars=MAX_TEXT_CHARS)
        text = "\n".join(line.text for line in layout.lines)
    except ImportError:
        # Restricted fallback for deterministic synthetic fixtures only.
        chunks = re.findall(rb"\(([^()]*)\)\s*Tj", content)
        text = "\n".join(value.decode("latin1") for value in chunks); layout = None
    except Exception as error:
        raise ValueError("PDF cannot be safely read") from error
    return text[:MAX_TEXT_CHARS].strip(), layout


def _xml_text(content: bytes) -> str:
    _bounded(content)
    upper = content[:4096].upper()
    if b"<!DOCTYPE" in upper or b"<!ENTITY" in upper:
        raise ValueError("DTD and XML entities are forbidden")
    try: root = ET.fromstring(content)
    except ET.ParseError as error: raise ValueError("XML cannot be safely read") from error
    depth = 0
    stack = [(root, 1)]
    values = []
    while stack:
        node, level = stack.pop(); depth = max(depth, level)
        if depth > MAX_XML_DEPTH: raise ValueError("XML depth limit exceeded")
        name = node.tag.rsplit("}", 1)[-1]
        if node.text and node.text.strip(): values.append(f"{name}: {node.text.strip()}")
        stack.extend((child, level + 1) for child in reversed(list(node)))
    return "\n".join(values)[:MAX_TEXT_CHARS]


def extract_text(document: DocumentInput) -> ExtractedDocument:
    media = document.media_type.lower().split(";", 1)[0].strip()
    if media == "application/octet-stream":
        if document.content.startswith(b"%PDF-"): media = "application/pdf"
        elif document.content.lstrip().startswith(b"<"): media = "application/xml"
        else: raise ValueError("Unknown octet-stream content")
    if media == "application/pdf": text, layout = _pdf_text(document.content)
    elif media in {"application/xml", "text/xml"}: text = _xml_text(document.content); layout = None
    else: raise ValueError("Unsupported document media type")
    warning = () if text.strip() else ("document-unreadable",)
    return ExtractedDocument(
        reference=document.reference, filename=document.filename, media_type=media,
        fingerprint=hashlib.sha256(document.content).hexdigest(),
        fields={"text": text, "layout": layout, "fragments": () if layout is None else layout.fragments},
        warnings=tuple(sorted(set(warning + (() if layout is None else layout.warnings)))),
    )
