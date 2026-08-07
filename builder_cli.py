import argparse
import json
from pathlib import Path

from builders.agent_builder import AgentBuilder
from builders.component_builder import (
    InvalidComponentName,
    InvalidTemplate,
    ProjectNotFound,
)
from builders.component_catalog import ComponentCatalog, ComponentNotFound
from builders.department_builder import DepartmentBuilder
from builders.project_builder import InvalidProjectName, ProjectBuilder
from builders.service_builder import ServiceBuilder
from template_system.errors import TemplateError
from template_system.manifest import TemplateManifest
from template_system.registry import TemplateRegistry
from template_system.renderer import TemplateRenderer
from template_system.validation import validate_template as validate_template_source


ROOT = Path(__file__).resolve().parent
TEMPLATES = ROOT / "templates"


def status() -> None:
    print("=" * 60)
    print("CAMILO BUILDER")
    print("=" * 60)
    print("Estado: Operativo")


def create_project(name: str, output: Path | None = None) -> Path:
    output = output or ROOT / "output"
    project = ProjectBuilder(output).build(name)
    print()
    print("Proyecto creado:")
    print(project)
    print()
    return project


def create_component(
    builder_class: type[AgentBuilder] | type[DepartmentBuilder] | type[ServiceBuilder],
    project_name: str,
    component_name: str,
    output: Path | None = None,
    template: str | Path | None = None,
) -> Path:
    output = output or ROOT / "output"
    ProjectBuilder._validate_project_name(project_name)
    component = builder_class(output / project_name, template).build(component_name)
    print()
    print(f"{builder_class.component_label} creado:")
    print(component)
    print()
    return component


def get_catalog(
    builder_class: type[AgentBuilder] | type[DepartmentBuilder] | type[ServiceBuilder],
    project_name: str,
    output: Path | None = None,
) -> ComponentCatalog:
    output = output or ROOT / "output"
    ProjectBuilder._validate_project_name(project_name)
    return ComponentCatalog(
        output / project_name,
        builder_class.component_folder,
        builder_class.component_label,
    )


def list_components(
    builder_class: type[AgentBuilder] | type[DepartmentBuilder] | type[ServiceBuilder],
    project_name: str,
    output: Path | None = None,
) -> list[str]:
    names = get_catalog(builder_class, project_name, output).list_names()
    for name in names:
        print(name)
    return names


def inspect_component(
    builder_class: type[AgentBuilder] | type[DepartmentBuilder],
    project_name: str,
    component_name: str,
    output: Path | None = None,
) -> dict[str, object]:
    details = get_catalog(builder_class, project_name, output).inspect(component_name)
    print(json.dumps(details, ensure_ascii=False, indent=2))
    return details


def inspect_service(
    project_name: str,
    service_name: str,
    output: Path | None = None,
) -> dict[str, object]:
    catalog = get_catalog(ServiceBuilder, project_name, output)
    catalog_details = catalog.inspect(service_name)
    details = {
        "name": catalog_details["name"],
        "relative_path": str(Path(catalog.component_folder) / service_name),
        "files": catalog_details["files"],
    }
    print(json.dumps(details, ensure_ascii=False, indent=2))
    return details


def template_details(manifest: TemplateManifest) -> dict[str, object]:
    return {
        "name": manifest.name,
        "type": manifest.component_type,
        "version": manifest.schema_version,
        "description": manifest.description,
        "required_variables": list(manifest.required_variables),
    }


def list_templates(component_type: str | None = None) -> list[dict[str, object]]:
    templates = [
        template_details(manifest)
        for _path, manifest in TemplateRegistry(TEMPLATES).list(component_type)
    ]
    print(json.dumps(templates, ensure_ascii=False, indent=2))
    return templates


def inspect_template(template_name: str, component_type: str) -> dict[str, object]:
    _path, manifest = TemplateRegistry(TEMPLATES).resolve(
        component_type, template_name
    )
    details = template_details(manifest)
    print(json.dumps(details, ensure_ascii=False, indent=2))
    return details


