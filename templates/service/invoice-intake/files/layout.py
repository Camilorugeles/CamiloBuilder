from __future__ import annotations

import io
import math
import re
import unicodedata
from dataclasses import dataclass


GEOMETRY_LEVELS = frozenset({"observed", "estimated", "insufficient"})


@dataclass(frozen=True)
class TextFragment:
    text: str
    page: int
    x0: float | None
    y0: float | None
    x1: float | None
    y1: float | None
    font_size: float
    order: int
    geometry: str


@dataclass(frozen=True)
class TextLine:
    text: str
    page: int
    order: int
    x: float | None = None
    y: float | None = None


@dataclass(frozen=True)
class LayoutCell:
    text: str
    page: int
    row_id: str
    x0: float
    x1: float
    y: float
    fragments: tuple[TextFragment, ...]
    geometry: str

    @property
    def center(self): return (self.x0 + self.x1) / 2


@dataclass(frozen=True)
class LayoutRow:
    row_id: str
    page: int
    y: float
    cells: tuple[LayoutCell, ...]
    confidence: str
    geometry: str


@dataclass(frozen=True)
class HeaderValuePair:
    header: LayoutCell
    value: LayoutCell
    relation: str
    horizontal_overlap: float
    vertical_distance: float
    confidence: str


@dataclass(frozen=True)
class IdentityBlock:
    role: str
    company: LayoutCell | None
    tax_id: LayoutCell | None
    address_cells: tuple[LayoutCell, ...]
    evidence_cells: tuple[LayoutCell, ...]
    score: int


@dataclass(frozen=True)
class FiscalRow:
    taxable_base: LayoutCell | None
    vat_rate: LayoutCell | None
    vat_amount: LayoutCell | None
    other_tax: LayoutCell | None
    withholding: LayoutCell | None
    total: LayoutCell | None
    evidence_cells: tuple[LayoutCell, ...]


@dataclass(frozen=True)
class LayoutPage:
    number: int
    fragments: tuple[TextFragment, ...]
    rows: tuple[LayoutRow, ...]


@dataclass(frozen=True)
class LayoutDocument:
    pages: tuple[LayoutPage, ...]
    fragments: tuple[TextFragment, ...]
    lines: tuple[TextLine, ...]
    rows: tuple[LayoutRow, ...]
    reading_order: tuple[int, ...]
    geometry: str
    warnings: tuple[str, ...]

    @property
    def coordinates_reliable(self): return self.geometry == "observed"


DocumentLayout = LayoutDocument


def clean_text(value: str) -> str:
    value = unicodedata.normalize("NFC", value).replace("\u00a0", " ")
    return re.sub(r"[ \t]+", " ", value).strip()


def _multiply(left, right):
    a, b, c, d, e, f = left; g, h, i, j, k, l = right
    return (a*g+c*h, b*g+d*h, a*i+c*j, b*i+d*j, a*k+c*l+e, b*k+d*l+f)


def _operand_text(value):
    if isinstance(value, bytes): return value.decode("latin1", errors="replace")
    return str(value)


def _text_width(text, size):
    # Conservative Helvetica-like estimate. It is evidence for grouping, not a
    # claim about exact glyph metrics.
    return max(size, size * .35 * len(text))


class PdfLayoutExtractor:
    """Private pypdf boundary: PDF bytes in, neutral LayoutDocument out."""

    def extract(self, content: bytes, *, max_pages: int, max_chars: int):
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(content), strict=True)
        if len(reader.pages) > max_pages: raise ValueError("PDF page limit exceeded")
        fragments = []
        page_text = []
        warnings = []
        for page_number, page in enumerate(reader.pages, 1):
            page_text.append(page.extract_text() or "")
            extracted, page_warnings = self._page_fragments(page, page_number)
            fragments.extend(extracted); warnings.extend(page_warnings)
        text = "\n".join(page_text)[:max_chars].strip()
        return build_layout(text, fragments, warnings=warnings)

    def _page_fragments(self, page, page_number):
        contents = page.get_contents()
        if contents is None or not hasattr(contents, "operations"):
            return (), (f"page-{page_number}:geometry-insufficient",)
        identity = (1., 0., 0., 1., 0., 0.)
        ctm = identity; text_matrix = identity; line_matrix = identity
        stack = []; leading = 0.; font_size = 10.; fragments = []; warnings = []
        for operands, operator in contents.operations:
            if operator == b"q": stack.append(ctm)
            elif operator == b"Q": ctm = stack.pop() if stack else identity
            elif operator == b"cm" and len(operands) >= 6:
                ctm = _multiply(ctm, tuple(float(value) for value in operands[:6]))
            elif operator == b"BT": text_matrix = line_matrix = identity
            elif operator == b"Tf" and len(operands) >= 2: font_size = max(1., abs(float(operands[1])))
            elif operator == b"TL" and operands: leading = float(operands[0])
            elif operator == b"Tm" and len(operands) >= 6:
                text_matrix = line_matrix = tuple(float(value) for value in operands[:6])
            elif operator in {b"Td", b"TD"} and len(operands) >= 2:
                tx, ty = float(operands[0]), float(operands[1])
                if operator == b"TD": leading = -ty
                line_matrix = _multiply(line_matrix, (1., 0., 0., 1., tx, ty)); text_matrix = line_matrix
            elif operator == b"T*":
                line_matrix = _multiply(line_matrix, (1., 0., 0., 1., 0., -leading)); text_matrix = line_matrix
            elif operator in {b"Tj", b"TJ"} and operands:
                if operator == b"Tj": parts = (_operand_text(operands[0]),)
                else: parts = tuple(_operand_text(item) for item in operands[0] if not isinstance(item, (int, float)))
                text = clean_text("".join(parts))
                if not text: continue
                matrix = _multiply(ctm, text_matrix)
                x, y = matrix[4], matrix[5]
                scale_x = math.hypot(matrix[0], matrix[1]); scale_y = math.hypot(matrix[2], matrix[3])
                geometry = "observed" if scale_x > .01 and (scale_y > .01 or abs(matrix[3]) > .01) else "estimated"
                width = _text_width(text, font_size) * max(scale_x, .25)
                height = font_size * max(scale_y, abs(matrix[3]), .25)
                fragments.append(TextFragment(text, page_number, x, y, x + width, y + height, font_size, len(fragments), geometry))
                advance = _text_width(text, font_size)
                text_matrix = _multiply(text_matrix, (1., 0., 0., 1., advance, 0.))
        if not fragments: warnings.append(f"page-{page_number}:geometry-insufficient")
        return tuple(fragments), tuple(warnings)


