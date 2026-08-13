from __future__ import annotations

import base64
import hashlib
import importlib
import sys
import tempfile
import unittest
from pathlib import Path

from builders.project_builder import ProjectBuilder
from builders.service_builder import ServiceBuilder
from tests.invoice_pdf_fixtures import encrypted_pdf, textual_pdf


class SafePdfAttachmentFramingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory()
        cls.project = ProjectBuilder(Path(cls.temporary.name) / "output").build("FramingFixtureOS")
        ServiceBuilder(cls.project, "agent-core").build("agent_core")
        ServiceBuilder(cls.project, "invoice-intake").build("invoice_intake")
        sys.path.insert(0, str(cls.project))
        for name in list(sys.modules):
            if name == "services" or name.startswith("services."):
                sys.modules.pop(name, None)
        cls.attachments = importlib.import_module("services.invoice_intake.attachments")
        cls.framing = importlib.import_module("services.invoice_intake.framing")
        cls.models = importlib.import_module("services.invoice_intake.models")
        cls.pdf = textual_pdf(["FACTURA", "Numero de factura: SYN-FRAME-1", "Total factura: 12,10 EUR"])

    @classmethod
    def tearDownClass(cls):
        for name in list(sys.modules):
            if name == "services" or name.startswith("services."):
                sys.modules.pop(name, None)
        sys.path.remove(str(cls.project)); cls.temporary.cleanup()

    def envelope(self, *, newline="\r\n", headers=(), body=None):
        content = self.pdf if body is None else body
        values = ["Content-Type: application/pdf", *headers]
        return newline.join(values).encode("ascii") + (newline * 2).encode("ascii") + content

    def canonical(self, payload):
        return self.framing.canonicalize_pdf_attachment(payload, "application/pdf")

    def test_pure_pdf_is_byte_for_byte_unchanged_and_fingerprinted_canonically(self):
        canonical = self.canonical(self.pdf)
        self.assertEqual(canonical.content, self.pdf)
        self.assertEqual((canonical.framing, canonical.warnings), ("none", ()))
        document = self.attachments.extract_text(self.models.DocumentInput("attachment:pure", "pure.pdf", "application/pdf", self.pdf))
        self.assertEqual(document.fingerprint, hashlib.sha256(self.pdf).hexdigest())

    def test_closed_crlf_and_lf_envelopes_are_recovered_exactly(self):
        for newline in ("\r\n", "\n"):
            with self.subTest(newline=repr(newline)):
                payload = self.envelope(newline=newline, headers=(f"Content-Length: {len(self.pdf)}", "Content-Disposition: attachment"))
                canonical = self.canonical(payload)
                self.assertEqual(canonical.content, self.pdf)
                self.assertEqual(canonical.framing, "recognized-header-envelope")
                self.assertEqual(canonical.warnings, ("attachment-framing-removed",))
                document = self.attachments.extract_text(self.models.DocumentInput(
                    "attachment:framed", "framed.pdf", "application/pdf", payload,
                ))
                self.assertEqual(document.fingerprint, hashlib.sha256(self.pdf).hexdigest())
                self.assertIn("attachment-framing-removed", document.warnings)

    def test_strict_base64_envelope_is_decoded_before_pdf_validation(self):
        encoded = base64.b64encode(self.pdf)
        payload = self.envelope(headers=(f"Content-Length: {len(encoded)}", "Content-Transfer-Encoding: base64"), body=encoded)
        self.assertEqual(self.canonical(payload).content, self.pdf)
        bad = payload[:-1] + b"!"
        with self.assertRaisesRegex(ValueError, "attachment-framing-unsafe"):
            self.canonical(bad)

    def test_unknown_duplicate_invalid_length_and_http_headers_are_rejected(self):
        payloads = (
            self.envelope(headers=("X-Unknown: value",)),
            self.envelope(headers=("Content-Type: application/pdf",)),
            self.envelope(headers=("Content-Length: 1",)),
            b"HTTP/1.1 200 OK\r\nContent-Type: application/pdf\r\n\r\n" + self.pdf,
        )
        for payload in payloads:
            with self.subTest(prefix=payload[:24]):
                with self.assertRaisesRegex(ValueError, "attachment-framing-unsafe"):
                    self.canonical(payload)

    def test_binary_html_xml_json_zip_and_multipart_prefixes_are_rejected(self):
        payloads = (
            b"\x00\x01binary\r\n\r\n" + self.pdf,
            b"<html>unsafe</html>\r\n\r\n" + self.pdf,
            b"<?xml version='1.0'?>\r\n\r\n" + self.pdf,
            b'{"kind":"wrapper"}\r\n\r\n' + self.pdf,
            b"PK\x03\x04archive containing %PDF- marker",
            b"Content-Type: multipart/mixed; boundary=x\r\n\r\n--x\r\n" + self.pdf,
        )
        for payload in payloads:
            with self.subTest(prefix=payload[:16]):
                with self.assertRaisesRegex(ValueError, "attachment-framing-unsafe"):
                    self.canonical(payload)

    def test_multiple_signatures_concatenation_missing_eof_and_truncation_fail(self):
        payloads = (
            self.pdf + self.pdf,
            self.pdf.replace(b"%%EOF", b"%PDF-1.4\n%%EOF", 1),
            self.pdf.replace(b"%%EOF", b""),
            self.pdf[:-32],
        )
        for payload in payloads:
            with self.subTest(size=len(payload)):
                with self.assertRaises(ValueError):
                    self.canonical(payload)

    def test_trailing_whitespace_is_allowed_but_significant_data_is_rejected(self):
        self.assertEqual(self.canonical(self.pdf + b" \t\r\n\f").content, self.pdf + b" \t\r\n\f")
        with self.assertRaisesRegex(ValueError, "pdf-structure-unsafe"):
            self.canonical(self.pdf + b"SIGNIFICANT")

    def test_corrupt_and_encrypted_pdfs_fail_with_sanitized_codes(self):
        corrupt = self.pdf.replace(b"startxref", b"brokenxref", 1)
        with self.assertRaisesRegex(ValueError, "pdf-structure-unsafe"):
            self.canonical(corrupt)
        with self.assertRaisesRegex(ValueError, "encrypted-pdf-unsupported"):
            self.canonical(encrypted_pdf())

    def test_declared_mime_must_match_and_content_must_be_pdf(self):
        with self.assertRaisesRegex(ValueError, "attachment-framing-unsafe"):
            self.framing.canonicalize_pdf_attachment(self.pdf, "text/html")
        with self.assertRaises(ValueError):
            self.canonical(b"Content-Type: application/pdf\r\n\r\n<html>not pdf</html>")
        with self.assertRaises(ValueError):
            self.canonical(b"Content-Type: text/html\r\n\r\n" + self.pdf)

    def test_limits_apply_before_and_after_decoding(self):
        oversized = b"%PDF-1.7\n" + b"A" * self.framing.MAX_ATTACHMENT_BYTES
        with self.assertRaisesRegex(ValueError, "attachment-size-unsafe"):
            self.canonical(oversized)
        encoded = base64.b64encode(oversized)
        payload = self.envelope(headers=("Content-Transfer-Encoding: base64",), body=encoded)
        with self.assertRaises(ValueError):
            self.canonical(payload)

    def test_failures_do_not_include_payload_data(self):
        marker = b"SYNTHETIC-SENSITIVE-MARKER"
        try:
            self.canonical(marker + b"\r\n\r\n" + self.pdf)
        except ValueError as error:
            self.assertNotIn(marker.decode(), str(error))
        else:
            self.fail("unsafe framing was accepted")


if __name__ == "__main__":
    unittest.main()
