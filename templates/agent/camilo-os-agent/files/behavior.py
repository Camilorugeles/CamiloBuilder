from services.agent_core.models import AgentAnalysis


class InvoiceIntakeBehavior:
    """Synthetic pilot behavior; it never writes or accesses the network."""

    def analyze(self, *, input_reference, connector):
        item = connector.read(input_reference)
        if item.get("technical_failure"):
            raise RuntimeError("Synthetic connector processing failure")
        if item.get("ambiguous"):
            return AgentAnalysis(
                evidence_refs=(input_reference.reference,),
                escalation={
                    "code": "ambiguous-classification",
                    "reason": "Synthetic input requires human classification",
                },
            )
        fields = dict(item.get("invoice_fields", {}))
        return AgentAnalysis(
            results=(
                {
                    "confidence": "high",
                    "kind": "classification",
                    "result_id": "result.classification",
                    "value": "invoice",
                },
                {
                    "kind": "structured-fields",
                    "result_id": "result.invoice-fields",
                    "value": fields,
                },
            ),
            proposed_actions=(
                {
                    "action_id": "action.propose-drive-destination",
                    "parameters": {"destination_ref": "destination.synthetic-finance"},
                },
            ),
            evidence_refs=tuple(sorted({
                input_reference.reference,
                str(item.get("attachment_ref", "fixture:invoice-attachment-001")),
            })),
        )
