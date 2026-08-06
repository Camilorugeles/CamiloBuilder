import json
import re
from dataclasses import dataclass
from pathlib import Path

from template_system.errors import InvalidTemplateManifest


MANIFEST_KEY_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")
VARIABLE_NAME_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


@dataclass(frozen=True)
class TemplateManifest:
    schema_version: int
    component_type: str
    name: str
    required_variables: tuple[str, ...]

    @classmethod
    def load(cls, path: Path) -> "TemplateManifest":
        path = Path(path)
        if path.is_symlink():
            raise InvalidTemplateManifest("El manifiesto no puede ser un enlace simbólico.")
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError as error:
            raise InvalidTemplateManifest(f"No existe el manifiesto: {path}") from error
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise InvalidTemplateManifest(f"El manifiesto no es JSON válido: {path}") from error

        if not isinstance(data, dict):
            raise InvalidTemplateManifest("El manifiesto debe contener un objeto JSON.")
        if type(data.get("schema_version")) is not int or data["schema_version"] != 1:
            raise InvalidTemplateManifest("La versión de esquema debe ser 1.")

        component_type = data.get("component_type")
        name = data.get("name")
        required_variables = data.get("required_variables")
        if not isinstance(component_type, str) or not MANIFEST_KEY_PATTERN.fullmatch(
            component_type
        ):
            raise InvalidTemplateManifest("component_type no es un identificador válido.")
        if not isinstance(name, str) or not MANIFEST_KEY_PATTERN.fullmatch(name):
            raise InvalidTemplateManifest("name no es un identificador válido.")
        if not isinstance(required_variables, list) or any(
            not isinstance(variable, str)
            or not VARIABLE_NAME_PATTERN.fullmatch(variable)
            for variable in required_variables
        ):
            raise InvalidTemplateManifest(
                "required_variables debe contener identificadores válidos."
            )
        if len(required_variables) != len(set(required_variables)):
            raise InvalidTemplateManifest("required_variables contiene valores repetidos.")

        return cls(
            schema_version=1,
            component_type=component_type,
            name=name,
            required_variables=tuple(required_variables),
        )
