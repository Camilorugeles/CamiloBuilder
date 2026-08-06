import re
from pathlib import Path


COMPONENT_NAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


class InvalidComponentName(ValueError):
    """Raised when a component name could escape or corrupt its project."""


class ProjectNotFound(FileNotFoundError):
    """Raised when a component is added to a project that does not exist."""


class ComponentBuilder:
    component_folder = ""
    component_label = "Componente"

    def __init__(self, project_dir: Path):
        self.project_dir = Path(project_dir)

    def build(self, component_name: str) -> Path:
        self._validate_component_name(component_name)
        self._validate_project()

        component = self.project_dir / self.component_folder / component_name
        component.mkdir(parents=True, exist_ok=True)
        (component / "__init__.py").touch(exist_ok=True)

        readme = component / "README.md"
        if not readme.exists():
            readme.write_text(
                f"# {component_name}\n\n{self.component_label} de Camilo OS.\n",
                encoding="utf-8",
            )

        return component

    def _validate_project(self) -> None:
        if not self.project_dir.is_dir():
            raise ProjectNotFound(
                f"No existe el proyecto: {self.project_dir}"
            )

        target_folder = self.project_dir / self.component_folder
        if not target_folder.is_dir():
            raise ProjectNotFound(
                f"La ruta no es un proyecto de Camilo OS: {self.project_dir}"
            )

    @staticmethod
    def _validate_component_name(component_name: str) -> None:
        if (
            not isinstance(component_name, str)
            or component_name in {".", ".."}
            or not COMPONENT_NAME_PATTERN.fullmatch(component_name)
        ):
            raise InvalidComponentName(
                "El nombre debe empezar por una letra o número y solo puede "
                "contener letras, números, puntos, guiones y guiones bajos."
            )
