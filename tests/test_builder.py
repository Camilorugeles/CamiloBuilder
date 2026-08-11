import contextlib
import inspect
import subprocess
import sys
import tempfile
import unittest
import json
from pathlib import Path

import builder
from builder_cli import COMMANDS, COMPONENT_COMMANDS, build_parser
from builders.agent_builder import AgentBuilder
from builders.component_builder import (
    InvalidComponentName,
    InvalidTemplate,
    ProjectNotFound,
)
from builders.component_catalog import ComponentCatalog, ComponentNotFound
from builders.department_builder import DepartmentBuilder
from builders.project_builder import InvalidProjectName, ProjectBuilder
from builders.service_builder import ServiceBuilder
from builders.templated_component_builder import TemplatedComponentBuilder


ROOT = Path(__file__).resolve().parents[1]


class CommandRegistrationTests(unittest.TestCase):
    EXPECTED_COMMANDS = (
        "status",
        "create-project",
        "create-agent",
        "create-department",
        "create-service",
        "list-agents",
        "list-departments",
        "list-services",
        "inspect-agent",
        "inspect-department",
        "inspect-service",
        "list-templates",
        "inspect-template",
        "validate-template",
    )

    def test_registry_declares_exactly_the_current_commands_in_order(self):
        self.assertEqual(
            tuple(command["name"] for command in COMMANDS),
            self.EXPECTED_COMMANDS,
        )
        self.assertEqual(len({command["name"] for command in COMMANDS}), 14)

    def test_every_command_declares_description_handler_and_builder(self):
        for command in COMMANDS:
            with self.subTest(command=command["name"]):
                self.assertIn("description", command)
                self.assertIn("handler", command)
                self.assertIn("builder", command)
                self.assertTrue(callable(command["handler"]))
                self.assertTrue(callable(command["configure"]))

    def test_component_commands_declare_the_expected_builders(self):
        builders_by_command = {
            command["name"]: command["builder"] for command in COMMANDS
        }
        for suffix, builder_class in (
            ("agent", AgentBuilder),
            ("department", DepartmentBuilder),
            ("service", ServiceBuilder),
        ):
            with self.subTest(component=suffix):
                self.assertIs(builders_by_command[f"create-{suffix}"], builder_class)
                list_name = f"list-{suffix}s" if suffix != "department" else "list-departments"
                self.assertIs(builders_by_command[list_name], builder_class)
                self.assertIs(builders_by_command[f"inspect-{suffix}"], builder_class)

    def test_each_component_type_uses_one_declarative_registry_entry(self):
        self.assertEqual(
            tuple(component["builder"] for component in COMPONENT_COMMANDS),
            (AgentBuilder, DepartmentBuilder, ServiceBuilder),
        )
        for component in COMPONENT_COMMANDS:
            with self.subTest(builder=component["builder"].__name__):
                self.assertEqual(
                    set(component), {"builder", "create", "list", "inspect"}
                )
                for operation in ("create", "list", "inspect"):
                    self.assertIs(
                        component[operation]["builder"], component["builder"]
                    )

    def test_registered_parsers_receive_handlers_and_builders(self):
        parser = build_parser()
        for arguments, expected_builder in (
            (("status",), None),
            (("create-agent", "demo", "assistant"), AgentBuilder),
            (("create-department", "demo", "operations"), DepartmentBuilder),
            (("create-service", "demo", "api"), ServiceBuilder),
            (("list-services", "demo"), ServiceBuilder),
            (("inspect-service", "demo", "api"), ServiceBuilder),
        ):
            with self.subTest(arguments=arguments):
                args = parser.parse_args(arguments)
                self.assertTrue(callable(args.handler))
                self.assertIs(args.builder, expected_builder)

    def test_builder_module_preserves_the_public_facade(self):
        for name in (
            "create_component",
            "create_project",
            "get_catalog",
            "inspect_component",
            "inspect_service",
            "inspect_template",
            "list_components",
            "list_templates",
            "main",
            "status",
            "template_details",
            "validate_template",
        ):
            with self.subTest(name=name):
                self.assertTrue(callable(getattr(builder, name)))


