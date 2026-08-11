from services.invoice_intake.pipeline import ShadowInvoiceIntakeBehavior


class InvoiceIntakeShadowBehavior(ShadowInvoiceIntakeBehavior):
    """Thin generated-agent boundary over the reusable invoice-intake service."""
