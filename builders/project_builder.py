import re
from pathlib import Path


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

    def __init__(self, output_dir: Path):
        self.output_dir = Path(output_dir)

    def build(self, project_name: str) -> Path:
        self._validate_project_name(project_name)

        project = self.output_dir / project_name
        project.mkdir(parents=True, exist_ok=True)

        for folder_name in self.FOLDERS:
            folder = project / folder_name
            folder.mkdir(exist_ok=True)
            (folder / "__init__.py").touch(exist_ok=True)

        (project / "README.md").write_text(
            "# CAMILO OS\n\nProyecto generado por Camilo Builder.\n",
            encoding="utf-8",
        )

        return project

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