class PdfPlumberLayoutExtractor:
    """Private diagnostic fallback producing the same neutral layout model."""

    def extract(self, content: bytes, *, max_pages: int, max_chars: int):
        import pdfplumber

        fragments = []
        text_parts = []
        warnings = []
        with pdfplumber.open(io.BytesIO(content)) as document:
            if len(document.pages) > max_pages:
                raise ValueError("PDF page limit exceeded")
            for page_number, page in enumerate(document.pages, 1):
                words = page.extract_words(
                    x_tolerance=2,
                    y_tolerance=3,
                    keep_blank_chars=False,
                    use_text_flow=False,
                )
                for word in words:
                    value = clean_text(str(word.get("text", "")))
                    if not value:
                        continue
                    x0 = float(word["x0"]); x1 = float(word["x1"])
                    y0 = float(page.height) - float(word["bottom"])
                    y1 = float(page.height) - float(word["top"])
                    fragments.append(TextFragment(
                        value, page_number, x0, y0, x1, y1,
                        max(1., y1 - y0), len(fragments), "observed",
                    ))
                    text_parts.append(value)
                if not words:
                    warnings.append(f"page-{page_number}:geometry-insufficient")
        text = "\n".join(text_parts)[:max_chars]
        return build_layout(text, fragments, warnings=warnings)


def _layout_quality(layout: LayoutDocument):
    multi_cell_rows = sum(len(row.cells) >= 2 for row in layout.rows)
    populated_rows = sum(bool(row.cells) for row in layout.rows)
    singleton_ratio = (
        sum(len(row.cells) == 1 for row in layout.rows) / populated_rows
        if populated_rows else 1.
    )
    return (
        layout.geometry == "observed",
        multi_cell_rows,
        -singleton_ratio,
        len(layout.fragments),
    )


def layout_needs_fallback(layout: LayoutDocument):
    """Detect structural insufficiency without interpreting invoice fields."""
    if layout.geometry != "observed" or not layout.fragments:
        return True
    populated_rows = [row for row in layout.rows if row.cells]
    if not populated_rows:
        return True
    singleton_ratio = sum(len(row.cells) == 1 for row in populated_rows) / len(populated_rows)
    return len(layout.fragments) >= 200 and singleton_ratio >= .80


class HybridPdfLayoutExtractor:
    """pypdf first; guarded pdfplumber fallback on structural insufficiency."""

    def __init__(self, primary=None, fallback=None):
        self.primary = primary or PdfLayoutExtractor()
        self.fallback = fallback or PdfPlumberLayoutExtractor()

    def extract(self, content: bytes, *, max_pages: int, max_chars: int):
        try:
            primary = self.primary.extract(content, max_pages=max_pages, max_chars=max_chars)
        except Exception as primary_error:
            try:
                fallback = self.fallback.extract(content, max_pages=max_pages, max_chars=max_chars)
            except Exception:
                raise primary_error
            return _with_warning(fallback, "layout-fallback:primary-unavailable")
        if not layout_needs_fallback(primary):
            return primary
        try:
            fallback = self.fallback.extract(content, max_pages=max_pages, max_chars=max_chars)
        except Exception:
            return _with_warning(primary, "layout-fallback:unavailable")
        if _layout_quality(fallback) <= _layout_quality(primary):
            return _with_warning(primary, "layout-fallback:not-better")
        return _with_warning(fallback, "layout-fallback:selected")


def _with_warning(layout: LayoutDocument, warning: str):
    return LayoutDocument(
        layout.pages, layout.fragments, layout.lines, layout.rows,
        layout.reading_order, layout.geometry,
        tuple(sorted(set(layout.warnings + (warning,)))),
    )


