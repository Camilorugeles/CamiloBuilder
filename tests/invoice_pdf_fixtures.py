from __future__ import annotations

import io

from pypdf import PdfWriter
from pypdf.generic import ArrayObject, DecodedStreamObject, DictionaryObject, NameObject


def textual_pdf(lines, *, columns=False):
    """Create a genuine one-page text PDF containing only synthetic data."""
    writer = PdfWriter(); page = writer.add_blank_page(width=595, height=842)
    font = DictionaryObject({NameObject("/Type"): NameObject("/Font"), NameObject("/Subtype"): NameObject("/Type1"), NameObject("/BaseFont"): NameObject("/Helvetica")})
    font_ref = writer._add_object(font)
    page[NameObject("/Resources")] = DictionaryObject({NameObject("/Font"): DictionaryObject({NameObject("/F1"): font_ref})})
    commands = ["BT", "/F1 11 Tf", "50 790 Td"]
    for line in lines:
        escaped = str(line).replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        commands.extend([f"({escaped}) Tj", "0 -18 Td"])
    commands.append("ET")
    stream = DecodedStreamObject(); stream.set_data("\n".join(commands).encode("latin-1", errors="replace"))
    page[NameObject("/Contents")] = writer._add_object(stream)
    output = io.BytesIO(); writer.write(output); return output.getvalue()


def positioned_pdf(rows):
    """Create a genuine PDF from synthetic rows of (x, text) cells."""
    writer = PdfWriter(); page = writer.add_blank_page(width=595, height=842)
    font = DictionaryObject({NameObject("/Type"): NameObject("/Font"), NameObject("/Subtype"): NameObject("/Type1"), NameObject("/BaseFont"): NameObject("/Helvetica")})
    font_ref = writer._add_object(font)
    page[NameObject("/Resources")] = DictionaryObject({NameObject("/Font"): DictionaryObject({NameObject("/F1"): font_ref})})
    streams = ArrayObject()
    y = 790
    for row in rows:
        for cell_index, (x, text) in enumerate(row):
            escaped = str(text).replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
            stream = DecodedStreamObject()
            cell_y = y - (cell_index * .4)
            stream.set_data("\n".join(["BT", "/F1 10 Tf", f"1 0 0 1 {x} {cell_y} Tm", f"({escaped}) Tj", "ET"]).encode("latin-1", errors="replace"))
            streams.append(writer._add_object(stream))
        y -= 24
    page[NameObject("/Contents")] = streams
    output = io.BytesIO(); writer.write(output); return output.getvalue()


def operation_pdf(commands):
    """Create a synthetic PDF from explicit, caller-controlled text operations."""
    writer = PdfWriter(); page = writer.add_blank_page(width=595, height=842)
    font = DictionaryObject({NameObject("/Type"): NameObject("/Font"), NameObject("/Subtype"): NameObject("/Type1"), NameObject("/BaseFont"): NameObject("/Helvetica")})
    font_ref = writer._add_object(font)
    page[NameObject("/Resources")] = DictionaryObject({NameObject("/Font"): DictionaryObject({NameObject("/F1"): font_ref})})
    stream = DecodedStreamObject(); stream.set_data("\n".join(commands).encode("latin-1", errors="replace"))
    page[NameObject("/Contents")] = writer._add_object(stream)
    output = io.BytesIO(); writer.write(output); return output.getvalue()


def visual_order_pdf(cells):
    """Write cells in stream order while coordinates define a different visual order."""
    commands = ["BT", "/F1 10 Tf"]
    for x, y, text in cells:
        escaped = str(text).replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        commands.extend([f"1 0 0 1 {x} {y} Tm", f"({escaped}) Tj"])
    commands.append("ET")
    return operation_pdf(commands)


def blank_text_pdf():
    writer = PdfWriter(); writer.add_blank_page(width=595, height=842)
    output = io.BytesIO(); writer.write(output); return output.getvalue()
