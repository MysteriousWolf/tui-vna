"""Export helpers for filename/folder templating and validation."""

from .templates import (
    SUPPORTED_SHORT_TAGS,
    RenderedTemplate,
    RenderedTemplateSegment,
    TemplateHistory,
    TemplateValidation,
    build_export_template_context,
    render_template,
    validate_template,
)

PATH_INVALID_CHARS = frozenset('<>:"|?*')
DEFAULT_TEMPLATE_TAGS = SUPPORTED_SHORT_TAGS
TemplateRenderContext = dict[str, object]
TemplateValidationResult = TemplateValidation
RenderedTemplateResult = RenderedTemplate
render_export_template = render_template
validate_export_template = validate_template

__all__ = [
    "DEFAULT_TEMPLATE_TAGS",
    "PATH_INVALID_CHARS",
    "RenderedTemplate",
    "RenderedTemplateResult",
    "RenderedTemplateSegment",
    "SUPPORTED_SHORT_TAGS",
    "TemplateHistory",
    "TemplateRenderContext",
    "TemplateValidation",
    "TemplateValidationResult",
    "build_export_template_context",
    "render_export_template",
    "render_template",
    "validate_export_template",
    "validate_template",
]
