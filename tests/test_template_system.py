import json
import tempfile
import unittest
from pathlib import Path

from template_system.errors import (
    InvalidTemplateManifest,
    TemplateNotFound,
    TemplateRenderError,
)
from template_system.manifest import TemplateManifest
from template_system.registry import TemplateRegistry
from template_system.renderer import TemplateRenderer


class TemplateTestCase(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)

    def tearDown(self):
        self.temporary_directory.cleanup()

    def make_template(
        self,
        component_type="agent",
        name="default",
        required_variables=None,
    ):
        template = self.root / "templates" / component_type / name
        (template / "files").mkdir(parents=True)
        (template / "template.json").write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "component_type": component_type,
                    "name": name,
                    "required_variables": required_variables or [],
                }
            ),
            encoding="utf-8",
        )
        return template


class TemplateManifestTests(TemplateTestCase):
    def test_loads_a_valid_manifest(self):
        template = self.make_template(required_variables=["component_name"])

        manifest = TemplateManifest.load(template / "template.json")

        self.assertEqual(manifest.schema_version, 1)
        self.assertEqual(manifest.component_type, "agent")
        self.assertEqual(manifest.name, "default")
        self.assertEqual(manifest.required_variables, ("component_name",))

    def test_rejects_invalid_json_and_schema(self):
        manifest_path = self.root / "template.json"
        manifest_path.write_text("not-json", encoding="utf-8")
        with self.assertRaises(InvalidTemplateManifest):
            TemplateManifest.load(manifest_path)

        manifest_path.write_text(
            json.dumps(
                {
                    "schema_version": 2,
                    "component_type": "agent",
                    "name": "default",
                    "required_variables": [],
                }
            ),
            encoding="utf-8",
        )
        with self.assertRaises(InvalidTemplateManifest):
            TemplateManifest.load(manifest_path)

    def test_rejects_duplicate_or_invalid_variables(self):
        template = self.make_template(required_variables=["name", "name"])
        with self.assertRaises(InvalidTemplateManifest):
            TemplateManifest.load(template / "template.json")

        manifest_path = template / "template.json"
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        data["required_variables"] = ["invalid variable"]
        manifest_path.write_text(json.dumps(data), encoding="utf-8")
        with self.assertRaises(InvalidTemplateManifest):
            TemplateManifest.load(manifest_path)


class TemplateRegistryTests(TemplateTestCase):
    def test_resolves_a_registered_template(self):
        template = self.make_template()

        path, manifest = TemplateRegistry(self.root / "templates").resolve("agent")

        self.assertEqual(path, template)
        self.assertEqual(manifest.component_type, "agent")

    def test_rejects_unknown_and_unsafe_template_keys(self):
        registry = TemplateRegistry(self.root / "templates")
        for component_type in ("missing", "../agent", "/tmp/agent"):
            with self.subTest(component_type=component_type):
                with self.assertRaises(TemplateNotFound):
                    registry.resolve(component_type)

    def test_rejects_manifest_that_does_not_match_its_location(self):
        template = self.make_template()
        manifest_path = template / "template.json"
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        data["component_type"] = "department"
        manifest_path.write_text(json.dumps(data), encoding="utf-8")

        with self.assertRaises(InvalidTemplateManifest):
            TemplateRegistry(self.root / "templates").resolve("agent")


class TemplateRendererTests(TemplateTestCase):
    def test_renders_text_and_binary_files(self):
        template = self.make_template(required_variables=["component_name"])
        (template / "files" / "README.md").write_text(
            "# {{ component_name }}\n", encoding="utf-8"
        )
        binary_content = b"\xff\x00\x10"
        (template / "files" / "asset.bin").write_bytes(binary_content)
        destination = self.root / "result"
        manifest = TemplateManifest.load(template / "template.json")

        TemplateRenderer().render(
            template, destination, manifest, {"component_name": "assistant"}
        )

        self.assertEqual(
            (destination / "README.md").read_text(encoding="utf-8"), "# assistant\n"
        )
        self.assertEqual((destination / "asset.bin").read_bytes(), binary_content)

    def test_renders_variable_values_with_regular_expression_characters(self):
        template = self.make_template(required_variables=["component_name"])
        (template / "files" / "value.txt").write_text(
            "{{ component_name }}\n", encoding="utf-8"
        )
        destination = self.root / "result"
        manifest = TemplateManifest.load(template / "template.json")

        TemplateRenderer().render(
            template, destination, manifest, {"component_name": r"value\1"}
        )

        self.assertEqual(
            (destination / "value.txt").read_text(encoding="utf-8"), "value\\1\n"
        )

    def test_rejects_missing_and_unknown_variables_before_writing(self):
        template = self.make_template(required_variables=["component_name"])
        (template / "files" / "README.md").write_text(
            "{{ unknown_variable }}\n", encoding="utf-8"
        )
        destination = self.root / "result"
        manifest = TemplateManifest.load(template / "template.json")

        with self.assertRaises(TemplateRenderError):
            TemplateRenderer().render(template, destination, manifest, {})
        self.assertFalse(destination.exists())

        with self.assertRaises(TemplateRenderError):
            TemplateRenderer().render(
                template, destination, manifest, {"component_name": "assistant"}
            )
        self.assertFalse(destination.exists())

    def test_does_not_overwrite_existing_files(self):
        template = self.make_template()
        (template / "files" / "README.md").write_text("Template\n", encoding="utf-8")
        destination = self.root / "result"
        destination.mkdir()
        (destination / "README.md").write_text("Custom\n", encoding="utf-8")
        manifest = TemplateManifest.load(template / "template.json")

        TemplateRenderer().render(template, destination, manifest, {})

        self.assertEqual(
            (destination / "README.md").read_text(encoding="utf-8"), "Custom\n"
        )

    def test_rejects_template_symlinks_before_writing(self):
        template = self.make_template()
        external_file = self.root / "external.txt"
        external_file.write_text("secret\n", encoding="utf-8")
        (template / "files" / "linked.txt").symlink_to(external_file)
        destination = self.root / "result"
        manifest = TemplateManifest.load(template / "template.json")

        with self.assertRaises(TemplateRenderError):
            TemplateRenderer().render(template, destination, manifest, {})
        self.assertFalse(destination.exists())

    def test_rejects_destination_paths_that_escape_through_symlinks(self):
        template = self.make_template()
        (template / "files" / "nested").mkdir()
        (template / "files" / "nested" / "file.txt").write_text(
            "content\n", encoding="utf-8"
        )
        destination = self.root / "result"
        destination.mkdir()
        external = self.root / "external"
        external.mkdir()
        (destination / "nested").symlink_to(external, target_is_directory=True)
        manifest = TemplateManifest.load(template / "template.json")

        with self.assertRaises(TemplateRenderError):
            TemplateRenderer().render(template, destination, manifest, {})
        self.assertFalse((external / "file.txt").exists())
