import hashlib
import json
import tempfile
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


ROOT = Path(__file__).resolve().parents[2]
WORK_ORDER_PATH = ROOT / "governance/work-orders/WORK-009.json"
WORK_011_PATH = ROOT / "governance/work-orders/WORK-011.json"
WORK_010_PATH = ROOT / "governance/work-orders/WORK-010.json"
V2_SCHEMA_PATH = ROOT / "governance/schemas/v2/work-order.schema.json"
WORK_009_SHA256 = "50edc69a50bcfd6179e68cd4a8fe0021c5e8cfcbd929b725e5f24d3d4c27ac9a"
WORK_010_SHA256 = "f9abb795ec8037625a8781aae623df6bbc223b001af6c461b3db91a8e67ec1c7"
WORK_011_SHA256 = "19f856ddfd64c20ca3dc05a061bdae3a521e4dea74835fbfa93a324b9b936e10"
V2_SCHEMA_SHA256 = "3787ea3b82e11ce19fba6dea453f61a1602b28028bcd42296b51f334f474f3d6"
IMPLEMENTATION_COMMITS = [
    "ac2f00def074e5bee7c50753e9bc9af82b655bd2",
    "c7031e5d858ab7130981287e017784727415a12a",
    "90cf95cb6062a4d7213c60380c23f15163fdc43c",
    "078c719a959e1f1a56f6289dde336850f68af237",
    "8ad36b81a95787cc25468387bbbce695e79bcbed",
    "38636518f5638a8c06da9d3366f551cc1cb90f5a",
    "82f9d9985c97ca514fea20e907005525e27f306f",
    "b586e24e680ca4a081b512f48858a247fe77ed2c",
    "a1e6e842cfdf653452c72a0de9ec7f14aa8aecdc",
]


def load_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def validator(schema):
    return Draft202012Validator(
        schema,
        format_checker=FormatChecker(),
        registry=Registry(
            retrieve=lambda uri: (_ for _ in ()).throw(
                AssertionError(f"Network retrieval attempted: {uri}")
            )
        ),
    )


class HistoricalWorkOrderRegistryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.schema = load_json(V2_SCHEMA_PATH)
        cls.work_009 = load_json(WORK_ORDER_PATH)
        cls.work_011 = load_json(WORK_011_PATH)

    def test_real_legacy_documents_validate_against_schema_v2(self):
        schema_validator = validator(self.schema)
        for path, document in (
            (WORK_ORDER_PATH, self.work_009),
            (WORK_011_PATH, self.work_011),
        ):
            with self.subTest(path=path.name):
                self.assertEqual(list(schema_validator.iter_errors(document)), [])

    def test_real_records_and_required_schema_are_byte_for_byte_intact(self):
        expected = {
            WORK_ORDER_PATH: WORK_009_SHA256,
            WORK_010_PATH: WORK_010_SHA256,
            WORK_011_PATH: WORK_011_SHA256,
            V2_SCHEMA_PATH: V2_SCHEMA_SHA256,
        }
        for path, digest in expected.items():
            with self.subTest(path=path.name):
                self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), digest)

    def test_schema_v2_is_local_closed_and_structurally_valid(self):
        Draft202012Validator.check_schema(self.schema)
        self.assertEqual(self.schema["properties"]["schema_version"], {"const": 2})
        nodes = list(self._nodes(self.schema))
        objects = [node for node in nodes if isinstance(node, dict) and node.get("type") == "object"]
        self.assertTrue(all(node.get("additionalProperties") is False for node in objects))
        refs = [node["$ref"] for node in nodes if isinstance(node, dict) and "$ref" in node]
        self.assertTrue(all(reference.startswith("#/$defs/") for reference in refs))

    def test_work_009_historical_commit_and_closure_fields_are_exact(self):
        self.assertEqual(self.work_009["implementation_commit_ids"], IMPLEMENTATION_COMMITS)
        self.assertEqual(
            self.work_009["registry_closure_commit_id"],
            "759360f02622905cba971695472ef10de4a24aa6",
        )
        self.assertNotIn(
            self.work_009["registry_closure_commit_id"],
            self.work_009["implementation_commit_ids"],
        )

    def test_work_011_remains_cancelled_without_implementation(self):
        self.assertEqual(self.work_011["status"], "cancelled")
        self.assertEqual(self.work_011["implementation_commit_ids"], [])
        self.assertEqual(self.work_011["contract_change"], "modifies")

    def test_missing_required_schema_fails_explicitly(self):
        with tempfile.TemporaryDirectory() as temporary:
            missing = Path(temporary) / "work-order.schema.json"
            with self.assertRaises(FileNotFoundError):
                load_json(missing)

    @staticmethod
    def _nodes(value):
        yield value
        if isinstance(value, dict):
            for child in value.values():
                yield from HistoricalWorkOrderRegistryTests._nodes(child)
        elif isinstance(value, list):
            for child in value:
                yield from HistoricalWorkOrderRegistryTests._nodes(child)


if __name__ == "__main__":
    unittest.main()
