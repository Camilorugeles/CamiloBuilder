import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from builders.agent_builder import AgentBuilder
from builders.component_builder import (
    InvalidComponentName,
    InvalidTemplate,
    ProjectNotFound,
)
from builders.department_builder import DepartmentBuilder
from builders.project_builder import InvalidProjectName, ProjectBuilder


ROOT = Path(__file__).resolve().parents[1]


class ProjectBuilderTests(unittest.TestCase):
    def test_build_creates_expected_structure(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            project = ProjectBuilder(Path(temporary_directory)).build("demo-project")

            self.assertEqual(project.name, "demo-project")
            self.assertTrue((project / "README.md").is_file())
            for folder_name in ProjectBuilder.FOLDERS:
                self.assertTrue((project / folder_name / "__init__.py").is_file())

    def test_build_is_idempotent(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            builder = ProjectBuilder(Path(temporary_directory))
            first = builder.build("demo")
            second = builder.build("demo")

            self.assertEqual(first, second)

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

    def test_department_builder_creates_expected_structure(self):
        department = DepartmentBuilder(self.project).build("operations")

        self.assertEqual(department, self.project / "departments" / "operations")
        self.assertTrue((department / "__init__.py").is_file())
        self.assertTrue((department / "README.md").is_file())

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

    def test_create_project_supports_custom_output(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            result = self.run_builder(
                "create-project", "cli-demo", "--output", temporary_directory
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("Proyecto creado:", result.stdout)
            self.assertTrue((Path(temporary_directory) / "cli-demo" / "README.md").is_file())

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
            self.assertTrue(
                (
                    Path(temporary_directory)
                    / "cli-demo"
                    / "departments"
                    / "operations"
                ).is_dir()
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


if __name__ == "__main__":
    unittest.main()
