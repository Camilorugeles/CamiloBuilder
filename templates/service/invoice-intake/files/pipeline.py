from __future__ import annotations

from services.agent_core.models import AgentAnalysis
from services.agent_core.models import InputReference

from .attachments import extract_text
from .classification import classify
from .duplicates import duplicate_fingerprint
from .extraction import extract_fields, reconcile
from .models import DocumentInput
from .review import build_review_card
from .validation import validate_invoice_analysis


def validate_closed_batch(*, configuration, connector, source_id="source.gmail-company-invoices"):
    """Validate the frozen batch without changing message state."""
    counts = {}
    for reference in configuration["selection"]["pilot_message_refs"]:
        message = connector.read(InputReference(source_id, reference))
        metadata = message.get("metadata", {})
        supplier_hint = str(metadata.get("from") or reference).strip().lower()
        counts[supplier_hint] = counts.get(supplier_hint, 0) + 1
        if counts[supplier_hint] > configuration["selection"]["max_per_supplier"]:
            raise ValueError("Closed batch exceeds the per-supplier limit")
    return tuple(configuration["selection"]["pilot_message_refs"])


class ShadowInvoiceIntakeBehavior:
    def __init__(self, *, configuration, duplicate_lookup):
        if configuration.get("mode") != "shadow": raise ValueError("Only shadow mode is supported")
        self.configuration = configuration; self.duplicate_lookup = duplicate_lookup

    def analyze(self, *, input_reference, connector):
        if input_reference.reference not in self.configuration["selection"]["pilot_message_refs"]:
            raise ValueError("Message reference is outside the closed pilot batch")
        validate_closed_batch(configuration=self.configuration, connector=connector, source_id=input_reference.source_id)
        message = connector.read(input_reference)
        documents = []
        failures = []
        filenames = message.get("attachment_filenames", {})
        for reference in sorted(message.get("content_refs", ())):
            try:
                content = connector.read_content(reference)
                documents.append(extract_text(DocumentInput(reference, str(filenames.get(reference, "attachment")), content.media_type, content.content)))
            except (ValueError, KeyError) as error:
                failures.append(f"attachment-unreadable:{reference}")
        extractions = [extract_fields(item) for item in documents]
        if extractions: fields, conflicts = reconcile(extractions)
        else:
            from .extraction import ALIASES, _field
            fields = {name: _field(None, "none", "unknown") for name in ALIASES}; conflicts = ()
        fingerprint = duplicate_fingerprint(fields, [item.fingerprint for item in documents])
        duplicate_refs = self.duplicate_lookup.find(fingerprint)
        classification = classify(fields=fields, config=self.configuration, conflicts=conflicts, duplicate_refs=duplicate_refs, unreadable=bool(failures or not documents))
        analysis = {
            "format": "camilo-os.invoice-analysis", "format_version": 1,
            "activity": classification["activity"], "arithmetic_consistency": classification["arithmetic_consistency"],
            "attachment_refs": sorted(item.reference for item in documents),
            "attachments": [{"filename": item.filename, "fingerprint": "sha256:" + item.fingerprint, "media_type": item.media_type, "reference": item.reference} for item in sorted(documents, key=lambda value: value.reference)],
            "content_fingerprints": sorted("sha256:" + item.fingerprint for item in documents),
            "destination_status": classification["destination_status"], "document_status": classification["document_status"],
            "duplicate_refs": classification["duplicate_refs"], "fields": fields,
            "gmail_message_ref": input_reference.reference, "global_confidence": classification["global_confidence"],
            "legal_entity": classification["legal_entity"], "proposed_destination_ref": classification["proposed_destination_ref"],
            "review_required": classification["review_required"], "review_reasons": classification["review_reasons"],
            "unknown_fields": classification["unknown_fields"], "warnings": sorted(set(classification["warnings"] + failures)),
        }
        analysis = validate_invoice_analysis(analysis)
        review = build_review_card(analysis)
        run_ref = "analysis:" + input_reference.reference
        self.duplicate_lookup.register(fingerprint, run_ref)
        results = (
            {"confidence": analysis["global_confidence"], "kind": "invoice-analysis.v1", "result_id": "result.invoice-analysis", "value": analysis},
            {"confidence": analysis["global_confidence"], "kind": "invoice-review-card.v1", "result_id": "result.review-card", "value": review},
        )
        escalation = None
        if analysis["review_required"]:
            escalation = {"code": "invoice-review-required", "reason": "; ".join(analysis["review_reasons"] or ["Document requires review"])}
        return AgentAnalysis(results=results, proposed_actions=(), evidence_refs=tuple(sorted([input_reference.reference] + analysis["attachment_refs"] + analysis["content_fingerprints"])), escalation=escalation)