def validate_template(template: str, component_type: str) -> dict[str, object]:
    manifest, file_count = validate_template_source(
        TemplateRegistry(TEMPLATES),
        TemplateRenderer(),
        component_type,
        template,
    )
    details = {
        "valid": True,
        **template_details(manifest),
        "files": file_count,
    }
    print(json.dumps(details, ensure_ascii=False, indent=2))
    return details


def _handle_status(_args, _parser) -> None:
    status()


def _handle_create_project(args, parser) -> None:
    try:
        create_project(args.name, args.output)
    except InvalidProjectName as error:
        parser.error(str(error))


def _handle_create_component(args, parser) -> None:
    try:
        create_component(
            args.builder,
            args.project,
            args.name,
            args.output,
            args.template,
        )
    except (
        InvalidComponentName,
        InvalidProjectName,
        InvalidTemplate,
        ProjectNotFound,
        TemplateError,
    ) as error:
        parser.error(str(error))


def _handle_list_component(args, parser) -> None:
    try:
        list_components(args.builder, args.project, args.output)
    except (InvalidProjectName, ProjectNotFound) as error:
        parser.error(str(error))


def _handle_inspect_component(args, parser) -> None:
    try:
        inspect_component(args.builder, args.project, args.name, args.output)
    except (ComponentNotFound, InvalidProjectName, ProjectNotFound) as error:
        parser.error(str(error))


def _handle_inspect_service(args, parser) -> None:
    try:
        inspect_service(args.project, args.name, args.output)
    except (ComponentNotFound, InvalidProjectName, ProjectNotFound) as error:
        parser.error(str(error))


def _handle_list_templates(args, parser) -> None:
    try:
        list_templates(args.component_type)
    except TemplateError as error:
        parser.error(str(error))


def _handle_inspect_template(args, parser) -> None:
    try:
        inspect_template(args.name, args.component_type)
    except TemplateError as error:
        parser.error(str(error))


def _handle_validate_template(args, parser) -> None:
    try:
        validate_template(args.template, args.component_type)
    except (OSError, TemplateError) as error:
        parser.error(str(error))


def _configure_status(_parser) -> None:
    pass


def _configure_create_project(parser) -> None:
    parser.add_argument("name")
    parser.add_argument(
        "--output",
        type=Path,
        help="Directorio donde se creará el proyecto (por defecto: ./output)",
    )


def _configure_create_component(parser) -> None:
    parser.add_argument("project", help="Nombre del proyecto")
    parser.add_argument("name", help="Nombre del componente")
    parser.add_argument(
        "--output",
        type=Path,
        help="Directorio que contiene el proyecto (por defecto: ./output)",
    )
    parser.add_argument(
        "--template", help="Directorio de plantilla para inicializar el componente"
    )


def _configure_list_component(parser) -> None:
    parser.add_argument("project", help="Nombre del proyecto")
    parser.add_argument(
        "--output",
        type=Path,
        help="Directorio que contiene el proyecto (por defecto: ./output)",
    )


def _configure_inspect_component(parser) -> None:
    parser.add_argument("project", help="Nombre del proyecto")
    parser.add_argument("name", help="Nombre del componente")
    parser.add_argument(
        "--output",
        type=Path,
        help="Directorio que contiene el proyecto (por defecto: ./output)",
    )


def _configure_list_templates(parser) -> None:
    parser.add_argument(
        "--type", dest="component_type", help="Filtra por tipo de componente"
    )


def _configure_inspect_template(parser) -> None:
    parser.add_argument("name", help="Nombre de la plantilla")
    parser.add_argument(
        "--type",
        dest="component_type",
        required=True,
        help="Tipo de componente",
    )


def _configure_validate_template(parser) -> None:
    parser.add_argument("template", help="Nombre registrado o ruta de plantilla")
    parser.add_argument(
        "--type",
        dest="component_type",
        required=True,
        help="Tipo de componente",
    )


