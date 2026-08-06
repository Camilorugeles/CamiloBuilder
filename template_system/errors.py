class TemplateError(ValueError):
    """Base error for invalid or unsafe templates."""


class TemplateNotFound(TemplateError):
    """Raised when a registered template cannot be found."""


class InvalidTemplateManifest(TemplateError):
    """Raised when template metadata is missing or invalid."""


class TemplateRenderError(TemplateError):
    """Raised when a template cannot be rendered safely."""
