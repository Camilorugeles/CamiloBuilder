import re
from pathlib import Path

from template_system.errors import TemplateRenderError
from template_system.manifest import TemplateManifest


VARIABLE_PATTERN = re.compile(r"{{\s*([A-Za-z_][A-Za-z0-9_]*)\s*}}")


class TemplateRenderer:
    VALIDATION_DESTINATION = Path("/__camilo_builder_template_validation__")

    def render(
        self,
        template_dir: Path,
        destination: Path,
        manifest: TemplateManifest,
        variables: dict[str, str],
    ) -> Path:
        template_dir = Path(template_dir)
        if template_dir.is_symlink():
            raise TemplateRenderError("La plantilla no puede contener enlaces simbólicos.")
        return self.render_files(
            template_dir / "files", destination, manifest, variables
        )

    def render_files(
        self,
        files_dir: Path,
        destination: Path,
        manifest: TemplateManifest,
        variables: dict[str, str],
    ) -> Path:
        files_dir = Path(files_dir)
        destination = Path(destination)
        self._validate_variables(manifest, variables)
        operations = self._plan(files_dir, destination, variables)

        destination.mkdir(parents=True, exist_ok=True)
        for source_is_dir, target, content in operations:
            if target.exists():
                if source_is_dir != target.is_dir():
                    raise TemplateRenderError(f"Conflicto de tipo en el destino: {target}")
                continue
            if source_is_dir:
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(content)
        return destination

    def validate(
        self,
        template_dir: Path,
        manifest: TemplateManifest,
        variables: dict[str, str],
    ) -> int:
        template_dir = Path(template_dir)
        if template_dir.is_symlink():
            raise TemplateRenderError("La plantilla no puede contener enlaces simbólicos.")
        return self.validate_files(template_dir / "files", manifest, variables)

    def validate_files(
        self,
        files_dir: Path,
        manifest: TemplateManifest,
        variables: dict[str, str],
    ) -> int:
        self._validate_variables(manifest, variables)
        operations = self._plan(
            Path(files_dir), self.VALIDATION_DESTINATION, variables
        )
        return sum(not source_is_dir for source_is_dir, _target, _content in operations)

    def _plan(
        self, files_dir: Path, destination: Path, variables: dict[str, str]
    ) -> list[tuple[bool, Path, bytes | None]]:
        if files_dir.is_symlink():
            raise TemplateRenderError("La plantilla no puede contener enlaces simbólicos.")
        if not files_dir.is_dir():
            raise TemplateRenderError(f"No existe el directorio de archivos: {files_dir}")

        destination_root = destination.resolve(strict=False)
        operations = []
        for source in sorted(files_dir.rglob("*")):
            if source.is_symlink():
                raise TemplateRenderError(
                    "La plantilla no puede contener enlaces simbólicos."
                )
            relative_path = source.relative_to(files_dir)
            if relative_path.is_absolute() or ".." in relative_path.parts:
                raise TemplateRenderError(f"Ruta de plantilla no válida: {relative_path}")
            target = destination / relative_path
            if not target.resolve(strict=False).is_relative_to(destination_root):
                raise TemplateRenderError(f"La ruta escapa del destino: {relative_path}")

            if source.is_dir():
                operations.append((True, target, None))
                continue
            if not source.is_file():
                raise TemplateRenderError(f"Entrada de plantilla no válida: {source}")

            raw_content = source.read_bytes()
            try:
                text_content = raw_content.decode("utf-8")
            except UnicodeDecodeError:
                rendered_content = raw_content
            else:
                unknown = set(VARIABLE_PATTERN.findall(text_content)) - variables.keys()
                if unknown:
                    names = ", ".join(sorted(unknown))
                    raise TemplateRenderError(f"Variables sin valor: {names}")
                for name, value in variables.items():
                    text_content = re.sub(
                        r"{{\s*" + re.escape(name) + r"\s*}}",
                        lambda _match, replacement=value: replacement,
                        text_content,
                    )
                rendered_content = text_content.encode("utf-8")
            operations.append((False, target, rendered_content))
        return operations

    @staticmethod
    def _validate_variables(
        manifest: TemplateManifest, variables: dict[str, str]
    ) -> None:
        if not isinstance(variables, dict) or any(
            not isinstance(name, str) or not isinstance(value, str)
            for name, value in variables.items()
        ):
            raise TemplateRenderError("Las variables deben ser un diccionario de cadenas.")
        missing = set(manifest.required_variables) - variables.keys()
        if missing:
            names = ", ".join(sorted(missing))
            raise TemplateRenderError(f"Faltan variables requeridas: {names}")
