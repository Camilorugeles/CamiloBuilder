CONTROLS = (
    ("control.architecture.contracts", "Architecture contract references", "error", "principle.traceability"),
    ("control.architecture.dependencies", "Allowed and prohibited dependencies", "critical", "principle.safe-failure-minimum-access"),
    ("control.architecture.modules", "Registered architecture modules", "error", "principle.traceability"),
    ("control.architecture.no-derived-inventories", "Absence of derived inventories", "error", "principle.no-drift-self-knowledge"),
    ("control.architecture.registry-schema", "Architecture registry schema", "critical", "principle.traceability"),
    ("control.architecture.runtime-coherence", "Limited static import dependency coherence", "error", "principle.traceability"),
    ("control.constitution.version", "Canonical Constitution version source", "critical", "principle.traceability"),
    ("control.governance.manual-assertion-sources", "Maintainer declaration source availability", "error", "principle.traceability"),
    ("control.introspection.coherence", "Capability introspection coherence", "error", "principle.no-drift-self-knowledge"),
    ("control.references.integrity", "Governed reference integrity", "error", "principle.traceability"),
    ("control.schemas.references", "Local schema references", "critical", "principle.safe-failure-minimum-access"),
    ("control.schemas.selection", "Explicit schema selection", "error", "principle.determinism"),
    ("control.schemas.validation", "Machine-consumed governed document schema validation", "critical", "principle.safe-failure-minimum-access"),
    ("control.work-orders.integrity", "Active and legacy Work Order integrity", "error", "principle.incremental-evolution"),
)


MANUAL_ASSERTIONS = (
    (
        "assertion.architectural-responsibility-declared",
        "Principal architectural responsibility is declared",
        "governance/MAINTAINERS.md",
        "Responsabilidad arquitectónica principal:** Camilo Rugeles",
    ),
    (
        "assertion.independent-review-status-declared",
        "Permanent independent review availability is declared",
        "governance/MAINTAINERS.md",
        "Revisor independiente permanente:** no existe actualmente",
    ),
    (
        "assertion.maintainer-current-declared",
        "Current Maintainer is declared",
        "governance/MAINTAINERS.md",
        "Maintainer:** Camilo Rugeles",
    ),
    (
        "assertion.material-authority-declared",
        "Material maintenance authority is declared",
        "governance/MAINTAINERS.md",
        "declara que ejerce actualmente la autoridad material",
    ),
)


UNVERIFIED_OBLIGATIONS = (
    (
        "obligation.architectural-simplicity-judgment",
        "Architectural mechanisms remain proportionate to the problem",
        "governance/CONSTITUTION.md#59-simplicidad-arquitectónica",
        "Architectural proportionality requires human judgment.",
    ),
    (
        "obligation.change-proportionality",
        "Evidence and governance ceremony remain proportionate to risk",
        "governance/CONSTITUTION.md#57-evolución-incremental",
        "Risk and process proportionality cannot be established mechanically.",
    ),
    (
        "obligation.contract-compatibility-judgment",
        "Contract compatibility classifications are conceptually adequate",
        "governance/CONSTITUTION.md#54-compatibilidad-explícita",
        "Tests provide evidence but do not prove a human compatibility classification.",
    ),
    (
        "obligation.non-destruction-completeness",
        "All destructive behavior is excluded or explicitly governed",
        "governance/CONSTITUTION.md#51-no-destrucción",
        "Known tests cannot exhaust every possible destructive operation.",
    ),
    (
        "obligation.reversal-adequacy",
        "Reversal strategies are operationally adequate",
        "governance/CONSTITUTION.md#56-reversibilidad",
        "The practical adequacy of a reversal requires contextual judgment.",
    ),
    (
        "obligation.safe-failure-completeness",
        "All ambiguous and corrupt states fail safely",
        "governance/CONSTITUTION.md#52-fallo-seguro-y-acceso-mínimo",
        "Automated controls cannot enumerate every ambiguous or corrupt state.",
    ),
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