class TemplatedComponentBuilderStructureTests(unittest.TestCase):
    def test_concrete_builders_share_the_templated_base(self):
        self.assertTrue(issubclass(AgentBuilder, TemplatedComponentBuilder))
        self.assertTrue(issubclass(DepartmentBuilder, TemplatedComponentBuilder))
        self.assertTrue(issubclass(ServiceBuilder, TemplatedComponentBuilder))
        self.assertNotIn("__init__", AgentBuilder.__dict__)
        self.assertNotIn("build", AgentBuilder.__dict__)
        self.assertNotIn("__init__", DepartmentBuilder.__dict__)
        self.assertNotIn("build", DepartmentBuilder.__dict__)
        self.assertNotIn("__init__", ServiceBuilder.__dict__)
        self.assertNotIn("build", ServiceBuilder.__dict__)

    def test_concrete_builders_preserve_the_public_constructor_signature(self):
        expected_parameters = (
            "project_dir",
            "template_dir",
            "templates_dir",
            "renderer",
        )

        for builder_class in (AgentBuilder, DepartmentBuilder, ServiceBuilder):
            with self.subTest(builder_class=builder_class.__name__):
                signature = inspect.signature(builder_class)
                self.assertEqual(tuple(signature.parameters), expected_parameters)
                self.assertEqual(
                    signature, inspect.signature(TemplatedComponentBuilder)
                )

    def test_concrete_builders_declare_their_component_metadata(self):
        self.assertEqual(
            (
                AgentBuilder.component_type,
                AgentBuilder.component_folder,
                AgentBuilder.component_label,
            ),
            ("agent", "agents", "Agente"),
        )
        self.assertEqual(
            (
                DepartmentBuilder.component_type,
                DepartmentBuilder.component_folder,
                DepartmentBuilder.component_label,
            ),
            ("department", "departments", "Departamento"),
        )
        self.assertEqual(
            (
                ServiceBuilder.component_type,
                ServiceBuilder.component_folder,
                ServiceBuilder.component_label,
            ),
            ("service", "services", "Servicio"),
        )


