import re
import shutil
from pathlib import Path


COMPONENT_NAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


class InvalidComponentName(ValueError):
    """Raised when a component name could escape or corrupt its project."""


class ProjectNotFound(FileNotFoundError):
    """Raised when a component is added to a project that does not exist."""


class InvalidTemplate(ValueError):
    """Raised when a component template cannot be used safely."""


class ComponentBuilder:
    component_folder = ""
    component_label = "Componente"

    def __init__(self, project_dir: Path, template_dir: Path | None = None):
        self.project_dir = Path(project_dir)
        self.template_dir = Path(template_dir) if template_dir is not None else None

    def build(self, component_name: str) -> Path:
        self._validate_component_name(component_name)
        self._validate_project()
        self._validate_template()

        component = self.project_dir / self.component_folder / component_name
        component.mkdir(parents=True, exist_ok=True)
        (component / "__init__.py").touch(exist_ok=True)

        if self.template_dir is None:
            self._write_default_readme(component, component_name)
        else:
            self._apply_template(component, component_name)

        return component

    def _write_default_readme(self, component: Path, component_name: str) -> None:
        readme = component / "README.md"
        if not readme.exists():
            readme.write_text(
                f"# {component_name}\n\n{self.component_label} de Camilo OS.\n",
                encoding="utf-8",
            )

    def _apply_template(self, component: Path, component_name: str) -> None:
        for source in self.template_dir.rglob("*"):
            relative_path = source.relative_to(self.template_dir)
            destination = component / relative_path
            if source.is_dir():
                destination.mkdir(parents=True, exist_ok=True)
                continue

            destination.parent.mkdir(parents=True, exist_ok=True)
            if destination.exists():
                continue

            try:
                content = source.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                shutil.copyfile(source, destination)
            else:
                destination.write_text(
                    content.replace("{{ component_name }}", component_name).replace(
                        "{{ component_type }}", self.component_label.lower()
                    ),
                    encoding="utf-8",
                )

    def _validate_template(self) -> None:
        if self.template_dir is None:
            return
        if not self.template_dir.is_dir():
            raise InvalidTemplate(
                f"No existe el directorio de plantilla: {self.template_dir}"
            )
        if any(path.is_symlink() for path in self.template_dir.rglob("*")):
            raise InvalidTemplate("La plantilla no puede contener enlaces simbólicos.")

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
