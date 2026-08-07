import datetime
import hashlib
import json
import subprocess
import unittest
from pathlib import Path, PurePosixPath

try:
    from jsonschema import Draft202012Validator, FormatChecker
    from referencing import Registry
except ModuleNotFoundError as error:
    raise RuntimeError(
        "Missing development dependency; run: "
        "python3 -m pip install -r requirements-dev.txt"
    ) from error


ROOT = Path(__file__).resolve().parents[1]
V1_SCHEMA_PATH = ROOT / "governance" / "schemas" / "v1" / "work-order.schema.json"
V2_SCHEMA_PATH = ROOT / "governance" / "schemas" / "v2" / "work-order.schema.json"
V1_FIXTURE_PATH = ROOT / "tests" / "fixtures" / "governance" / "v1" / "valid" / "work-order.json"
V2_FIXTURE_ROOT = ROOT / "tests" / "fixtures" / "governance" / "v2"
INDEX_PATH = ROOT / "governance" / "work-orders" / "index.json"
WORK_ORDER_PATH = ROOT / "governance" / "work-orders" / "WORK-009.json"
ARCHITECTURE_PATH = ROOT / "governance" / "architecture" / "registry.json"
V1_SCHEMA_SHA256 = "6e3102a7cd53b7db1d421889015aa2f978e114256edeefbb25500fec8381281d"
IMPLEMENTATION_COMMITS = [
    "ac2f00def074e5bee7c50753e9bc9af82b655bd2",
    "c7031e5d858ab7130981287e017784727415a12a",
    "90cf95cb6062a4d7213c60380c23f15163fdc43c",
    "078c719a959e1f1a56f6289dde336850f68af237",
    "8ad36b81a95787cc25468387bbbce695e79bcbed",
    "38636518f5638a8c06da9d3366f551cc1cb90f5a",
    "82f9d9985c97ca514fea20e907005525e27f306f",
    "b586e24e680ca4a081b512f48858a247fe77ed2c",
]
INDEX_FIELDS = {"id", "title", "status", "path"}
TERMINAL_STATES = {"cancelled", "reverted"}
VALID_TRANSITIONS = {
    ("proposed", "approved"),
    ("proposed", "cancelled"),
    ("approved", "in_progress"),
    ("approved", "cancelled"),
    ("in_progress", "completed"),
    ("in_progress", "cancelled"),
    ("completed", "published"),
    ("completed", "reverted"),
    ("published", "reverted"),
}


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


def select_work_order_schema(document):
    paths = {1: V1_SCHEMA_PATH, 2: V2_SCHEMA_PATH}
    version = document.get("schema_version")
    if version not in paths:
        raise ValueError(f"Unsupported Work Order schema_version: {version!r}")
    return load_json(paths[version])


