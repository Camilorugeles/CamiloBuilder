import os
from dataclasses import dataclass
from pathlib import Path

from template_system.errors import TemplateNotFound
from template_system.manifest import TemplateManifest
from template_system.registry import TemplateRegistry


@dataclass(frozen=True)
class ResolvedTemplate:
    files_dir: Path
    manifest: TemplateManifest
    registered: bool


class TemplateResolver:
    def __init__(self, registry: TemplateRegistry):
        self.registry = registry

    def resolve(
        self,
        component_type: str,
        selection: str | Path | None = None,
    ) -> ResolvedTemplate:
        if selection is None:
            return self._resolve_registered(component_type, "default")

        raw_selection = str(selection)
        external_path = Path(selection).expanduser()
        if external_path.exists():
            if not external_path.is_dir():
                raise TemplateNotFound(
                    f"La ruta de plantilla no es un directorio: {external_path}"
                )
            return ResolvedTemplate(
                files_dir=external_path,
                manifest=TemplateManifest(
                    schema_version=1,
                    component_type=component_type,
                    name="external",
                    required_variables=("component_name",),
                ),
                registered=False,
            )

        try:
            return self._resolve_registered(component_type, raw_selection)
        except TemplateNotFound as error:
            if self._looks_like_path(raw_selection):
                raise TemplateNotFound(
                    f"No existe el directorio de plantilla: {external_path}"
                ) from error
            raise

    def _resolve_registered(
        self, component_type: str, template_name: str
    ) -> ResolvedTemplate:
        template_dir, manifest = self.registry.resolve(component_type, template_name)
        return ResolvedTemplate(
            files_dir=template_dir / "files",
            manifest=manifest,
            registered=True,
        )

    @staticmethod
    def _looks_like_path(value: str) -> bool:
        separators = {os.sep}
        if os.altsep:
            separators.add(os.altsep)
        return (
            value.startswith((".", "~"))
            or Path(value).is_absolute()
            or any(separator in value for separator in separators)
        )
