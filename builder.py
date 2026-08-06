"""
CAMILO BUILDER
"""

from builder_cli import (
    ROOT,
    TEMPLATES,
    create_component,
    create_project,
    get_catalog,
    inspect_component,
    inspect_service,
    inspect_template,
    list_components,
    list_templates,
    main,
    status,
    template_details,
    validate_template,
)


__all__ = [
    "ROOT",
    "TEMPLATES",
    "create_component",
    "create_project",
    "get_catalog",
    "inspect_component",
    "inspect_service",
    "inspect_template",
    "list_components",
    "list_templates",
    "main",
    "status",
    "template_details",
    "validate_template",
]


if __name__ == "__main__":
    main()
