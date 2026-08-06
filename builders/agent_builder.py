from pathlib import Path

from builders.component_builder import ComponentBuilder, InvalidTemplate
from template_system.errors import TemplateNotFound
from template_system.registry import TemplateRegistry
from template_system.renderer import TemplateRenderer
from template_system.resolver import TemplateResolver


class AgentBuilder(ComponentBuilder):
    component_folder = "agents"
    component_label = "Agente"

    def __init__(
        self,
        project_dir: Path,
        template_dir: str | Path | None = None,
        templates_dir: Path | None = None,
        renderer: TemplateRenderer | None = None,
    ):
        super().__init__(project_dir)
        templates_dir = templates_dir or Path(__file__).resolve().parents[1] / "templates"
        self.template_selection = template_dir
        self.resolver = TemplateResolver(TemplateRegistry(templates_dir))
        self.renderer = renderer or TemplateRenderer()

    def build(self, component_name: str) -> Path:
        self._validate_component_name(component_name)
        self._validate_project()
        try:
            template = self.resolver.resolve("agent", self.template_selection)
        except TemplateNotFound as error:
            raise InvalidTemplate(str(error)) from error
        component = self.project_dir / self.component_folder / component_name

        self.renderer.render_files(
            template.files_dir,
            component,
            template.manifest,
            {
                "component_name": component_name,
                "component_type": self.component_label.lower(),
            },
        )
        (component / "__init__.py").touch(exist_ok=True)
        return component
