"""
CAMILO BUILDER
"""

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

    builder = ProjectBuilder(output)

    project = builder.build(name)

    print()
    print("Proyecto creado:")
    print(project)
    print()

    return project


def create_component(
    builder_class: type[AgentBuilder] | type[DepartmentBuilder],
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
    builder_class: type[AgentBuilder] | type[DepartmentBuilder],
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
    builder_class: type[AgentBuilder] | type[DepartmentBuilder],
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


def main():

    parser = argparse.ArgumentParser(prog="builder", description="Constructor de Camilo OS")

    sub = parser.add_subparsers(dest="cmd")

    sub.add_parser("status")

    p = sub.add_parser("create-project")
    p.add_argument("name")
    p.add_argument(
        "--output",
        type=Path,
        help="Directorio donde se creará el proyecto (por defecto: ./output)",
    )

    for command, help_text in (
        ("create-agent", "Crea un agente dentro de un proyecto"),
        ("create-department", "Crea un departamento dentro de un proyecto"),
    ):
        component_parser = sub.add_parser(command, help=help_text)
        component_parser.add_argument("project", help="Nombre del proyecto")
        component_parser.add_argument("name", help="Nombre del componente")
        component_parser.add_argument(
            "--output",
            type=Path,
            help="Directorio que contiene el proyecto (por defecto: ./output)",
        )
        component_parser.add_argument(
            "--template",
            help="Directorio de plantilla para inicializar el componente",
        )

    for command, help_text in (
        ("list-agents", "Lista los agentes de un proyecto"),
        ("list-departments", "Lista los departamentos de un proyecto"),
    ):
        list_parser = sub.add_parser(command, help=help_text)
        list_parser.add_argument("project", help="Nombre del proyecto")
        list_parser.add_argument(
            "--output",
            type=Path,
            help="Directorio que contiene el proyecto (por defecto: ./output)",
        )

    for command, help_text in (
        ("inspect-agent", "Muestra los detalles de un agente"),
        ("inspect-department", "Muestra los detalles de un departamento"),
    ):
        inspect_parser = sub.add_parser(command, help=help_text)
        inspect_parser.add_argument("project", help="Nombre del proyecto")
        inspect_parser.add_argument("name", help="Nombre del componente")
        inspect_parser.add_argument(
            "--output",
            type=Path,
            help="Directorio que contiene el proyecto (por defecto: ./output)",
        )

    list_templates_parser = sub.add_parser(
        "list-templates", help="Lista las plantillas registradas"
    )
    list_templates_parser.add_argument(
        "--type", dest="component_type", help="Filtra por tipo de componente"
    )

    inspect_template_parser = sub.add_parser(
        "inspect-template", help="Muestra los metadatos de una plantilla registrada"
    )
    inspect_template_parser.add_argument("name", help="Nombre de la plantilla")
    inspect_template_parser.add_argument(
        "--type",
        dest="component_type",
        required=True,
        help="Tipo de componente",
    )

    validate_template_parser = sub.add_parser(
        "validate-template", help="Valida una plantilla sin generar archivos"
    )
    validate_template_parser.add_argument(
        "template", help="Nombre registrado o ruta de plantilla"
    )
    validate_template_parser.add_argument(
        "--type",
        dest="component_type",
        required=True,
        help="Tipo de componente",
    )

    args = parser.parse_args()

    if args.cmd == "status":
        status()

    elif args.cmd == "create-project":
        try:
            create_project(args.name, args.output)
        except InvalidProjectName as error:
            parser.error(str(error))

    elif args.cmd in {"create-agent", "create-department"}:
        builder_class = (
            AgentBuilder if args.cmd == "create-agent" else DepartmentBuilder
        )
        try:
            create_component(
                builder_class,
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

    elif args.cmd in {"list-agents", "list-departments"}:
        builder_class = AgentBuilder if args.cmd == "list-agents" else DepartmentBuilder
        try:
            list_components(builder_class, args.project, args.output)
        except (InvalidProjectName, ProjectNotFound) as error:
            parser.error(str(error))

    elif args.cmd in {"inspect-agent", "inspect-department"}:
        builder_class = (
            AgentBuilder if args.cmd == "inspect-agent" else DepartmentBuilder
        )
        try:
            inspect_component(
                builder_class, args.project, args.name, args.output
            )
        except (ComponentNotFound, InvalidProjectName, ProjectNotFound) as error:
            parser.error(str(error))

    elif args.cmd == "list-templates":
        try:
            list_templates(args.component_type)
        except TemplateError as error:
            parser.error(str(error))

    elif args.cmd == "inspect-template":
        try:
            inspect_template(args.name, args.component_type)
        except TemplateError as error:
            parser.error(str(error))

    elif args.cmd == "validate-template":
        try:
            validate_template(args.template, args.component_type)
        except (OSError, TemplateError) as error:
            parser.error(str(error))

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