def git(*arguments):
    return subprocess.run(
        ["git", *arguments],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def tree_digest(paths):
    digest = hashlib.sha256()
    files = []
    for path in paths:
        files.extend(item for item in path.rglob("*") if item.is_file())
    for path in sorted(files):
        digest.update(path.relative_to(ROOT).as_posix().encode("utf-8"))
        digest.update(path.read_bytes())
    return digest.hexdigest()


def is_safe_relative_path(value):
    path = PurePosixPath(value)
    return (
        not path.is_absolute()
        and value == path.as_posix()
        and all(part not in ("", ".", "..") for part in path.parts)
    )


def transition_issues(document):
    issues = []
    history = document["status_history"]
    for index, transition in enumerate(history):
        pair = transition["from"], transition["to"]
        if pair not in VALID_TRANSITIONS:
            issues.append(("invalid-transition", index))
        if transition["from"] in TERMINAL_STATES:
            issues.append(("terminal-transition", index))
        if index and history[index - 1]["to"] != transition["from"]:
            issues.append(("discontinuous-history", index))
    if history and history[-1]["to"] != document["status"]:
        issues.append(("status-mismatch", len(history) - 1))
    if document["status"] == "published":
        if not history or history[-1]["from"] != "completed":
            issues.append(("published-without-completed", len(history)))
    dates = [datetime.datetime.fromisoformat(item["at"]) for item in history]
    if dates != sorted(dates):
        issues.append(("non-chronological-history", 0))
    created_at = datetime.datetime.fromisoformat(document["created_at"])
    if dates and dates[0] < created_at:
        issues.append(("transition-before-creation", 0))
    return sorted(issues)


class WorkOrderRegistryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.v1_schema = load_json(V1_SCHEMA_PATH)
        cls.v2_schema = load_json(V2_SCHEMA_PATH)
        cls.index = load_json(INDEX_PATH)
        cls.work_order = load_json(WORK_ORDER_PATH)
        cls.valid_fixture = load_json(V2_FIXTURE_ROOT / "valid" / "work-order.json")

    def test_v1_schema_is_byte_for_byte_unchanged_and_fixture_still_validates(self):
        digest = hashlib.sha256(V1_SCHEMA_PATH.read_bytes()).hexdigest()
        self.assertEqual(digest, V1_SCHEMA_SHA256)
        fixture = load_json(V1_FIXTURE_PATH)
        self.assertEqual(stable_schema_errors(make_validator(self.v1_schema), fixture), [])

    def test_schema_selection_is_explicit_for_v1_and_v2(self):
        v1_fixture = load_json(V1_FIXTURE_PATH)
        self.assertEqual(select_work_order_schema(v1_fixture)["properties"]["schema_version"], {"const": 1})
        self.assertEqual(select_work_order_schema(self.work_order)["properties"]["schema_version"], {"const": 2})
        with self.assertRaisesRegex(ValueError, "Unsupported Work Order schema_version"):
            select_work_order_schema({"schema_version": 3})

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

    def test_index_contains_only_the_required_fields_and_matches_document(self):
        self.assertEqual(len(self.index), 1)
        entry = self.index[0]
        self.assertEqual(set(entry), INDEX_FIELDS)
        self.assertEqual(entry["id"], "WORK-009")
        for field in ("id", "title", "status"):
            self.assertEqual(entry[field], self.work_order[field])
        self.assertEqual(entry["path"], "governance/work-orders/WORK-009.json")

    def test_index_paths_are_local_safe_existing_unique_and_not_symlinks(self):
        paths = [entry["path"] for entry in self.index]
        ids = [entry["id"] for entry in self.index]
        self.assertEqual(paths, sorted(set(paths)))
        self.assertEqual(ids, sorted(set(ids)))
        for value in paths:
            self.assertTrue(is_safe_relative_path(value))
            path = ROOT / value
            self.assertTrue(path.is_file())
            current = path
            while current != ROOT:
                self.assertFalse(current.is_symlink())
                current = current.parent
            path.resolve().relative_to(ROOT.resolve())

    def test_work_order_validates_deterministically_without_writes_or_network(self):
        guarded = [ROOT / "governance", V2_FIXTURE_ROOT]
        before = tree_digest(guarded)
        first = stable_schema_errors(make_validator(self.v2_schema), self.work_order)
        second = stable_schema_errors(make_validator(self.v2_schema), self.work_order)
        after = tree_digest(guarded)
        self.assertEqual(first, [])
        self.assertEqual(first, second)
        self.assertEqual(before, after)

    def test_work_order_uses_normative_identity_and_current_state(self):
        self.assertEqual(self.work_order["id"], "WORK-009")
        self.assertEqual(self.work_order["status"], "in_progress")
        self.assertEqual(self.work_order["constitution_version"], "1.0.0")
        self.assertEqual(self.work_order["contract_change"], "creates")
        self.assertEqual(self.work_order["affected_contract_ids"], ["contract.governance-schema"])
        self.assertEqual(self.work_order["affected_capability_ids"], [])

    def test_status_history_is_continuous_real_and_ends_in_current_state(self):
        self.assertEqual(transition_issues(self.work_order), [])
        first_commit_date = git("show", "-s", "--format=%cI", IMPLEMENTATION_COMMITS[0])
        self.assertEqual(self.work_order["created_at"], first_commit_date)
        self.assertEqual(self.work_order["status_history"][0]["at"], first_commit_date)
        self.assertFalse(any(source in TERMINAL_STATES for source, _ in VALID_TRANSITIONS))
        published_origins = {source for source, target in VALID_TRANSITIONS if target == "published"}
        self.assertEqual(published_origins, {"completed"})

    def test_registered_commits_are_exact_real_ancestral_remote_and_chronological(self):
        commits = self.work_order["implementation_commit_ids"]
        self.assertEqual(commits, IMPLEMENTATION_COMMITS)
        self.assertEqual(len(commits), len(set(commits)))
        timestamps = []
        for commit in commits:
            with self.subTest(commit=commit):
                self.assertEqual(len(commit), 40)
                self.assertEqual(git("cat-file", "-t", commit), "commit")
                subprocess.run(["git", "merge-base", "--is-ancestor", commit, "HEAD"], cwd=ROOT, check=True)
                subprocess.run(["git", "merge-base", "--is-ancestor", commit, "origin/main"], cwd=ROOT, check=True)
                timestamps.append(int(git("show", "-s", "--format=%ct", commit)))
        self.assertEqual(timestamps, sorted(timestamps))

    def test_implementation_and_closure_commits_are_separate_without_self_reference(self):
        self.assertIn("implementation_commit_ids", self.work_order)
        self.assertNotIn("registry_closure_commit_id", self.work_order)
        self.assertIn("registry_closure_commit_id", self.v2_schema["properties"])
        self.assertNotIn("registry_closure_commit_id", self.v2_schema["required"])

    def test_historical_tests_have_only_id_command_and_result(self):
        expected_fields = {"id", "command", "result"}
        test_ids = []
        for test in self.work_order["tests"]:
            self.assertEqual(set(test), expected_fields)
            test_ids.append(test["id"])
        self.assertEqual(test_ids, sorted(set(test_ids)))

    def test_contract_references_are_known_and_capabilities_are_not_invented(self):
        architecture = load_json(ARCHITECTURE_PATH)
        known_contracts = set(architecture["contract_ids"])
        self.assertLessEqual(set(self.work_order["affected_contract_ids"]), known_contracts)
        self.assertEqual(self.work_order["affected_capability_ids"], [])

    def test_completed_and_published_require_constitutional_traceability(self):
        required = {
            "implementation_commit_ids",
            "tests",
            "risks",
            "reversal",
            "contract_change",
            "constitution_version",
            "affected_component_ids",
            "affected_contract_ids",
            "affected_capability_ids",
            "status_history",
        }
        for status in ("completed", "published"):
            document = dict(self.valid_fixture)
            document["status"] = status
            if status == "published":
                document["status_history"] = [
                    *document["status_history"],
                    {"from": "completed", "to": "published", "at": "2026-01-01T12:00:00Z"},
                ]
            self.assertTrue(required.issubset(document))
            self.assertEqual(stable_schema_errors(make_validator(self.v2_schema), document), [])
            self.assertEqual(transition_issues(document), [])

    def test_each_invalid_fixture_fails_for_a_specific_reason(self):
        cases = {
            "work-order-completed-missing-commits": ("required", "implementation_commit_ids"),
            "work-order-completed-missing-tests": ("required", "tests"),
            "work-order-completed-missing-risks": ("required", "risks"),
            "work-order-completed-missing-reversal": ("required", "reversal"),
            "work-order-completed-missing-constitution-version": ("required", "constitution_version"),
            "work-order-invalid-contract-classification": ("maxItems", "affected_contract_ids"),
            "work-order-invalid-transition": ("oneOf", "status_history"),
            "work-order-short-commit": ("pattern", "implementation_commit_ids"),
            "work-order-unknown-property": ("additionalProperties", None),
        }
        invalid_dir = V2_FIXTURE_ROOT / "invalid"
        work_order_files = sorted(path for path in invalid_dir.glob("work-order-*.json"))
        self.assertEqual([path.stem for path in work_order_files], sorted(cases))
        validator = make_validator(self.v2_schema)
        for path in work_order_files:
            errors = stable_schema_errors(validator, load_json(path))
            keyword, path_part = cases[path.stem]
            with self.subTest(fixture=path.stem):
                self.assertTrue(errors)
                self.assertTrue(all(error.validator == keyword for error in errors))
                if path_part:
                    self.assertTrue(
                        any(
                            path_part in error.message
                            or path_part in tuple(str(part) for part in error.absolute_path)
                            for error in errors
                        )
                    )

    @staticmethod
    def _nodes(value):
        yield value
        if isinstance(value, dict):
            for child in value.values():
                yield from WorkOrderRegistryTests._nodes(child)
        elif isinstance(value, list):
            for child in value:
                yield from WorkOrderRegistryTests._nodes(child)


if __name__ == "__main__":
    unittest.main()
