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


def validate_template(
    registry: TemplateRegistry,
    renderer: TemplateRenderer,
    component_type: str,
    selection: str | Path,
) -> tuple[TemplateManifest, int]:
    selected_path = Path(selection).expanduser()
    if selected_path.exists():
        if selected_path.is_symlink():
            raise TemplateRenderError(
                "La plantilla no puede contener enlaces simbólicos."
            )
        if not selected_path.is_dir():
            raise TemplateNotFound(
                f"La ruta de plantilla no es un directorio: {selected_path}"
            )
        manifest_path = selected_path / "template.json"
        if manifest_path.exists() or manifest_path.is_symlink():
            manifest = TemplateManifest.load(manifest_path)
            if manifest.component_type != component_type:
                raise InvalidTemplateManifest(
                    "El tipo del manifiesto no coincide con --type."
                )
            files_dir = selected_path / "files"
        else:
            manifest = TemplateManifest(
                schema_version=1,
                component_type=component_type,
                name=selected_path.name or "external",
                required_variables=("component_name",),
                description="Plantilla externa heredada.",
            )
            files_dir = selected_path
    else:
        resolved = TemplateResolver(registry).resolve(component_type, selection)
        manifest = resolved.manifest
        files_dir = resolved.files_dir

    variables = {
        variable: f"validation_{variable}"
        for variable in manifest.required_variables
    }
    variables.setdefault("component_name", "validation_component")
    variables.setdefault("component_type", component_type)
    file_count = renderer.validate_files(files_dir, manifest, variables)
    return manifest, file_count
