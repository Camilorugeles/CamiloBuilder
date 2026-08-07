CONTROLS = (
    ("control.architecture.contracts", "Architecture contract references", "error", "principle.traceability"),
    ("control.architecture.dependencies", "Allowed and prohibited dependencies", "critical", "principle.least-privilege"),
    ("control.architecture.modules", "Registered architecture modules", "error", "principle.living-architecture"),
    ("control.architecture.no-derived-inventories", "Absence of derived inventories", "error", "principle.no-drift"),
    ("control.architecture.registry-schema", "Architecture registry schema", "critical", "principle.living-architecture"),
    ("control.architecture.runtime-coherence", "Runtime dependency coherence", "error", "principle.living-architecture"),
    ("control.constitution.version", "Constitution version coherence", "critical", "principle.traceability"),
    ("control.exceptions.integrity", "Exception registry integrity", "critical", "principle.incremental-evolution"),
    ("control.exceptions.temporal-validity", "Exception temporal validity", "error", "principle.failure-safe"),
    ("control.introspection.coherence", "Capability introspection coherence", "error", "principle.self-knowledge"),
    ("control.references.integrity", "Governed reference integrity", "error", "principle.traceability"),
    ("control.schemas.references", "Local schema references", "critical", "principle.failure-safe"),
    ("control.schemas.selection", "Explicit schema selection", "error", "principle.determinism"),
    ("control.schemas.validation", "Governed document schema validation", "critical", "principle.living-architecture"),
    ("control.work-orders.integrity", "Work Order registry integrity", "error", "principle.incremental-evolution"),
)


CONTROL_BY_ID = {
    control_id: {
        "id": control_id,
        "title": title,
        "severity": severity,
        "constitutional_provision": provision,
    }
    for control_id, title, severity, provision in CONTROLS
}