class ProjectBuilderTests(unittest.TestCase):
    def test_build_creates_expected_structure(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            project = ProjectBuilder(Path(temporary_directory)).build("demo-project")

            self.assertEqual(project.name, "demo-project")
            self.assertEqual(
                (project / "README.md").read_text(encoding="utf-8"),
                "# CAMILO OS\n\nProyecto generado por Camilo Builder.\n",
            )
            self.assertEqual(
                sorted(path.name for path in project.iterdir()),
                sorted((*ProjectBuilder.FOLDERS, "README.md")),
            )
            for folder_name in ProjectBuilder.FOLDERS:
                folder = project / folder_name
                self.assertEqual(
                    sorted(path.name for path in folder.iterdir()), ["__init__.py"]
                )

    def test_build_is_idempotent(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            builder = ProjectBuilder(Path(temporary_directory))
            first = builder.build("demo")
            second = builder.build("demo")

            self.assertEqual(first, second)

    def test_build_does_not_overwrite_existing_project_files(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            builder = ProjectBuilder(Path(temporary_directory))
            project = builder.build("demo")
            (project / "README.md").write_text("Personalizado\n", encoding="utf-8")

            builder.build("demo")

            self.assertEqual(
                (project / "README.md").read_text(encoding="utf-8"),
                "Personalizado\n",
            )

    def test_build_rejects_unsafe_project_names(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            builder = ProjectBuilder(Path(temporary_directory))
            for name in ("", ".", "..", "../outside", "nested/project", "bad name"):
                with self.subTest(name=name):
                    with self.assertRaises(InvalidProjectName):
                        builder.build(name)


class ComponentBuilderTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.project = ProjectBuilder(Path(self.temporary_directory.name)).build("demo")

    def tearDown(self):
        self.temporary_directory.cleanup()

    def test_agent_builder_creates_expected_structure(self):
        agent = AgentBuilder(self.project).build("research-agent")

        self.assertEqual(agent, self.project / "agents" / "research-agent")
        self.assertTrue((agent / "__init__.py").is_file())
        self.assertEqual(
            (agent / "README.md").read_text(encoding="utf-8"),
            "# research-agent\n\nAgente de Camilo OS.\n",
        )
        self.assertEqual(
            sorted(path.name for path in agent.iterdir()), ["README.md", "__init__.py"]
        )

    def test_department_builder_creates_expected_structure(self):
        department = DepartmentBuilder(self.project).build("operations")

        self.assertEqual(department, self.project / "departments" / "operations")
        self.assertTrue((department / "__init__.py").is_file())
        self.assertEqual(
            (department / "README.md").read_text(encoding="utf-8"),
            "# operations\n\nDepartamento de Camilo OS.\n",
        )
        self.assertEqual(
            sorted(path.name for path in department.iterdir()),
            ["README.md", "__init__.py"],
        )

    def test_component_build_is_idempotent_and_preserves_readme(self):
        builder = AgentBuilder(self.project)
        agent = builder.build("assistant")
        (agent / "README.md").write_text("Personalizado\n", encoding="utf-8")

        self.assertEqual(builder.build("assistant"), agent)
        self.assertEqual(
            (agent / "README.md").read_text(encoding="utf-8"), "Personalizado\n"
        )

    def test_component_builder_rejects_unsafe_names(self):
        builder = AgentBuilder(self.project)
        for name in ("", ".", "..", "../outside", "nested/agent", "bad name"):
            with self.subTest(name=name):
                with self.assertRaises(InvalidComponentName):
                    builder.build(name)

    def test_component_builder_requires_an_existing_project(self):
        missing = Path(self.temporary_directory.name) / "missing"

        with self.assertRaises(ProjectNotFound):
            AgentBuilder(missing).build("assistant")

    def test_component_builder_applies_a_configurable_template(self):
        template = Path(self.temporary_directory.name) / "template"
        (template / "config").mkdir(parents=True)
        (template / "README.md").write_text(
            "# {{ component_name }}\n\nTipo: {{ component_type }}.\n",
            encoding="utf-8",
        )
        (template / "config" / "settings.json").write_text(
            '{"name": "{{ component_name }}"}\n', encoding="utf-8"
        )

        agent = AgentBuilder(self.project, template).build("assistant")

        self.assertEqual(
            (agent / "README.md").read_text(encoding="utf-8"),
            "# assistant\n\nTipo: agente.\n",
        )
        self.assertEqual(
            (agent / "config" / "settings.json").read_text(encoding="utf-8"),
            '{"name": "assistant"}\n',
        )

    def test_component_template_does_not_overwrite_existing_files(self):
        template = Path(self.temporary_directory.name) / "template"
        template.mkdir()
        (template / "README.md").write_text("Plantilla\n", encoding="utf-8")
        builder = DepartmentBuilder(self.project, template)
        department = builder.build("operations")
        (department / "README.md").write_text("Personalizado\n", encoding="utf-8")

        builder.build("operations")

        self.assertEqual(
            (department / "README.md").read_text(encoding="utf-8"),
            "Personalizado\n",
        )

    def test_component_builder_rejects_a_missing_template(self):
        missing = Path(self.temporary_directory.name) / "missing-template"

        with self.assertRaises(InvalidTemplate):
            AgentBuilder(self.project, missing).build("assistant")
        self.assertFalse((self.project / "agents" / "assistant").exists())

    def test_agent_builder_resolves_a_registered_template(self):
        templates = Path(self.temporary_directory.name) / "registered"
        template = templates / "agent" / "research"
        (template / "files").mkdir(parents=True)
        (template / "template.json").write_text(
            '{"schema_version": 1, "component_type": "agent", '
            '"name": "research", "required_variables": ["component_name"]}',
            encoding="utf-8",
        )
        (template / "files" / "profile.txt").write_text(
            "Research: {{ component_name }}\n", encoding="utf-8"
        )

        agent = AgentBuilder(
            self.project, "research", templates_dir=templates
        ).build("analyst")

        self.assertEqual(
            (agent / "profile.txt").read_text(encoding="utf-8"),
            "Research: analyst\n",
        )
        self.assertTrue((agent / "__init__.py").is_file())

    def test_existing_external_path_takes_priority_over_registered_name(self):
        templates = Path(self.temporary_directory.name) / "registered"
        registered = templates / "agent" / "research"
        (registered / "files").mkdir(parents=True)
        (registered / "template.json").write_text(
            '{"schema_version": 1, "component_type": "agent", '
            '"name": "research", "required_variables": []}',
            encoding="utf-8",
        )
        (registered / "files" / "source.txt").write_text(
            "registered\n", encoding="utf-8"
        )
        external = Path(self.temporary_directory.name) / "research"
        external.mkdir()
        (external / "source.txt").write_text("external\n", encoding="utf-8")

        agent = AgentBuilder(
            self.project, external, templates_dir=templates
        ).build("analyst")

        self.assertEqual(
            (agent / "source.txt").read_text(encoding="utf-8"), "external\n"
        )

    def test_external_agent_template_preserves_binary_files(self):
        template = Path(self.temporary_directory.name) / "external-template"
        template.mkdir()
        content = b"\xff\x00\x10"
        (template / "asset.bin").write_bytes(content)

        agent = AgentBuilder(self.project, template).build("assistant")

        self.assertEqual((agent / "asset.bin").read_bytes(), content)

    def test_external_agent_template_rejects_symlinks(self):
        template = Path(self.temporary_directory.name) / "external-template"
        template.mkdir()
        external = Path(self.temporary_directory.name) / "external.txt"
        external.write_text("secret\n", encoding="utf-8")
        (template / "linked.txt").symlink_to(external)

        with self.assertRaises(ValueError):
            AgentBuilder(self.project, template).build("assistant")
        self.assertFalse((self.project / "agents" / "assistant").exists())


class DepartmentTemplateTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.project = ProjectBuilder(self.root).build("demo")

    def tearDown(self):
        self.temporary_directory.cleanup()

    def make_registered_template(self, name="operations"):
        templates = self.root / "registered"
        template = templates / "department" / name
        (template / "files").mkdir(parents=True)
        (template / "template.json").write_text(
            '{"schema_version": 1, "component_type": "department", '
            f'"name": "{name}", "required_variables": ["component_name"]}}',
            encoding="utf-8",
        )
        return templates, template

    def test_resolves_a_registered_department_template(self):
        templates, template = self.make_registered_template()
        (template / "files" / "profile.txt").write_text(
            "Department: {{ component_name }}\n", encoding="utf-8"
        )

        department = DepartmentBuilder(
            self.project, "operations", templates_dir=templates
        ).build("support")

        self.assertEqual(
            (department / "profile.txt").read_text(encoding="utf-8"),
            "Department: support\n",
        )
        self.assertTrue((department / "__init__.py").is_file())

    def test_existing_external_path_has_priority_over_registered_name(self):
        templates, registered = self.make_registered_template()
        (registered / "files" / "source.txt").write_text(
            "registered\n", encoding="utf-8"
        )
        external = self.root / "operations"
        external.mkdir()
        (external / "source.txt").write_text("external\n", encoding="utf-8")

        with contextlib.chdir(self.root):
            department = DepartmentBuilder(
                self.project, "operations", templates_dir=templates
            ).build("support")

        self.assertEqual(
            (department / "source.txt").read_text(encoding="utf-8"), "external\n"
        )

    def test_external_template_renders_variables_and_binary_files(self):
        template = self.root / "external-template"
        template.mkdir()
        (template / "details.txt").write_text(
            "{{ component_type }}: {{ component_name }}\n", encoding="utf-8"
        )
        binary_content = b"\xff\x00\x10"
        (template / "asset.bin").write_bytes(binary_content)

        department = DepartmentBuilder(self.project, template).build("support")

        self.assertEqual(
            (department / "details.txt").read_text(encoding="utf-8"),
            "departamento: support\n",
        )
        self.assertEqual((department / "asset.bin").read_bytes(), binary_content)

    def test_default_template_is_idempotent_and_preserves_custom_files(self):
        builder = DepartmentBuilder(self.project)
        department = builder.build("support")
        (department / "README.md").write_text("Personalizado\n", encoding="utf-8")
        (department / "custom.txt").write_text("custom\n", encoding="utf-8")

        self.assertEqual(builder.build("support"), department)
        self.assertEqual(
            (department / "README.md").read_text(encoding="utf-8"),
            "Personalizado\n",
        )
        self.assertEqual(
            (department / "custom.txt").read_text(encoding="utf-8"), "custom\n"
        )

    def test_rejects_a_missing_external_template_path(self):
        missing = self.root / "missing" / "department-template"

        with self.assertRaisesRegex(InvalidTemplate, "No existe el directorio"):
            DepartmentBuilder(self.project, missing).build("support")
        self.assertFalse((self.project / "departments" / "support").exists())

    def test_rejects_external_template_symlinks_before_writing(self):
        template = self.root / "external-template"
        template.mkdir()
        external = self.root / "external.txt"
        external.write_text("secret\n", encoding="utf-8")
        (template / "linked.txt").symlink_to(external)

        with self.assertRaises(ValueError):
            DepartmentBuilder(self.project, template).build("support")
        self.assertFalse((self.project / "departments" / "support").exists())

    def test_rejects_destination_escape_through_a_symlink(self):
        template = self.root / "external-template"
        (template / "nested").mkdir(parents=True)
        (template / "nested" / "file.txt").write_text("content\n", encoding="utf-8")
        department = self.project / "departments" / "support"
        department.mkdir()
        external = self.root / "external"
        external.mkdir()
        (department / "nested").symlink_to(external, target_is_directory=True)

        with self.assertRaises(ValueError):
            DepartmentBuilder(self.project, template).build("support")
        self.assertFalse((external / "file.txt").exists())


class ServiceBuilderTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.project = ProjectBuilder(self.root).build("demo")

    def tearDown(self):
        self.temporary_directory.cleanup()

    def make_registered_template(self, name="worker"):
        templates = self.root / "registered"
        template = templates / "service" / name
        (template / "files").mkdir(parents=True)
        (template / "template.json").write_text(
            '{"schema_version": 1, "component_type": "service", '
            f'"name": "{name}", "required_variables": ["component_name"]}}',
            encoding="utf-8",
        )
        return templates, template

    def test_builds_the_exact_default_service_structure(self):
        service = ServiceBuilder(self.project).build("notifications")

        self.assertEqual(service, self.project / "services" / "notifications")
        self.assertEqual(
            sorted(path.name for path in service.iterdir()),
            ["README.md", "__init__.py"],
        )
        self.assertEqual(
            (service / "README.md").read_bytes(),
            b"# notifications\n\nServicio de Camilo OS.\n",
        )

    def test_default_service_is_idempotent_and_preserves_custom_files(self):
        builder = ServiceBuilder(self.project)
        service = builder.build("notifications")
        (service / "README.md").write_text("Personalizado\n", encoding="utf-8")
        (service / "custom.txt").write_text("custom\n", encoding="utf-8")

        self.assertEqual(builder.build("notifications"), service)
        self.assertEqual(
            (service / "README.md").read_text(encoding="utf-8"),
            "Personalizado\n",
        )
        self.assertEqual(
            (service / "custom.txt").read_text(encoding="utf-8"), "custom\n"
        )

    def test_resolves_a_registered_service_template(self):
        templates, template = self.make_registered_template()
        (template / "files" / "worker.txt").write_text(
            "Worker: {{ component_name }}\n", encoding="utf-8"
        )

        service = ServiceBuilder(
            self.project, "worker", templates_dir=templates
        ).build("notifications")

        self.assertEqual(
            (service / "worker.txt").read_text(encoding="utf-8"),
            "Worker: notifications\n",
        )

    def test_existing_external_path_has_priority_over_registered_name(self):
        templates, registered = self.make_registered_template()
        (registered / "files" / "source.txt").write_text(
            "registered\n", encoding="utf-8"
        )
        external = self.root / "worker"
        external.mkdir()
        (external / "source.txt").write_text("external\n", encoding="utf-8")

        with contextlib.chdir(self.root):
            service = ServiceBuilder(
                self.project, "worker", templates_dir=templates
            ).build("notifications")

        self.assertEqual(
            (service / "source.txt").read_text(encoding="utf-8"), "external\n"
        )

    def test_external_template_renders_variables_and_binary_files(self):
        template = self.root / "external-template"
        template.mkdir()
        (template / "details.txt").write_text(
            "{{ component_type }}: {{ component_name }}\n", encoding="utf-8"
        )
        binary_content = b"\xff\x00\x10"
        (template / "asset.bin").write_bytes(binary_content)

        service = ServiceBuilder(self.project, template).build("notifications")

        self.assertEqual(
            (service / "details.txt").read_text(encoding="utf-8"),
            "servicio: notifications\n",
        )
        self.assertEqual((service / "asset.bin").read_bytes(), binary_content)

    def test_rejects_missing_templates_unsafe_names_and_missing_projects(self):
        missing_template = self.root / "missing" / "service-template"
        with self.assertRaisesRegex(InvalidTemplate, "No existe el directorio"):
            ServiceBuilder(self.project, missing_template).build("notifications")
        with self.assertRaises(InvalidComponentName):
            ServiceBuilder(self.project).build("../service")
        with self.assertRaises(ProjectNotFound):
            ServiceBuilder(self.root / "missing-project").build("notifications")

    def test_rejects_external_symlinks_and_destination_escapes(self):
        template = self.root / "external-template"
        template.mkdir()
        external_file = self.root / "external.txt"
        external_file.write_text("secret\n", encoding="utf-8")
        (template / "linked.txt").symlink_to(external_file)
        with self.assertRaises(ValueError):
            ServiceBuilder(self.project, template).build("notifications")

        (template / "linked.txt").unlink()
        (template / "nested").mkdir()
        (template / "nested" / "file.txt").write_text("content\n", encoding="utf-8")
        service = self.project / "services" / "notifications"
        service.mkdir()
        external_dir = self.root / "external"
        external_dir.mkdir()
        (service / "nested").symlink_to(external_dir, target_is_directory=True)
        with self.assertRaises(ValueError):
            ServiceBuilder(self.project, template).build("notifications")
        self.assertFalse((external_dir / "file.txt").exists())


class ComponentCatalogTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.project = ProjectBuilder(Path(self.temporary_directory.name)).build("demo")

    def tearDown(self):
        self.temporary_directory.cleanup()

    def test_list_names_returns_sorted_components(self):
        AgentBuilder(self.project).build("writer")
        AgentBuilder(self.project).build("analyst")
        catalog = ComponentCatalog(self.project, "agents", "Agente")

        self.assertEqual(catalog.list_names(), ["analyst", "writer"])

    def test_inspect_returns_component_details(self):
        agent = AgentBuilder(self.project).build("assistant")
        (agent / "config").mkdir()
        (agent / "config" / "settings.json").write_text("{}\n", encoding="utf-8")
        catalog = ComponentCatalog(self.project, "agents", "Agente")

        details = catalog.inspect("assistant")

        self.assertEqual(details["name"], "assistant")
        self.assertEqual(details["type"], "agente")
        self.assertEqual(details["path"], str(agent))
        self.assertEqual(
            details["files"], ["README.md", "__init__.py", "config/settings.json"]
        )

    def test_inspect_rejects_a_missing_component(self):
        catalog = ComponentCatalog(self.project, "departments", "Departamento")

        with self.assertRaises(ComponentNotFound):
            catalog.inspect("missing")


class CommandLineTests(unittest.TestCase):
    def run_builder(self, *arguments):
        return subprocess.run(
            [sys.executable, str(ROOT / "builder.py"), *arguments],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )

    def test_status_reports_operational(self):
        result = self.run_builder("status")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Estado: Operativo", result.stdout)

    def test_no_arguments_prints_help_with_success(self):
        result = self.run_builder()

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")
        self.assertTrue(result.stdout.startswith("usage: builder"))

    def test_help_preserves_command_order(self):
        result = self.run_builder("--help")

        self.assertEqual(result.returncode, 0, result.stderr)
        command_list = "{" + ",".join(CommandRegistrationTests.EXPECTED_COMMANDS) + "}"
        self.assertIn(command_list, "".join(result.stdout.split()))

    def test_unknown_command_preserves_argparse_error_behavior(self):
        result = self.run_builder("unknown-command")

        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, "")
        self.assertTrue(result.stderr.startswith("usage: builder"))
        self.assertIn("invalid choice: 'unknown-command'", result.stderr)

    def test_create_project_supports_custom_output(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            result = self.run_builder(
                "create-project", "cli-demo", "--output", temporary_directory
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("Proyecto creado:", result.stdout)
            project = Path(temporary_directory) / "cli-demo"
            self.assertEqual(
                (project / "README.md").read_text(encoding="utf-8"),
                "# CAMILO OS\n\nProyecto generado por Camilo Builder.\n",
            )
            self.assertEqual(
                sorted(path.name for path in project.iterdir()),
                sorted((*ProjectBuilder.FOLDERS, "README.md")),
            )

    def test_create_agent_supports_custom_output(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            ProjectBuilder(Path(temporary_directory)).build("cli-demo")

            result = self.run_builder(
                "create-agent",
                "cli-demo",
                "assistant",
                "--output",
                temporary_directory,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("Agente creado:", result.stdout)
            self.assertTrue(
                (Path(temporary_directory) / "cli-demo" / "agents" / "assistant").is_dir()
            )

    def test_create_department_supports_custom_output(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            ProjectBuilder(Path(temporary_directory)).build("cli-demo")

            result = self.run_builder(
                "create-department",
                "cli-demo",
                "operations",
                "--output",
                temporary_directory,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("Departamento creado:", result.stdout)
            department = (
                Path(temporary_directory)
                / "cli-demo"
                / "departments"
                / "operations"
            )
            self.assertEqual(
                (department / "README.md").read_bytes(),
                b"# operations\n\nDepartamento de Camilo OS.\n",
            )
            self.assertEqual(
                sorted(path.name for path in department.iterdir()),
                ["README.md", "__init__.py"],
            )

    def test_create_department_supports_an_external_template(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            ProjectBuilder(root).build("cli-demo")
            template = root / "department-template"
            template.mkdir()
            (template / "department.txt").write_text(
                "Departamento: {{ component_name }}\n", encoding="utf-8"
            )

            result = self.run_builder(
                "create-department",
                "cli-demo",
                "operations",
                "--output",
                temporary_directory,
                "--template",
                str(template),
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("Departamento creado:", result.stdout)
            self.assertEqual(
                (
                    root
                    / "cli-demo"
                    / "departments"
                    / "operations"
                    / "department.txt"
                ).read_text(encoding="utf-8"),
                "Departamento: operations\n",
            )

    def test_create_department_supports_a_registered_template_name(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            ProjectBuilder(root).build("cli-demo")

            result = self.run_builder(
                "create-department",
                "cli-demo",
                "operations",
                "--output",
                temporary_directory,
                "--template",
                "default",
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("Departamento creado:", result.stdout)
            self.assertEqual(
                (
                    root
                    / "cli-demo"
                    / "departments"
                    / "operations"
                    / "README.md"
                ).read_bytes(),
                b"# operations\n\nDepartamento de Camilo OS.\n",
            )

    def test_create_department_reports_a_missing_external_template_path(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            ProjectBuilder(root).build("cli-demo")
            missing = root / "missing" / "department-template"

            result = self.run_builder(
                "create-department",
                "cli-demo",
                "operations",
                "--output",
                temporary_directory,
                "--template",
                str(missing),
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("No existe el directorio de plantilla", result.stderr)
            self.assertFalse(
                (root / "cli-demo" / "departments" / "operations").exists()
            )

    def test_create_service_supports_custom_output(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            ProjectBuilder(root).build("cli-demo")

            result = self.run_builder(
                "create-service",
                "cli-demo",
                "notifications",
                "--output",
                temporary_directory,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            service = root / "cli-demo" / "services" / "notifications"
            self.assertEqual(
                result.stdout, f"\nServicio creado:\n{service}\n\n"
            )
            self.assertEqual(
                sorted(path.name for path in service.iterdir()),
                ["README.md", "__init__.py"],
            )
            self.assertEqual(
                (service / "README.md").read_bytes(),
                b"# notifications\n\nServicio de Camilo OS.\n",
            )

    def test_create_service_supports_an_external_template(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            ProjectBuilder(root).build("cli-demo")
            template = root / "service-template"
            template.mkdir()
            (template / "service.txt").write_text(
                "Servicio: {{ component_name }}\n", encoding="utf-8"
            )

            result = self.run_builder(
                "create-service",
                "cli-demo",
                "notifications",
                "--output",
                temporary_directory,
                "--template",
                str(template),
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("Servicio creado:", result.stdout)
            self.assertEqual(
                (
                    root
                    / "cli-demo"
                    / "services"
                    / "notifications"
                    / "service.txt"
                ).read_text(encoding="utf-8"),
                "Servicio: notifications\n",
            )

    def test_create_service_supports_a_registered_template_name(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            ProjectBuilder(root).build("cli-demo")

            result = self.run_builder(
                "create-service",
                "cli-demo",
                "notifications",
                "--output",
                temporary_directory,
                "--template",
                "default",
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("Servicio creado:", result.stdout)

    def test_create_service_reports_a_missing_external_template_path(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            ProjectBuilder(root).build("cli-demo")
            missing = root / "missing" / "service-template"

            result = self.run_builder(
                "create-service",
                "cli-demo",
                "notifications",
                "--output",
                temporary_directory,
                "--template",
                str(missing),
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("No existe el directorio de plantilla", result.stderr)
            self.assertFalse(
                (root / "cli-demo" / "services" / "notifications").exists()
            )

    def test_create_component_reports_missing_project(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            result = self.run_builder(
                "create-agent", "missing", "assistant", "--output", temporary_directory
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("No existe el proyecto", result.stderr)

    def test_create_component_rejects_unsafe_project_name(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            result = self.run_builder(
                "create-agent", "../outside", "assistant", "--output", temporary_directory
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("El nombre debe empezar", result.stderr)
            self.assertFalse((Path(temporary_directory).parent / "outside").exists())

    def test_create_agent_supports_a_template(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            ProjectBuilder(root).build("cli-demo")
            template = root / "agent-template"
            template.mkdir()
            (template / "agent.txt").write_text(
                "Agente: {{ component_name }}\n", encoding="utf-8"
            )

            result = self.run_builder(
                "create-agent",
                "cli-demo",
                "assistant",
                "--output",
                temporary_directory,
                "--template",
                str(template),
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(
                (root / "cli-demo" / "agents" / "assistant" / "agent.txt").read_text(
                    encoding="utf-8"
                ),
                "Agente: assistant\n",
            )

    def test_create_agent_supports_a_registered_template_name(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            ProjectBuilder(root).build("cli-demo")

            result = self.run_builder(
                "create-agent",
                "cli-demo",
                "assistant",
                "--output",
                temporary_directory,
                "--template",
                "default",
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("Agente creado:", result.stdout)
            self.assertEqual(
                (root / "cli-demo" / "agents" / "assistant" / "README.md").read_text(
                    encoding="utf-8"
                ),
                "# assistant\n\nAgente de Camilo OS.\n",
            )

    def test_create_agent_reports_a_missing_external_template_path(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            ProjectBuilder(root).build("cli-demo")
            missing = root / "missing" / "agent-template"

            result = self.run_builder(
                "create-agent",
                "cli-demo",
                "assistant",
                "--output",
                temporary_directory,
                "--template",
                str(missing),
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("No existe el directorio de plantilla", result.stderr)
            self.assertFalse((root / "cli-demo" / "agents" / "assistant").exists())

    def test_list_agents_outputs_sorted_names(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            project = ProjectBuilder(Path(temporary_directory)).build("cli-demo")
            AgentBuilder(project).build("writer")
            AgentBuilder(project).build("analyst")

            result = self.run_builder(
                "list-agents", "cli-demo", "--output", temporary_directory
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout.splitlines(), ["analyst", "writer"])

    def test_list_departments_supports_an_empty_project(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            ProjectBuilder(Path(temporary_directory)).build("cli-demo")

            result = self.run_builder(
                "list-departments", "cli-demo", "--output", temporary_directory
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout, "")

    def test_list_services_outputs_sorted_names_and_ignores_hidden_directories(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            project = ProjectBuilder(Path(temporary_directory)).build("cli-demo")
            ServiceBuilder(project).build("worker")
            ServiceBuilder(project).build("api")
            (project / "services" / ".internal").mkdir()

            result = self.run_builder(
                "list-services", "cli-demo", "--output", temporary_directory
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout, "api\nworker\n")

    def test_list_services_supports_an_empty_project(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            ProjectBuilder(Path(temporary_directory)).build("cli-demo")

            result = self.run_builder(
                "list-services", "cli-demo", "--output", temporary_directory
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout, "")

    def test_list_services_reports_a_missing_project(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            result = self.run_builder(
                "list-services", "missing", "--output", temporary_directory
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(result.stdout, "")
            self.assertIn("No existe el proyecto", result.stderr)

    def test_inspect_department_outputs_json_details(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            project = ProjectBuilder(Path(temporary_directory)).build("cli-demo")
            department = DepartmentBuilder(project).build("operations")

            result = self.run_builder(
                "inspect-department",
                "cli-demo",
                "operations",
                "--output",
                temporary_directory,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            details = json.loads(result.stdout)
            self.assertEqual(details["name"], "operations")
            self.assertEqual(details["path"], str(department))
            self.assertEqual(details["files"], ["README.md", "__init__.py"])

    def test_inspect_service_outputs_stable_relative_json_details(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            project = ProjectBuilder(Path(temporary_directory)).build("cli-demo")
            service = ServiceBuilder(project).build("notifications")
            (service / "config").mkdir()
            (service / "config" / "settings.json").write_text(
                "{}\n", encoding="utf-8"
            )
            (service / "custom.txt").write_text("custom\n", encoding="utf-8")

            result = self.run_builder(
                "inspect-service",
                "cli-demo",
                "notifications",
                "--output",
                temporary_directory,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(
                result.stdout,
                '{\n'
                '  "name": "notifications",\n'
                '  "relative_path": "services/notifications",\n'
                '  "files": [\n'
                '    "README.md",\n'
                '    "__init__.py",\n'
                '    "config/settings.json",\n'
                '    "custom.txt"\n'
                '  ]\n'
                '}\n',
            )
            details = json.loads(result.stdout)
            self.assertNotIn("path", details)
            self.assertNotIn(str(Path(temporary_directory)), result.stdout)

    def test_inspect_service_reports_a_missing_service(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            ProjectBuilder(Path(temporary_directory)).build("cli-demo")

            result = self.run_builder(
                "inspect-service",
                "cli-demo",
                "missing",
                "--output",
                temporary_directory,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(result.stdout, "")
            self.assertIn("No existe el servicio", result.stderr)

    def test_inspect_agent_reports_a_missing_component(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            ProjectBuilder(Path(temporary_directory)).build("cli-demo")

            result = self.run_builder(
                "inspect-agent",
                "cli-demo",
                "missing",
                "--output",
                temporary_directory,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("No existe el agente", result.stderr)

    def test_list_templates_outputs_stable_json(self):
        result = self.run_builder("list-templates")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            json.loads(result.stdout),
            [
                {
                    "name": "camilo-os-agent",
                    "type": "agent",
                    "version": 1,
                    "description": "Agente operativo de Camilo OS para el piloto sintético invoice-intake.",
                    "required_variables": ["component_name"],
                },
                {
                    "name": "default",
                    "type": "agent",
                    "version": 1,
                    "description": "Plantilla predeterminada de agente.",
                    "required_variables": ["component_name"],
                },
                {
                    "name": "default",
                    "type": "department",
                    "version": 1,
                    "description": "Plantilla predeterminada de departamento.",
                    "required_variables": ["component_name"],
                },
                {
                    "name": "default",
                    "type": "project",
                    "version": 1,
                    "description": "Plantilla predeterminada de proyecto.",
                    "required_variables": ["project_name"],
                },
                {
                    "name": "agent-core",
                    "type": "service",
                    "version": 1,
                    "description": "Núcleo local, determinista y sin conectores externos para agentes de Camilo OS.",
                    "required_variables": ["component_name"],
                },
                {
                    "name": "default",
                    "type": "service",
                    "version": 1,
                    "description": "Plantilla predeterminada de servicio.",
                    "required_variables": ["component_name"],
                },
                {
                    "name": "google-connectors",
                    "type": "service",
                    "version": 1,
                    "description": "Conectores Google read-only, neutrales y configurados externamente para Camilo OS.",
                    "required_variables": ["component_name"],
                },
            ],
        )

    def test_list_templates_filters_by_component_type(self):
        result = self.run_builder("list-templates", "--type", "agent")

        self.assertEqual(result.returncode, 0, result.stderr)
        templates = json.loads(result.stdout)
        self.assertEqual([item["name"] for item in templates], ["camilo-os-agent", "default"])
        self.assertTrue(all(item["type"] == "agent" for item in templates))

    def test_service_template_integrates_with_management_commands(self):
        list_result = self.run_builder("list-templates", "--type", "service")
        inspect_result = self.run_builder(
            "inspect-template", "default", "--type", "service"
        )
        validate_result = self.run_builder(
            "validate-template", "default", "--type", "service"
        )

        for result in (list_result, inspect_result, validate_result):
            self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(list_result.stdout)[0]["type"], "service")
        self.assertEqual(json.loads(inspect_result.stdout)["type"], "service")
        self.assertEqual(
            json.loads(validate_result.stdout),
            {
                "valid": True,
                "name": "default",
                "type": "service",
                "version": 1,
                "description": "Plantilla predeterminada de servicio.",
                "required_variables": ["component_name"],
                "files": 2,
            },
        )

    def test_inspect_template_outputs_stable_json(self):
        result = self.run_builder(
            "inspect-template", "default", "--type", "department"
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            result.stdout,
            '{\n'
            '  "name": "default",\n'
            '  "type": "department",\n'
            '  "version": 1,\n'
            '  "description": "Plantilla predeterminada de departamento.",\n'
            '  "required_variables": [\n'
            '    "component_name"\n'
            '  ]\n'
            '}\n',
        )
        self.assertEqual(
            json.loads(result.stdout),
            {
                "name": "default",
                "type": "department",
                "version": 1,
                "description": "Plantilla predeterminada de departamento.",
                "required_variables": ["component_name"],
            },
        )

    def test_validate_template_validates_a_registered_template(self):
        result = self.run_builder(
            "validate-template", "default", "--type", "agent"
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            json.loads(result.stdout),
            {
                "valid": True,
                "name": "default",
                "type": "agent",
                "version": 1,
                "description": "Plantilla predeterminada de agente.",
                "required_variables": ["component_name"],
                "files": 2,
            },
        )

    def test_validate_template_validates_legacy_path_without_writing(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            template = Path(temporary_directory) / "legacy"
            template.mkdir()
            (template / "README.md").write_text(
                "{{ component_name }}\n", encoding="utf-8"
            )
            before = sorted(
                path.relative_to(temporary_directory)
                for path in Path(temporary_directory).rglob("*")
            )

            result = self.run_builder(
                "validate-template", str(template), "--type", "agent"
            )

            after = sorted(
                path.relative_to(temporary_directory)
                for path in Path(temporary_directory).rglob("*")
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(json.loads(result.stdout)["valid"])
            self.assertEqual(after, before)

    def test_validate_template_reports_errors_on_stderr(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            missing = Path(temporary_directory) / "missing" / "template"

            result = self.run_builder(
                "validate-template", str(missing), "--type", "agent"
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(result.stdout, "")
            self.assertIn("No existe el directorio de plantilla", result.stderr)


if __name__ == "__main__":
    unittest.main()
