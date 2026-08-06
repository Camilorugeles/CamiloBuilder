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

ROOT = Path(__file__).resolve().parent


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
    template: Path | None = None,
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
            type=Path,
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

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
