from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass


@dataclass(frozen=True)
class TextFragment:
    text: str
    page: int
    x: float | None
    y: float | None
    order: int


@dataclass(frozen=True)
class TextLine:
    text: str
    page: int
    order: int
    x: float | None = None
    y: float | None = None


@dataclass(frozen=True)
class DocumentLayout:
    lines: tuple[TextLine, ...]
    coordinates_reliable: bool


def clean_text(value: str) -> str:
    value = unicodedata.normalize("NFC", value).replace("\u00a0", " ")
    return re.sub(r"[ \t]+", " ", value).strip()


def build_layout(text: str, fragments=()) -> DocumentLayout:
    positioned = []
    for item in fragments or ():
        value = clean_text(str(item.get("text", "")))
        if value and item.get("x") is not None and item.get("y") is not None:
            positioned.append(item)
    reliable = len(positioned) >= 3
    # pypdf extraction order is the safe baseline. Coordinates are retained as
    # evidence but never used to reorder contradictory content.
    lines = []
    for index, raw in enumerate(text.splitlines()):
        value = clean_text(raw)
        if value:
            lines.append(TextLine(value, 1, index))
    return DocumentLayout(tuple(lines), reliable)


def nearby(layout: DocumentLayout, index: int, radius: int = 2):
    start = max(0, index - radius); end = min(len(layout.lines), index + radius + 1)
    return layout.lines[start:end]
