import contextlib
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
from template_system.resolver import TemplateResolver
from template_system.validation import validate_template


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
        self.assertEqual(manifest.description, "")

    def test_loads_an_optional_description(self):
        template = self.make_template()
        manifest_path = template / "template.json"
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        data["description"] = "A reusable agent template."
        manifest_path.write_text(json.dumps(data), encoding="utf-8")

        manifest = TemplateManifest.load(manifest_path)

        self.assertEqual(manifest.description, "A reusable agent template.")

    def test_rejects_a_non_string_description(self):
        template = self.make_template()
        manifest_path = template / "template.json"
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        data["description"] = 42
        manifest_path.write_text(json.dumps(data), encoding="utf-8")

        with self.assertRaises(InvalidTemplateManifest):
            TemplateManifest.load(manifest_path)

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

    def test_lists_registered_templates_in_stable_order(self):
        self.make_template(component_type="department")
        self.make_template(component_type="agent", name="research")
        self.make_template(component_type="agent")
        registry = TemplateRegistry(self.root / "templates")

        manifests = [manifest for _path, manifest in registry.list()]

        self.assertEqual(
            [(manifest.component_type, manifest.name) for manifest in manifests],
            [
                ("agent", "default"),
                ("agent", "research"),
                ("department", "default"),
            ],
        )

    def test_lists_registered_templates_filtered_by_type(self):
        self.make_template(component_type="department")
        agent = self.make_template(component_type="agent")

        templates = TemplateRegistry(self.root / "templates").list("agent")

        self.assertEqual(len(templates), 1)
        self.assertEqual(templates[0][0], agent)


class TemplateResolverTests(TemplateTestCase):
    def test_resolves_default_and_named_registered_templates(self):
        default = self.make_template()
        named = self.make_template(name="research")
        resolver = TemplateResolver(TemplateRegistry(self.root / "templates"))

        self.assertEqual(resolver.resolve("agent").files_dir, default / "files")
        self.assertEqual(
            resolver.resolve("agent", "research").files_dir, named / "files"
        )

    def test_existing_external_directory_has_priority_over_registered_name(self):
        self.make_template(name="research")
        external = self.root / "research"
        external.mkdir()
        resolver = TemplateResolver(TemplateRegistry(self.root / "templates"))

        with contextlib.chdir(self.root):
            resolved = resolver.resolve("agent", "research")

        self.assertEqual(resolved.files_dir, Path("research"))
        self.assertFalse(resolved.registered)

    def test_rejects_missing_path_like_selection_with_clear_error(self):
        resolver = TemplateResolver(TemplateRegistry(self.root / "templates"))
        missing = self.root / "missing" / "template"

        with self.assertRaisesRegex(TemplateNotFound, "No existe el directorio"):
            resolver.resolve("agent", str(missing))


class TemplateValidationTests(TemplateTestCase):
    def test_validates_a_registered_template(self):
        template = self.make_template(required_variables=["component_name"])
        (template / "files" / "README.md").write_text(
            "{{ component_name }}\n", encoding="utf-8"
        )

        manifest, file_count = validate_template(
            TemplateRegistry(self.root / "templates"),
            TemplateRenderer(),
            "agent",
            "default",
        )

        self.assertEqual(manifest.name, "default")
        self.assertEqual(file_count, 1)

    def test_validates_a_legacy_external_template_without_writing(self):
        external = self.root / "legacy"
        external.mkdir()
        (external / "README.md").write_text(
            "{{ component_type }}: {{ component_name }}\n", encoding="utf-8"
        )
        (external / "asset.bin").write_bytes(b"\xff\x00")
        before = sorted(path.relative_to(self.root) for path in self.root.rglob("*"))

        manifest, file_count = validate_template(
            TemplateRegistry(self.root / "templates"),
            TemplateRenderer(),
            "agent",
            external,
        )

        after = sorted(path.relative_to(self.root) for path in self.root.rglob("*"))
        self.assertEqual(manifest.name, "legacy")
        self.assertEqual(manifest.description, "Plantilla externa heredada.")
        self.assertEqual(file_count, 2)
        self.assertEqual(after, before)

    def test_existing_external_path_has_priority_over_registered_name(self):
        self.make_template(name="research")
        external = self.root / "research"
        external.mkdir()
        (external / "source.txt").write_text("external\n", encoding="utf-8")

        with contextlib.chdir(self.root):
            manifest, file_count = validate_template(
                TemplateRegistry(self.root / "templates"),
                TemplateRenderer(),
                "agent",
                "research",
            )

        self.assertEqual(manifest.description, "Plantilla externa heredada.")
        self.assertEqual(file_count, 1)

    def test_validates_an_external_template_with_a_manifest(self):
        external = self.root / "modern"
        (external / "files").mkdir(parents=True)
        (external / "template.json").write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "component_type": "agent",
                    "name": "modern",
                    "description": "Modern external template.",
                    "required_variables": ["component_name"],
                }
            ),
            encoding="utf-8",
        )
        (external / "files" / "README.md").write_text(
            "{{ component_name }}\n", encoding="utf-8"
        )

        manifest, file_count = validate_template(
            TemplateRegistry(self.root / "templates"),
            TemplateRenderer(),
            "agent",
            external,
        )

        self.assertEqual(manifest.name, "modern")
        self.assertEqual(file_count, 1)

    def test_rejects_a_missing_path_and_an_invalid_external_structure(self):
        registry = TemplateRegistry(self.root / "templates")
        missing = self.root / "missing" / "template"
        with self.assertRaisesRegex(TemplateNotFound, "No existe el directorio"):
            validate_template(
                registry, TemplateRenderer(), "agent", str(missing)
            )

        external = self.root / "modern"
        external.mkdir()
        (external / "template.json").write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "component_type": "agent",
                    "name": "modern",
                    "required_variables": [],
                }
            ),
            encoding="utf-8",
        )
        with self.assertRaises(TemplateRenderError):
            validate_template(registry, TemplateRenderer(), "agent", external)

    def test_rejects_external_symlinks(self):
        external = self.root / "legacy"
        external.mkdir()
        target = self.root / "target.txt"
        target.write_text("secret\n", encoding="utf-8")
        (external / "linked.txt").symlink_to(target)

        with self.assertRaises(TemplateRenderError):
            validate_template(
                TemplateRegistry(self.root / "templates"),
                TemplateRenderer(),
                "agent",
                external,
            )


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

    def test_validates_text_and_binary_files_without_writing(self):
        template = self.make_template(required_variables=["component_name"])
        (template / "files" / "README.md").write_text(
            "{{ component_name }}\n", encoding="utf-8"
        )
        (template / "files" / "asset.bin").write_bytes(b"\xff\x00")
        manifest = TemplateManifest.load(template / "template.json")
        before = sorted(path.relative_to(self.root) for path in self.root.rglob("*"))

        file_count = TemplateRenderer().validate(
            template, manifest, {"component_name": "assistant"}
        )

        after = sorted(path.relative_to(self.root) for path in self.root.rglob("*"))
        self.assertEqual(file_count, 2)
        self.assertEqual(after, before)

    def test_validation_rejects_unknown_markers_without_writing(self):
        template = self.make_template()
        (template / "files" / "README.md").write_text(
            "{{ unknown }}\n", encoding="utf-8"
        )
        manifest = TemplateManifest.load(template / "template.json")
        before = sorted(path.relative_to(self.root) for path in self.root.rglob("*"))

        with self.assertRaises(TemplateRenderError):
            TemplateRenderer().validate(template, manifest, {})

        after = sorted(path.relative_to(self.root) for path in self.root.rglob("*"))
        self.assertEqual(after, before)

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
