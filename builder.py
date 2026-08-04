"""
CAMILO BUILDER
"""

import argparse
from pathlib import Path

from builders.project_builder import ProjectBuilder

ROOT = Path(__file__).resolve().parent


def status():
    print("=" * 60)
    print("CAMILO BUILDER")
    print("=" * 60)
    print("Estado: Operativo")


def create_project(name):

    output = ROOT / "output"

    builder = ProjectBuilder(output)

    project = builder.build(name)

    print()
    print("Proyecto creado:")
    print(project)
    print()


def main():

    parser = argparse.ArgumentParser()

    sub = parser.add_subparsers(dest="cmd")

    sub.add_parser("status")

    p = sub.add_parser("create-project")
    p.add_argument("name")

    args = parser.parse_args()

    if args.cmd == "status":
        status()

    elif args.cmd == "create-project":
        create_project(args.name)

    else:
        parser.print_help()


if __name__ == "__main__":
    main()