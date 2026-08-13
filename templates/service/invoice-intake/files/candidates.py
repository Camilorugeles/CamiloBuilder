from __future__ import annotations

from dataclasses import dataclass, replace


RELATIONS = frozenset({
    "same_line_right", "next_line", "aligned_column", "same_block",
    "table_row", "syntax_only", "arithmetic_support", "table_header_value",
    "aligned_below_header", "aligned_above_label", "paired_column",
})


@dataclass(frozen=True)
class EvidenceLink:
    observation_id: str
    page: int
    row_id: str | None
    header: str | None
    value: str
    relation: str
    horizontal_overlap: float | None = None
    vertical_distance: float | None = None
    geometry: str = "insufficient"
    block_id: str | None = None
    table_id: str | None = None
    positive_signals: tuple[str, ...] = ()
    negative_signals: tuple[str, ...] = ()
    veto: bool = False

    def __post_init__(self):
        if self.relation not in RELATIONS:
            raise ValueError(f"Unknown evidence relation: {self.relation}")


@dataclass(frozen=True)
class FieldCandidate:
    field: str
    value: str
    source_ref: str
    page: int
    rule_id: str
    label: str | None
    evidence_text: str
    relation: str
    distance: float | None
    score: int
    alternatives: tuple[str, ...] = ()
    evidence: EvidenceLink | None = None

    def __post_init__(self):
        if self.relation not in RELATIONS:
            raise ValueError(f"Unknown candidate relation: {self.relation}")

    def strengthened(self, points: int, *, relation: str | None = None):
        return replace(self, score=self.score + points, relation=relation or self.relation)
