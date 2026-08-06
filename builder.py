"""
CAMILO BUILDER
"""

import argparse
from pathlib import Path

from builders.agent_builder import AgentBuilder
from builders.component_builder import InvalidComponentName, ProjectNotFound
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
) -> Path:
    output = output or ROOT / "output"
    ProjectBuilder._validate_project_name(project_name)
    component = builder_class(output / project_name).build(component_name)

    print()
    print(f"{builder_class.component_label} creado:")
    print(component)
    print()

    return component


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
            create_component(builder_class, args.project, args.name, args.output)
        except (InvalidComponentName, InvalidProjectName, ProjectNotFound) as error:
            parser.error(str(error))

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
