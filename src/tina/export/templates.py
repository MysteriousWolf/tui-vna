"""Export template rendering and validation utilities.

This module provides a shared templating engine for export filename and folder
templates. It supports:

- Short tag names (e.g. ``{date}``, ``{host}``, ``{start}``)
- Direct ``strftime`` formatting inside braces (e.g. ``{%Y%m%d_%H%M%S}``)
- Unknown tags preserved literally while reported as warnings
- Invalid path character validation with error status

The renderer is intentionally pure and UI-agnostic so it can be reused from
both setup validation and export execution paths.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime

# Windows-invalid path chars; broadly safe to enforce cross-platform.
_INVALID_PATH_CHARS = set('<>:"|?*')
_TOKEN_RE = re.compile(r"\{([^{}]+)\}")


@dataclass(slots=True, frozen=True)
class TemplateValidation:
    """Validation output for a template string."""

    unknown_tags: tuple[str, ...] = ()
    invalid_characters: tuple[str, ...] = ()

    @property
    def has_warnings(self) -> bool:
        """Whether template contains warning-level issues."""
        return bool(self.unknown_tags)

    @property
    def has_errors(self) -> bool:
        """Whether template contains error-level issues."""
        return bool(self.invalid_characters)


@dataclass(slots=True, frozen=True)
class RenderedTemplateSegment:
    """One rendered template segment with source metadata."""

    text: str
    source: str
    token: str | None = None


@dataclass(slots=True, frozen=True)
class RenderedTemplate:
    """Rendered template output with diagnostics."""

    template: str
    rendered: str
    validation: TemplateValidation
    used_tags: tuple[str, ...] = ()
    used_time_formats: tuple[str, ...] = ()
    segments: tuple[RenderedTemplateSegment, ...] = ()


@dataclass(slots=True)
class TemplateHistory:
    """Simple MRU list for template strings."""

    items: list[str] = field(default_factory=list)
    max_items: int = 20

    def touch(self, value: str) -> None:
        """Move an item to top of MRU history (or insert if new)."""
        normalized = value.strip()
        if not normalized:
            return

        if normalized in self.items:
            self.items.remove(normalized)

        self.items.insert(0, normalized)

        if len(self.items) > self.max_items:
            del self.items[self.max_items :]


def _stable_unique(values: Sequence[str]) -> tuple[str, ...]:
    seen: set[str] = set()
    out: list[str] = []
    for item in values:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return tuple(out)


def _bool_to_human(value: object) -> str:
    """Convert booleans to lowercase human-readable strings."""
    if isinstance(value, bool):
        return "yes" if value else "no"
    return str(value)


def validate_template(
    template: str,
    *,
    allowed_tags: set[str],
    invalid_path_chars: set[str] | None = None,
) -> TemplateValidation:
    """Validate template string for unknown tags and invalid path chars.

    Unknown tags are warning-level and are expected to remain literal during
    rendering. Invalid path characters are error-level.
    """
    if invalid_path_chars is None:
        invalid_path_chars = _INVALID_PATH_CHARS

    unknown: list[str] = []
    for match in _TOKEN_RE.finditer(template):
        token = match.group(1)
        if token.startswith("%"):
            # Direct strftime token.
            continue
        if token not in allowed_tags:
            unknown.append(token)

    invalid = [ch for ch in template if ch in invalid_path_chars]
    return TemplateValidation(
        unknown_tags=_stable_unique(unknown),
        invalid_characters=_stable_unique(invalid),
    )


def render_template(
    template: str,
    *,
    context: Mapping[str, object],
    now: datetime | None = None,
    allowed_tags: set[str] | None = None,
    invalid_path_chars: set[str] | None = None,
) -> RenderedTemplate:
    """Render a template string using context and timestamp formatting.

    Rules:
    - ``{known_tag}`` -> replaced with context value.
    - ``{%...}`` -> interpreted as ``strftime`` format.
    - ``{unknown}`` -> preserved literally and reported as warning.
    """
    if now is None:
        now = datetime.now()

    if allowed_tags is None:
        allowed_tags = set(context.keys())

    validation = validate_template(
        template,
        allowed_tags=allowed_tags,
        invalid_path_chars=invalid_path_chars,
    )

    used_tags: list[str] = []
    used_time_formats: list[str] = []
    rendered_parts: list[str] = []
    segments: list[RenderedTemplateSegment] = []
    last_end = 0

    for match in _TOKEN_RE.finditer(template):
        start, end = match.span()
        if start > last_end:
            literal_text = template[last_end:start]
            rendered_parts.append(literal_text)
            segments.append(
                RenderedTemplateSegment(
                    text=literal_text,
                    source="literal",
                )
            )

        token = match.group(1)
        original_text = match.group(0)

        if token.startswith("%"):
            used_time_formats.append(token)
            try:
                rendered_text = now.strftime(token)
                rendered_parts.append(rendered_text)
                segments.append(
                    RenderedTemplateSegment(
                        text=rendered_text,
                        source="time_format",
                        token=token,
                    )
                )
            except Exception:
                rendered_parts.append(original_text)
                segments.append(
                    RenderedTemplateSegment(
                        text=original_text,
                        source="unknown",
                        token=token,
                    )
                )
        elif token in context:
            used_tags.append(token)
            rendered_text = _bool_to_human(context[token])
            rendered_parts.append(rendered_text)
            segments.append(
                RenderedTemplateSegment(
                    text=rendered_text,
                    source="tag",
                    token=token,
                )
            )
        else:
            # Unknown tags are preserved literally by design.
            rendered_parts.append(original_text)
            segments.append(
                RenderedTemplateSegment(
                    text=original_text,
                    source="unknown",
                    token=token,
                )
            )

        last_end = end

    if last_end < len(template):
        literal_text = template[last_end:]
        rendered_parts.append(literal_text)
        segments.append(
            RenderedTemplateSegment(
                text=literal_text,
                source="literal",
            )
        )

    rendered = "".join(rendered_parts)

    return RenderedTemplate(
        template=template,
        rendered=rendered,
        validation=validation,
        used_tags=_stable_unique(used_tags),
        used_time_formats=_stable_unique(used_time_formats),
        segments=tuple(segments),
    )


def build_export_template_context(
    *,
    date_time: datetime | None = None,
    host: str = "",
    vendor: str = "",
    model: str = "",
    start: object = "",
    stop: object = "",
    span: object = "",
    pts: object = "",
    avg: object = "",
    ifbw: object = "",
    cal: object = "",
) -> dict[str, object]:
    """Build canonical export context for supported short tags.

    Supported tags:
    - ``date``, ``time``, ``host``, ``vend``, ``model``
    - ``start``, ``stop``, ``span``, ``pts``, ``avg``, ``ifbw``, ``cal``

    Notes:
    - Frequency values should be preformatted in selected setup unit.
    - Units are not appended automatically.
    """
    dt = date_time or datetime.now()
    return {
        "date": dt.strftime("%Y-%m-%d"),
        "time": dt.strftime("%H%M%S"),
        "host": host,
        "vend": vendor,
        "model": model,
        "start": start,
        "stop": stop,
        "span": span,
        "pts": pts,
        "avg": avg,
        "ifbw": ifbw,
        "cal": cal,
    }


SUPPORTED_SHORT_TAGS: tuple[str, ...] = (
    "date",
    "time",
    "host",
    "vend",
    "model",
    "start",
    "stop",
    "span",
    "pts",
    "avg",
    "ifbw",
    "cal",
)
