import datetime
import hashlib
import json
import unittest
from pathlib import Path

try:
    from jsonschema import Draft202012Validator, FormatChecker
    from referencing import Registry
except ModuleNotFoundError as error:
    raise RuntimeError(
        "Missing development dependency; run: "
        "python3 -m pip install -r requirements-dev.txt"
    ) from error


ROOT = Path(__file__).resolve().parents[1]
V1_SCHEMA_PATH = ROOT / "governance" / "schemas" / "v1" / "exception.schema.json"
V2_SCHEMA_PATH = ROOT / "governance" / "schemas" / "v2" / "exception.schema.json"
V1_FIXTURE_PATH = ROOT / "tests" / "fixtures" / "governance" / "v1" / "valid" / "exception.json"
V2_FIXTURE_ROOT = ROOT / "tests" / "fixtures" / "governance" / "v2"
INDEX_PATH = ROOT / "governance" / "exceptions" / "index.json"
ARCHITECTURE_PATH = ROOT / "governance" / "architecture" / "registry.json"
WORK_ORDER_INDEX_PATH = ROOT / "governance" / "work-orders" / "index.json"
WORK_ORDER_PATH = ROOT / "governance" / "work-orders" / "WORK-009.json"
V1_SCHEMA_SHA256 = "d554fe81c766b744df79c40c185af6c4685faac8fa7927edf7639ff5240e80c8"
EXPLICIT_VALIDATION_INSTANT = datetime.datetime.fromisoformat("2026-01-10T10:00:00+00:00")
VALID_TRANSITIONS = {
    ("proposed", "active"),
    ("proposed", "expired"),
    ("proposed", "revoked"),
    ("active", "expired"),
    ("active", "closed"),
    ("active", "revoked"),
    ("expired", "closed"),
}
TERMINAL_STATES = {"closed", "revoked"}
ORDERED_ARRAY_FIELDS = (
    "affected_component_ids",
    "affected_contract_ids",
    "affected_capability_ids",
    "approval_ids",
    "compensating_controls",
    "risks",
)


def load_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def reject_remote_retrieval(uri):
    raise AssertionError(f"Schema validation attempted network retrieval: {uri}")


def make_validator(schema):
    return Draft202012Validator(
        schema,
        format_checker=FormatChecker(),
        registry=Registry(retrieve=reject_remote_retrieval),
    )


def stable_schema_errors(validator, instance):
    return sorted(
        validator.iter_errors(instance),
        key=lambda error: (
            tuple(str(part) for part in error.absolute_path),
            error.validator,
            error.message,
        ),
    )


def select_exception_schema(document):
    paths = {1: V1_SCHEMA_PATH, 2: V2_SCHEMA_PATH}
    version = document.get("schema_version")
    if version not in paths:
        raise ValueError(f"Unsupported exception schema_version: {version!r}")
    return load_json(paths[version])


def tree_digest(paths):
    digest = hashlib.sha256()
    files = []
    for path in paths:
        files.extend(item for item in path.rglob("*") if item.is_file())
    for path in sorted(files):
        digest.update(path.relative_to(ROOT).as_posix().encode("utf-8"))
        digest.update(path.read_bytes())
    return digest.hexdigest()


def semantic_issues(document, validation_instant):
    issues = []
    starts_at = datetime.datetime.fromisoformat(document["starts_at"])
    expires_at = datetime.datetime.fromisoformat(document["expires_at"])
    if starts_at >= expires_at:
        issues.append(("invalid-date-order", "expires_at"))
    if document["status"] == "active" and validation_instant >= expires_at:
        issues.append(("active-expired", "status"))

    history = document["status_history"]
    if not history and document["status"] != "proposed":
        issues.append(("missing-history", "status_history"))
    for index, transition in enumerate(history):
        pair = transition["from"], transition["to"]
        if pair not in VALID_TRANSITIONS:
            issues.append(("invalid-transition", str(index)))
        if transition["from"] in TERMINAL_STATES:
            issues.append(("terminal-transition", str(index)))
        if index and history[index - 1]["to"] != transition["from"]:
            issues.append(("discontinuous-history", str(index)))
    if history and history[-1]["to"] != document["status"]:
        issues.append(("status-mismatch", "status"))
    transition_dates = [datetime.datetime.fromisoformat(item["at"]) for item in history]
    if transition_dates != sorted(transition_dates):
        issues.append(("non-chronological-history", "status_history"))
    if transition_dates and transition_dates[0] < starts_at:
        issues.append(("transition-before-start", "status_history"))

    for field in ORDERED_ARRAY_FIELDS:
        values = document[field]
        if values != sorted(set(values)):
            issues.append(("unsorted-array", field))
    if "closure" in document:
        approvals = document["closure"]["approval_ids"]
        if approvals != sorted(set(approvals)):
            issues.append(("unsorted-array", "closure.approval_ids"))

    known_contracts = set(load_json(ARCHITECTURE_PATH)["contract_ids"])
    for contract_id in sorted(set(document["affected_contract_ids"]) - known_contracts):
        issues.append(("unknown-contract", contract_id))
    known_work_orders = {entry["id"] for entry in load_json(WORK_ORDER_INDEX_PATH)}
    if document["remediation_work_order_id"] not in known_work_orders:
        issues.append(("unknown-work-order", document["remediation_work_order_id"]))
    if document["affected_capability_ids"]:
        issues.append(("capability-registry-unavailable", "affected_capability_ids"))
    return sorted(issues)


class ExceptionRegistryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.v1_schema = load_json(V1_SCHEMA_PATH)
        cls.v2_schema = load_json(V2_SCHEMA_PATH)
        cls.active = load_json(V2_FIXTURE_ROOT / "valid" / "exception-active.json")
        cls.closed = load_json(V2_FIXTURE_ROOT / "valid" / "exception-closed.json")

    def test_v1_schema_is_byte_for_byte_unchanged_and_fixture_still_validates(self):
        self.assertEqual(hashlib.sha256(V1_SCHEMA_PATH.read_bytes()).hexdigest(), V1_SCHEMA_SHA256)
        fixture = load_json(V1_FIXTURE_PATH)
        self.assertEqual(stable_schema_errors(make_validator(self.v1_schema), fixture), [])

    def test_schema_selection_is_explicit_for_v1_and_v2(self):
        self.assertEqual(select_exception_schema(load_json(V1_FIXTURE_PATH))["properties"]["schema_version"], {"const": 1})
        self.assertEqual(select_exception_schema(self.active)["properties"]["schema_version"], {"const": 2})
        with self.assertRaisesRegex(ValueError, "Unsupported exception schema_version"):
            select_exception_schema({"schema_version": 3})

    def test_v2_schema_is_local_closed_and_draft_2020_12(self):
        self.assertEqual(self.v2_schema["$schema"], "https://json-schema.org/draft/2020-12/schema")
        self.assertEqual(self.v2_schema["properties"]["schema_version"], {"const": 2})
        Draft202012Validator.check_schema(self.v2_schema)
        nodes = list(self._nodes(self.v2_schema))
        object_nodes = [node for node in nodes if isinstance(node, dict) and node.get("type") == "object"]
        self.assertTrue(all(node.get("additionalProperties") is False for node in object_nodes))
        refs = [node["$ref"] for node in nodes if isinstance(node, dict) and "$ref" in node]
        self.assertTrue(refs)
        self.assertTrue(all(ref.startswith("#/$defs/") for ref in refs))

    def test_official_index_is_exactly_empty_and_no_real_exceptions_exist(self):
        self.assertEqual(INDEX_PATH.read_bytes(), b"[]\n")
        self.assertEqual(load_json(INDEX_PATH), [])
        exception_files = sorted((ROOT / "governance" / "exceptions").glob("EXCEPTION-*.json"))
        self.assertEqual(exception_files, [])

    def test_valid_fixtures_validate_deterministically_without_network_or_writes(self):
        guarded = [ROOT / "governance", V2_FIXTURE_ROOT]
        before = tree_digest(guarded)
        for fixture in (self.active, self.closed):
            first = stable_schema_errors(make_validator(self.v2_schema), fixture)
            second = stable_schema_errors(make_validator(self.v2_schema), fixture)
            self.assertEqual(first, [])
            self.assertEqual(first, second)
            self.assertEqual(semantic_issues(fixture, EXPLICIT_VALIDATION_INSTANT), [])
        self.assertEqual(before, tree_digest(guarded))

    def test_active_exception_is_temporary_non_precedential_and_not_expired(self):
        self.assertFalse(self.active["creates_precedent"])
        self.assertEqual(self.active["conformance_status"], "temporarily_authorized")
        self.assertEqual(self.active["affected_capability_ids"], [])
        expires_at = datetime.datetime.fromisoformat(self.active["expires_at"])
        self.assertLess(EXPLICIT_VALIDATION_INSTANT, expires_at)
        expired_instant = datetime.datetime.fromisoformat("2026-01-16T10:00:00+00:00")
        self.assertIn(("active-expired", "status"), semantic_issues(self.active, expired_instant))

    def test_status_transitions_are_complete_and_terminal_states_have_no_exit(self):
        expected = {
            ("proposed", "active"), ("proposed", "expired"), ("proposed", "revoked"),
            ("active", "expired"), ("active", "closed"), ("active", "revoked"),
            ("expired", "closed"),
        }
        self.assertEqual(VALID_TRANSITIONS, expected)
        self.assertFalse(any(source in TERMINAL_STATES for source, _ in VALID_TRANSITIONS))
        self.assertNotIn(("expired", "active"), VALID_TRANSITIONS)

    def test_critical_policy_is_structural_and_requires_two_approvals(self):
        self.assertEqual(self.active["approval_policy"], "critical")
        self.assertGreaterEqual(len(self.active["approval_ids"]), 2)
        schema_errors = stable_schema_errors(make_validator(self.v2_schema), {**self.active, "approval_ids": ["approval.only-one"]})
        self.assertTrue(any(error.validator == "minItems" for error in schema_errors))

    def test_references_are_ids_and_resolve_to_current_governed_indexes(self):
        self.assertEqual(semantic_issues(self.active, EXPLICIT_VALIDATION_INSTANT), [])
        self.assertEqual(self.active["remediation_work_order_id"], "WORK-009")
        self.assertEqual(self.active["affected_contract_ids"], ["contract.governance-schema"])

    def test_work_order_traceability_adds_only_the_previously_published_commit(self):
        work_order = load_json(WORK_ORDER_PATH)
        self.assertEqual(work_order["status"], "published")
        self.assertEqual(
            work_order["implementation_commit_ids"],
            [
                "ac2f00def074e5bee7c50753e9bc9af82b655bd2",
                "c7031e5d858ab7130981287e017784727415a12a",
                "90cf95cb6062a4d7213c60380c23f15163fdc43c",
                "078c719a959e1f1a56f6289dde336850f68af237",
                "8ad36b81a95787cc25468387bbbce695e79bcbed",
                "38636518f5638a8c06da9d3366f551cc1cb90f5a",
                "82f9d9985c97ca514fea20e907005525e27f306f",
                "b586e24e680ca4a081b512f48858a247fe77ed2c",
                "a1e6e842cfdf653452c72a0de9ec7f14aa8aecdc",
            ],
        )
        self.assertEqual(
            work_order["registry_closure_commit_id"],
            "759360f02622905cba971695472ef10de4a24aa6",
        )

    def test_each_invalid_fixture_fails_for_one_specific_reason(self):
        schema_cases = {
            "exception-active-missing-approvals": "minItems",
            "exception-active-missing-controls": "minItems",
            "exception-active-missing-expiration": "required",
            "exception-active-missing-remediation": "required",
            "exception-active-missing-reversal": "required",
            "exception-active-missing-risks": "minItems",
            "exception-active-missing-closure-criteria": "minLength",
            "exception-closed-missing-closure": "required",
            "exception-revoked-missing-closure": "required",
            "exception-expired-conforming": "const",
            "exception-invalid-transition": "oneOf",
            "exception-creates-precedent": "const",
            "exception-unknown-property": "additionalProperties",
        }
        semantic_cases = {
            "exception-invalid-date-order": "invalid-date-order",
            "exception-unknown-contract": "unknown-contract",
        }
        invalid_dir = V2_FIXTURE_ROOT / "invalid"
        files = sorted(path for path in invalid_dir.glob("exception-*.json"))
        self.assertEqual([path.stem for path in files], sorted(schema_cases | semantic_cases))
        validator = make_validator(self.v2_schema)
        for path in files:
            fixture = load_json(path)
            schema_errors = stable_schema_errors(validator, fixture)
            with self.subTest(fixture=path.stem):
                if path.stem in schema_cases:
                    self.assertTrue(schema_errors)
                    self.assertTrue(all(error.validator == schema_cases[path.stem] for error in schema_errors))
                else:
                    self.assertEqual(schema_errors, [])
                    validation_instant = EXPLICIT_VALIDATION_INSTANT
                    if path.stem == "exception-invalid-date-order":
                        validation_instant = datetime.datetime.fromisoformat(
                            "2025-12-31T10:00:00+00:00"
                        )
                    issues = semantic_issues(fixture, validation_instant)
                    self.assertEqual(len(issues), 1)
                    self.assertEqual(issues[0][0], semantic_cases[path.stem])

    @staticmethod
    def _nodes(value):
        yield value
        if isinstance(value, dict):
            for child in value.values():
                yield from ExceptionRegistryTests._nodes(child)
        elif isinstance(value, list):
            for child in value:
                yield from ExceptionRegistryTests._nodes(child)


if __name__ == "__main__":
    unittest.main()
