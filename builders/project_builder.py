from pathlib import Path


class ProjectBuilder:

    FOLDERS = (
        "agents",
        "kernel",
        "departments",
        "services",
        "config",
        "docs",
        "logs",
        "tests",
    )

    def __init__(self, output_dir: Path):
        self.output_dir = output_dir

    def build(self, project_name: str):

        project = self.output_dir / project_name
        project.mkdir(parents=True, exist_ok=True)

        for folder_name in self.FOLDERS:
            folder = project / folder_name
            folder.mkdir(exist_ok=True)
            (folder / "__init__.py").touch(exist_ok=True)

        (project / "README.md").write_text(
            "# CAMILO OS\n\nProyecto generado por Camilo Builder.\n",
            encoding="utf-8",
        )

        return project