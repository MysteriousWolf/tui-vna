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
class RenderedTemplate:
    """Rendered template output with diagnostics."""

    template: str
    rendered: str
    validation: TemplateValidation
    used_tags: tuple[str, ...] = ()
    used_time_formats: tuple[str, ...] = ()


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

    def replace(match: re.Match[str]) -> str:
        token = match.group(1)

        if token.startswith("%"):
            used_time_formats.append(token)
            try:
                return now.strftime(token)
            except Exception:
                # Keep literal if formatting fails unexpectedly.
                return match.group(0)

        if token in context:
            used_tags.append(token)
            return _bool_to_human(context[token])

        # Unknown tags are preserved literally by design.
        return match.group(0)

    rendered = _TOKEN_RE.sub(replace, template)

    return RenderedTemplate(
        template=template,
        rendered=rendered,
        validation=validation,
        used_tags=_stable_unique(used_tags),
        used_time_formats=_stable_unique(used_time_formats),
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
