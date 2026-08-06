import re
from pathlib import Path

from template_system.errors import InvalidTemplateManifest, TemplateNotFound
from template_system.manifest import TemplateManifest


TEMPLATE_KEY_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")


class TemplateRegistry:
    def __init__(self, templates_dir: Path):
        self.templates_dir = Path(templates_dir)

    def resolve(
        self, component_type: str, template_name: str = "default"
    ) -> tuple[Path, TemplateManifest]:
        self._validate_key(component_type, "tipo")
        self._validate_key(template_name, "nombre")

        template_dir = self.templates_dir / component_type / template_name
        if template_dir.is_symlink():
            raise TemplateNotFound("La plantilla no puede ser un enlace simbólico.")
        if not template_dir.is_dir():
            raise TemplateNotFound(f"No existe la plantilla: {component_type}/{template_name}")
        if not template_dir.resolve().is_relative_to(self.templates_dir.resolve()):
            raise TemplateNotFound("La plantilla no puede escapar del registro.")

        manifest = TemplateManifest.load(template_dir / "template.json")
        if manifest.component_type != component_type or manifest.name != template_name:
            raise InvalidTemplateManifest(
                "El tipo y el nombre del manifiesto deben coincidir con su ubicación."
            )
        return template_dir, manifest

    @staticmethod
    def _validate_key(value: str, label: str) -> None:
        if not isinstance(value, str) or not TEMPLATE_KEY_PATTERN.fullmatch(value):
            raise TemplateNotFound(f"El {label} de plantilla no es válido: {value!r}")