def _geometry(items):
    levels = {item.geometry for item in items}
    if levels == {"observed"}: return "observed"
    if "observed" in levels or "estimated" in levels: return "estimated"
    return "insufficient"


def _rows(positioned):
    groups = []
    for fragment in sorted(positioned, key=lambda item: (item.page, -(item.y0 or 0), item.x0 or 0, item.order)):
        match = next((row for row in groups if row[0].page == fragment.page and abs((row[0].y0 or 0) - (fragment.y0 or 0)) <= max(2., min(row[0].font_size, fragment.font_size) * .35)), None)
        if match is None: groups.append([fragment])
        else: match.append(fragment)
    rows = []
    for row_index, fragments in enumerate(groups):
        fragments.sort(key=lambda item: (item.x0 or 0, item.order)); cells = []; current = []
        for fragment in fragments:
            if current and (fragment.x0 or 0) - (current[-1].x1 or 0) > max(12., fragment.font_size * 1.5):
                cells.append(current); current = []
            current.append(fragment)
        if current: cells.append(current)
        row_id = f"page-{fragments[0].page}-row-{row_index}"
        layout_cells = tuple(LayoutCell(" ".join(item.text for item in cell), fragments[0].page, row_id, min(item.x0 or 0 for item in cell), max(item.x1 or 0 for item in cell), sum(item.y0 or 0 for item in cell)/len(cell), tuple(cell), _geometry(cell)) for cell in cells)
        geometry = _geometry(fragments)
        rows.append(LayoutRow(row_id, fragments[0].page, sum(item.y0 or 0 for item in fragments)/len(fragments), layout_cells, "high" if geometry == "observed" and len(fragments) >= 2 else "medium", geometry))
    return tuple(rows)


def build_layout(text: str, fragments=(), *, warnings=()):
    positioned = tuple(item if isinstance(item, TextFragment) else TextFragment(clean_text(str(item.get("text", ""))), int(item.get("page", 1)), float(item["x"]) if item.get("x") is not None else None, float(item["y"]) if item.get("y") is not None else None, float(item.get("x1")) if item.get("x1") is not None else None, float(item.get("y1")) if item.get("y1") is not None else None, max(1., float(item.get("font_size") or 10.)), int(item.get("order", 0)), str(item.get("geometry", "estimated"))) for item in fragments if clean_text(str(item.text if isinstance(item, TextFragment) else item.get("text", ""))))
    usable = tuple(item for item in positioned if item.x0 is not None and item.y0 is not None and item.x1 is not None and item.y1 is not None)
    rows = _rows(usable)
    geometry = _geometry(usable) if len(usable) >= 3 and len({round(item.y0 or 0, 1) for item in usable}) >= 2 else "insufficient"
    linear = tuple(TextLine(value, 1, index) for index, raw in enumerate(text.splitlines()) if (value := clean_text(raw)))
    visual = tuple(TextLine(cell.text, row.page, index, cell.x0, row.y) for index, row in enumerate(rows) for cell in row.cells)
    lines = visual if geometry != "insufficient" else linear
    pages = tuple(LayoutPage(page, tuple(item for item in usable if item.page == page), tuple(row for row in rows if row.page == page)) for page in sorted({item.page for item in usable}))
    warning_values = set(warnings)
    if geometry != "observed": warning_values.add(f"geometry-{geometry}")
    return LayoutDocument(pages, usable, lines, rows, tuple(item.order for item in sorted(usable, key=lambda item: (item.page, -(item.y0 or 0), item.x0 or 0, item.order))), geometry, tuple(sorted(warning_values)))


def overlap(left: LayoutCell, right: LayoutCell):
    width = max(0., min(left.x1, right.x1) - max(left.x0, right.x0))
    return width / max(1., min(left.x1-left.x0, right.x1-right.x0))


def pair_rows(header_row: LayoutRow, value_row: LayoutRow):
    if header_row.page != value_row.page or header_row.y <= value_row.y: return ()
    pairs = []; used = set()
    for header in header_row.cells:
        ranked = sorted((abs(header.center-value.center), -overlap(header, value), index, value) for index, value in enumerate(value_row.cells))
        if not ranked or ranked[0][2] in used: return ()
        distance, negative_overlap, index, value = ranked[0]; horizontal = -negative_overlap
        relative = distance/max(25., header.x1-header.x0)
        if horizontal < .10 and relative > 1.2: return ()
        if len(ranked) > 1 and abs(ranked[1][0]-distance) < 8. and max(horizontal, -ranked[1][1]) < .3: return ()
        used.add(index)
        geometry = _geometry((header, value))
        confidence = "high" if geometry == "observed" and (horizontal >= .3 or relative <= .5) else "medium" if geometry != "insufficient" else "low"
        pairs.append(HeaderValuePair(header, value, "table_header_value", horizontal, header_row.y-value_row.y, confidence))
    return tuple(pairs)


def nearby(layout: LayoutDocument, index: int, radius: int = 2):
    return layout.lines[max(0, index-radius):min(len(layout.lines), index+radius+1)]
