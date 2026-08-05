"""
CAMILO BUILDER
"""

import argparse
from pathlib import Path

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

    args = parser.parse_args()

    if args.cmd == "status":
        status()

    elif args.cmd == "create-project":
        try:
            create_project(args.name, args.output)
        except InvalidProjectName as error:
            parser.error(str(error))

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
