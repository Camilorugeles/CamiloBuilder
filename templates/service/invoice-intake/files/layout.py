from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass


@dataclass(frozen=True)
class TextFragment:
    text: str
    page: int
    x0: float
    y0: float
    x1: float
    y1: float
    font_size: float
    order: int


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

    @property
    def center(self): return (self.x0 + self.x1) / 2


@dataclass(frozen=True)
class LayoutRow:
    row_id: str
    page: int
    y: float
    cells: tuple[LayoutCell, ...]
    confidence: str


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
class DocumentLayout:
    lines: tuple[TextLine, ...]
    rows: tuple[LayoutRow, ...]
    coordinates_reliable: bool


def clean_text(value: str) -> str:
    value = unicodedata.normalize("NFC", value).replace("\u00a0", " ")
    return re.sub(r"[ \t]+", " ", value).strip()


def _fragment(item):
    text = clean_text(str(item.get("text", "")))
    size = max(1.0, float(item.get("font_size") or 10.0))
    x0 = float(item["x"]); y0 = float(item["y"])
    return TextFragment(text, int(item.get("page", 1)), x0, y0, x0 + max(size * .35 * len(text), size), y0 + size, size, int(item.get("order", 0)))


def _rows(positioned):
    groups = []
    for fragment in sorted(positioned, key=lambda item: (item.page, -item.y0, item.x0, item.order)):
        match = next((row for row in groups if row[0].page == fragment.page and abs(row[0].y0 - fragment.y0) <= max(2.0, min(row[0].font_size, fragment.font_size) * .35)), None)
        if match is None: groups.append([fragment])
        else: match.append(fragment)
    rows = []
    for row_index, fragments in enumerate(groups):
        fragments.sort(key=lambda item: (item.x0, item.order))
        cells = []
        current = []
        for fragment in fragments:
            if current and fragment.x0 - current[-1].x1 > max(12.0, fragment.font_size * 1.5):
                cells.append(current); current = []
            current.append(fragment)
        if current: cells.append(current)
        row_id = f"page-{fragments[0].page}-row-{row_index}"
        layout_cells = tuple(LayoutCell(" ".join(item.text for item in cell), fragments[0].page, row_id, min(item.x0 for item in cell), max(item.x1 for item in cell), sum(item.y0 for item in cell) / len(cell), tuple(cell)) for cell in cells)
        rows.append(LayoutRow(row_id, fragments[0].page, sum(item.y0 for item in fragments) / len(fragments), layout_cells, "high" if len(fragments) >= 2 else "medium"))
    return tuple(rows)


def build_layout(text: str, fragments=()) -> DocumentLayout:
    positioned = []
    for item in fragments or ():
        if clean_text(str(item.get("text", ""))) and item.get("x") is not None and item.get("y") is not None:
            positioned.append(_fragment(item))
    reliable = len(positioned) >= 3 and len({round(item.y0, 1) for item in positioned}) >= 2
    lines = tuple(TextLine(value, 1, index) for index, raw in enumerate(text.splitlines()) if (value := clean_text(raw)))
    return DocumentLayout(lines, _rows(positioned) if reliable else (), reliable)


def overlap(left: LayoutCell, right: LayoutCell):
    width = max(0.0, min(left.x1, right.x1) - max(left.x0, right.x0))
    return width / max(1.0, min(left.x1 - left.x0, right.x1 - right.x0))


def pair_rows(header_row: LayoutRow, value_row: LayoutRow):
    if header_row.page != value_row.page or header_row.y <= value_row.y: return ()
    pairs = []
    used = set()
    for header in header_row.cells:
        ranked = sorted(((abs(header.center - value.center), -overlap(header, value), index, value) for index, value in enumerate(value_row.cells)), key=lambda item: item[:3])
        if not ranked or ranked[0][2] in used: return ()
        distance, negative_overlap, index, value = ranked[0]
        relative = distance / max(25.0, header.x1 - header.x0)
        horizontal = -negative_overlap
        if horizontal < .10 and relative > 1.2: return ()
        used.add(index)
        pairs.append(HeaderValuePair(header, value, "table_header_value", horizontal, header_row.y - value_row.y, "high" if horizontal >= .3 or relative <= .5 else "medium"))
    return tuple(pairs)


def nearby(layout: DocumentLayout, index: int, radius: int = 2):
    return layout.lines[max(0, index - radius):min(len(layout.lines), index + radius + 1)]
