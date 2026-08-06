from pathlib import Path

from builders.component_builder import ProjectNotFound


class ComponentNotFound(FileNotFoundError):
    """Raised when a requested project component does not exist."""


class ComponentCatalog:
    def __init__(self, project_dir: Path, component_folder: str, component_label: str):
        self.project_dir = Path(project_dir)
        self.component_folder = component_folder
        self.component_label = component_label

    @property
    def components_dir(self) -> Path:
        return self.project_dir / self.component_folder

    def list_names(self) -> list[str]:
        self._validate_project()
        return sorted(
            path.name
            for path in self.components_dir.iterdir()
            if path.is_dir() and not path.name.startswith(".")
        )

    def inspect(self, component_name: str) -> dict[str, object]:
        self._validate_project()
        component = self.components_dir / component_name
        if not component.is_dir() or component.name != component_name:
            raise ComponentNotFound(
                f"No existe el {self.component_label.lower()}: {component_name}"
            )

        files = sorted(
            str(path.relative_to(component))
            for path in component.rglob("*")
            if path.is_file()
        )
        return {
            "name": component_name,
            "type": self.component_label.lower(),
            "path": str(component),
            "files": files,
        }

    def _validate_project(self) -> None:
        if not self.project_dir.is_dir():
            raise ProjectNotFound(f"No existe el proyecto: {self.project_dir}")
        if not self.components_dir.is_dir():
            raise ProjectNotFound(
                f"La ruta no es un proyecto de Camilo OS: {self.project_dir}"
            )
