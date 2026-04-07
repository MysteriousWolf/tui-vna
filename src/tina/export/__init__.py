"""Export helpers for filename/folder templating, validation, CSV, and image metadata."""

from .csv import CsvExporter, CsvExportResult
from .image_metadata import (
    ImageExportMetadata,
    build_image_export_metadata,
    embed_png_metadata,
    embed_svg_metadata,
    read_png_metadata,
    read_svg_metadata,
)
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
CSVExporter = CsvExporter

__all__ = [
    "CSVExporter",
    "CsvExporter",
    "CsvExportResult",
    "DEFAULT_TEMPLATE_TAGS",
    "ImageExportMetadata",
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
    "build_image_export_metadata",
    "embed_png_metadata",
    "embed_svg_metadata",
    "read_png_metadata",
    "read_svg_metadata",
    "render_export_template",
    "render_template",
    "validate_export_template",
    "validate_template",
]
