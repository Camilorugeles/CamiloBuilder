import re
from pathlib import Path

from template_system.registry import TemplateRegistry
from template_system.renderer import TemplateRenderer


PROJECT_NAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


class InvalidProjectName(ValueError):
    """Raised when a project name could escape or corrupt the output folder."""


class ProjectBuilder:

    FOLDERS = (
        "agents",
        "kernel",
        "departments",
        "services",
        "config",
        "docs",
        "logs",
        "tests",
    )

    def __init__(
        self,
        output_dir: Path,
        templates_dir: Path | None = None,
        renderer: TemplateRenderer | None = None,
    ):
        self.output_dir = Path(output_dir)
        self.templates_dir = templates_dir or Path(__file__).resolve().parents[1] / "templates"
        self.registry = TemplateRegistry(self.templates_dir)
        self.renderer = renderer or TemplateRenderer()

    def build(self, project_name: str) -> Path:
        self._validate_project_name(project_name)

        project = self.output_dir / project_name
        template_dir, manifest = self.registry.resolve("project")
        return self.renderer.render(
            template_dir,
            project,
            manifest,
            {"project_name": project_name},
        )

    @staticmethod
    def _validate_project_name(project_name: str) -> None:
        if (
            not isinstance(project_name, str)
            or project_name in {".", ".."}
            or not PROJECT_NAME_PATTERN.fullmatch(project_name)
        ):
            raise InvalidProjectName(
                "El nombre debe empezar por una letra o número y solo puede "
                "contener letras, números, puntos, guiones y guiones bajos."
            )
