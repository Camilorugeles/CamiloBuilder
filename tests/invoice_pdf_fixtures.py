from __future__ import annotations

import io

from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject


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


def blank_text_pdf():
    writer = PdfWriter(); writer.add_blank_page(width=595, height=842)
    output = io.BytesIO(); writer.write(output); return output.getvalue()