COMPONENT_COMMANDS = (
    {
        "builder": AgentBuilder,
        "create": {
            "name": "create-agent",
            "description": "Crea un agente dentro de un proyecto",
            "handler": _handle_create_component,
            "builder": AgentBuilder,
            "configure": _configure_create_component,
        },
        "list": {
            "name": "list-agents",
            "description": "Lista los agentes de un proyecto",
            "handler": _handle_list_component,
            "builder": AgentBuilder,
            "configure": _configure_list_component,
        },
        "inspect": {
            "name": "inspect-agent",
            "description": "Muestra los detalles de un agente",
            "handler": _handle_inspect_component,
            "builder": AgentBuilder,
            "configure": _configure_inspect_component,
        },
    },
    {
        "builder": DepartmentBuilder,
        "create": {
            "name": "create-department",
            "description": "Crea un departamento dentro de un proyecto",
            "handler": _handle_create_component,
            "builder": DepartmentBuilder,
            "configure": _configure_create_component,
        },
        "list": {
            "name": "list-departments",
            "description": "Lista los departamentos de un proyecto",
            "handler": _handle_list_component,
            "builder": DepartmentBuilder,
            "configure": _configure_list_component,
        },
        "inspect": {
            "name": "inspect-department",
            "description": "Muestra los detalles de un departamento",
            "handler": _handle_inspect_component,
            "builder": DepartmentBuilder,
            "configure": _configure_inspect_component,
        },
    },
    {
        "builder": ServiceBuilder,
        "create": {
            "name": "create-service",
            "description": "Crea un servicio dentro de un proyecto",
            "handler": _handle_create_component,
            "builder": ServiceBuilder,
            "configure": _configure_create_component,
        },
        "list": {
            "name": "list-services",
            "description": "Lista los servicios de un proyecto",
            "handler": _handle_list_component,
            "builder": ServiceBuilder,
            "configure": _configure_list_component,
        },
        "inspect": {
            "name": "inspect-service",
            "description": "Muestra los detalles de un servicio",
            "handler": _handle_inspect_service,
            "builder": ServiceBuilder,
            "configure": _configure_inspect_component,
        },
    },
)


BUILDER_METADATA = (
    {"builder": ProjectBuilder, "component_type": "project"},
    *(
        {
            "builder": component["builder"],
            "component_type": component["builder"].component_type,
        }
        for component in COMPONENT_COMMANDS
    ),
)


COMMANDS = (
    {
        "name": "status",
        "description": None,
        "handler": _handle_status,
        "builder": None,
        "configure": _configure_status,
    },
    {
        "name": "create-project",
        "description": None,
        "handler": _handle_create_project,
        "builder": None,
        "configure": _configure_create_project,
    },
    *(component["create"] for component in COMPONENT_COMMANDS),
    *(component["list"] for component in COMPONENT_COMMANDS),
    *(component["inspect"] for component in COMPONENT_COMMANDS),
    {
        "name": "list-templates",
        "description": "Lista las plantillas registradas",
        "handler": _handle_list_templates,
        "builder": None,
        "configure": _configure_list_templates,
    },
    {
        "name": "inspect-template",
        "description": "Muestra los metadatos de una plantilla registrada",
        "handler": _handle_inspect_template,
        "builder": None,
        "configure": _configure_inspect_template,
    },
    {
        "name": "validate-template",
        "description": "Valida una plantilla sin generar archivos",
        "handler": _handle_validate_template,
        "builder": None,
        "configure": _configure_validate_template,
    },
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="builder", description="Constructor de Camilo OS")
    subparsers = parser.add_subparsers(dest="cmd")
    for command in COMMANDS:
        parser_options = {}
        if command["description"] is not None:
            parser_options["help"] = command["description"]
        command_parser = subparsers.add_parser(command["name"], **parser_options)
        command["configure"](command_parser)
        command_parser.set_defaults(
            handler=command["handler"], builder=command["builder"]
        )
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    if hasattr(args, "handler"):
        args.handler(args, parser)
    else:
        parser.print_help()
