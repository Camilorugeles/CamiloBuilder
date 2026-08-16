from __future__ import annotations

import json
import re
import stat
from collections import Counter
from datetime import date
from pathlib import Path


MAX_GROUND_TRUTH_BYTES = 64 * 1024
CASE_ID = re.compile(r"^[A-Z][A-Z0-9-]{2,63}$")
VALIDATOR_REF = re.compile(r"^reviewer:[a-z0-9][a-z0-9_-]{1,63}$")
FIELD_NAMES = frozenset({
    "document_type", "supplier", "supplier_tax_id", "invoice_number",
    "issue_date", "recipient", "recipient_tax_id", "taxable_base", "vat",
    "other_taxes", "withholdings", "total", "currency", "concept",
})
FIELD_STATUSES = frozenset({"extracted", "derived", "unknown", "conflict"})


class GroundTruthError(ValueError):
    """A sanitized failure while loading or evaluating human ground truth."""


def _inside(path, root):
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def load_ground_truth(path, *, repository_root):
    """Load a human-validated ground truth file kept outside the repository."""
    path = Path(path)
    root = Path(repository_root).resolve()
    try:
        resolved = path.resolve(strict=True)
        metadata = path.lstat()
    except OSError:
        raise GroundTruthError("ground-truth-unsafe") from None
    if (
        stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode)
        or stat.S_IMODE(metadata.st_mode) != 0o600 or _inside(resolved, root)
        or metadata.st_size > MAX_GROUND_TRUTH_BYTES
    ):
        raise GroundTruthError("ground-truth-unsafe")
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        raise GroundTruthError("ground-truth-invalid") from None
    if not isinstance(document, dict) or set(document) != {
        "format", "format_version", "revision", "validated_by_ref",
        "validated_on", "cases",
    }:
        raise GroundTruthError("ground-truth-invalid")
    if (
        document["format"] != "camilo-os.invoice-ground-truth"
        or document["format_version"] != 1
        or not isinstance(document["revision"], int)
        or isinstance(document["revision"], bool) or document["revision"] < 1
        or not isinstance(document["validated_by_ref"], str)
        or not VALIDATOR_REF.fullmatch(document["validated_by_ref"])
        or not isinstance(document["validated_on"], str)
    ):
        raise GroundTruthError("ground-truth-invalid")
    try:
        date.fromisoformat(document["validated_on"])
    except ValueError:
        raise GroundTruthError("ground-truth-invalid") from None
    cases = document["cases"]
    if not isinstance(cases, list) or not 1 <= len(cases) <= 15:
        raise GroundTruthError("ground-truth-invalid")
    normalized = []
    for case in cases:
        if not isinstance(case, dict) or set(case) != {"case_id", "fields"}:
            raise GroundTruthError("ground-truth-invalid")
        if not isinstance(case["case_id"], str) or not CASE_ID.fullmatch(case["case_id"]):
            raise GroundTruthError("ground-truth-invalid")
        fields = case["fields"]
        if not isinstance(fields, dict) or not fields or not set(fields) <= FIELD_NAMES:
            raise GroundTruthError("ground-truth-invalid")
        for value in fields.values():
            if (
                not isinstance(value, dict) or set(value) != {"evaluable", "value"}
                or not isinstance(value["evaluable"], bool)
                or (value["evaluable"] and (
                    not isinstance(value["value"], str) or not value["value"]
                ))
                or (not value["evaluable"] and value["value"] is not None)
            ):
                raise GroundTruthError("ground-truth-invalid")
        normalized.append({"case_id": case["case_id"], "fields": fields})
    identifiers = [case["case_id"] for case in normalized]
    if identifiers != sorted(set(identifiers)):
        raise GroundTruthError("ground-truth-order-invalid")
    return {**document, "cases": normalized}


def evaluate_ground_truth(*, ground_truth, analyses):
    """Return only aggregate MATCH/MISMATCH/UNKNOWN/CONFLICT counters."""
    if not isinstance(ground_truth, dict) or not isinstance(analyses, dict):
        raise GroundTruthError("ground-truth-evaluation-invalid")
    cases = ground_truth.get("cases")
    if not isinstance(cases, list):
        raise GroundTruthError("ground-truth-evaluation-invalid")
    expected_ids = {case.get("case_id") for case in cases if isinstance(case, dict)}
    if set(analyses) != expected_ids:
        raise GroundTruthError("ground-truth-case-set-mismatch")
    per_case = []
    total = Counter()
    for case in cases:
        analysis = analyses[case["case_id"]]
        fields = analysis.get("fields") if isinstance(analysis, dict) else None
        if not isinstance(fields, dict):
            raise GroundTruthError("ground-truth-evaluation-invalid")
        counts = Counter()
        for name, expected in case["fields"].items():
            if not expected["evaluable"]:
                continue
            observed = fields.get(name)
            if (
                not isinstance(observed, dict) or observed.get("status") not in FIELD_STATUSES
                or set(observed) < {"value", "status"}
            ):
                raise GroundTruthError("ground-truth-evaluation-invalid")
            status = observed["status"]
            if status in {"extracted", "derived"}:
                outcome = "MATCH" if observed["value"] == expected["value"] else "MISMATCH"
            else:
                outcome = status.upper()
            counts[outcome] += 1
        total.update(counts)
        per_case.append({"case_id": case["case_id"], **_metrics(counts)})
    return {
        "format": "camilo-os.invoice-evaluation", "format_version": 1,
        "ground_truth_revision": ground_truth.get("revision"),
        "cases": per_case, "total": _metrics(total),
    }


def _metrics(counts):
    match = counts["MATCH"]
    mismatch = counts["MISMATCH"]
    unknown = counts["UNKNOWN"]
    conflict = counts["CONFLICT"]
    evaluable = match + mismatch + unknown + conflict
    resolved = match + mismatch
    return {
        "evaluable": evaluable, "match": match, "mismatch": mismatch,
        "unknown": unknown, "conflict": conflict,
        "coverage": resolved / evaluable if evaluable else None,
        "resolved_precision": match / resolved if resolved else None,
        "safe_abstention": (unknown + conflict) / evaluable if evaluable else None,
    }
