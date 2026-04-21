"""Setup/output templating logic helpers for the TINA GUI."""

from __future__ import annotations

from datetime import datetime

from textual.widgets import Input, Static

from ...export import (
    DEFAULT_TEMPLATE_TAGS,
    PATH_INVALID_CHARS,
    build_export_template_context,
    render_template,
    validate_template,
)
from ..components import (
    AutocompleteChoice,
    HistoryReplaceAutoComplete,
    TemplateAutoComplete,
)


def build_export_template_context_for_app(app) -> dict[str, object]:
    """Build export-template context from the current setup state."""
    start_freq = float(app.query_one("#input_start_freq", Input).value or "1.0")
    stop_freq = float(app.query_one("#input_stop_freq", Input).value or "1100.0")
    sweep_points = int(app.query_one("#input_points", Input).value or "601")
    averaging_count = int(app.query_one("#input_avg_count", Input).value or "16")
    span = stop_freq - start_freq

    return build_export_template_context(
        date_time=datetime.now(),
        host=app.query_one("#input_host", Input).value.strip(),
        vendor=getattr(app.worker, "vendor", ""),
        model=getattr(app.worker, "model", ""),
        start=f"{start_freq:.6g}",
        stop=f"{stop_freq:.6g}",
        span=f"{span:.6g}",
        pts=sweep_points,
        avg=averaging_count,
        ifbw="",
        cal=False,
    )


def validate_export_template_for_app(template: str, *, allow_path_separators: bool):
    """Validate one export template, optionally permitting folder separators."""
    invalid_chars = set(PATH_INVALID_CHARS)
    if allow_path_separators:
        invalid_chars.discard("/")
        invalid_chars.discard("\\")

    return validate_template(
        template,
        allowed_tags=set(DEFAULT_TEMPLATE_TAGS),
        invalid_path_chars=invalid_chars,
    )


def apply_template_input_state(app, input_id: str, validation, *, kind: str) -> None:
    """Apply warning/error classes and tooltip-like hints to a template input."""
    widget = app.query_one(input_id, Input)
    widget.remove_class("template-warning", "template-error")

    messages: list[str] = []
    if validation.has_warnings:
        widget.add_class("template-warning")
        messages.append(f"Unknown {kind} tags: {', '.join(validation.unknown_tags)}")
    if validation.has_errors:
        widget.add_class("template-error")
        messages.append(
            "Invalid path characters: " + ", ".join(validation.invalid_characters)
        )

    widget.tooltip = "\n".join(messages) if messages else None


def update_template_preview(
    app,
    input_id: str,
    preview_id: str,
    *,
    allow_path_separators: bool,
    default_template: str,
) -> None:
    """Render one template preview and update its paired preview widget."""
    template = app.query_one(input_id, Input).value.strip() or default_template
    preview = app.query_one(preview_id, Static)

    # Validate template but results are currently rendered-only; keep for side-effects
    validate_export_template_for_app(
        template,
        allow_path_separators=allow_path_separators,
    )
    rendered = render_template(
        template,
        context=build_export_template_context_for_app(app),
        allowed_tags=set(DEFAULT_TEMPLATE_TAGS),
        invalid_path_chars=(
            set(PATH_INVALID_CHARS) - {"/", "\\"}
            if allow_path_separators
            else set(PATH_INVALID_CHARS)
        ),
    )

    rendered_markup = []
    for segment in rendered.segments:
        if segment.source in ("tag", "time_format"):
            rendered_markup.append(f"[bold $accent]{segment.text}[/]")
        elif segment.source == "unknown":
            rendered_markup.append(f"[italic $warning]{segment.text}[/]")
        else:
            rendered_markup.append(segment.text)

    preview.update(
        "".join(rendered_markup) if rendered_markup else "[dim](empty)[/dim]"
    )

    # The preview border color was previously computed and applied via
    # programmatic styles. We now rely on a CSS class to control preview
    # appearance and keep theme logic centralized in tcss. Apply the class
    # unconditionally; tcss can reference theme variables for color decisions.
    preview.set_class(True, "preview-border-round")


def get_host_autocomplete_choices(app) -> list[AutocompleteChoice]:
    """Build host autocomplete choices from persisted host history."""
    return [
        AutocompleteChoice(
            value=host,
            kind="history",
            label=host,
            prefix="↺ ",
        )
        for host in app.settings.host_history
        if host
    ]


def get_port_autocomplete_choices(app) -> list[AutocompleteChoice]:
    """Build port autocomplete choices from persisted port history."""
    return [
        AutocompleteChoice(
            value=port,
            kind="history",
            label=port,
            prefix="↺ ",
        )
        for port in app.settings.port_history
        if port
    ]


def get_template_tag_choices() -> list[AutocompleteChoice]:
    """Build autocomplete choices for supported export template tags."""
    tag_examples = {
        "date": "{date}",
        "time": "{time}",
        "host": "{host}",
        "vend": "{vend}",
        "model": "{model}",
        "start": "{start}",
        "stop": "{stop}",
        "span": "{span}",
        "pts": "{pts}",
        "avg": "{avg}",
        "ifbw": "{ifbw}",
        "cal": "{cal}",
    }
    time_formats = ("{%Y%m%d_%H%M%S}", "{%Y-%m-%d}", "{%H%M}")
    choices = [
        AutocompleteChoice(
            value=value,
            kind="tag",
            label=value,
            prefix="# ",
        )
        for value in tag_examples.values()
    ]
    choices.extend(
        AutocompleteChoice(
            value=value,
            kind="tag",
            label=value,
            prefix="% ",
        )
        for value in time_formats
    )
    return choices


def get_filename_template_autocomplete_choices(app) -> list[AutocompleteChoice]:
    """Build autocomplete choices for filename templates."""
    history = [
        AutocompleteChoice(
            value=template,
            kind="history",
            label=template,
            prefix="↺ ",
        )
        for template in (app.settings.filename_template_history or [])
        if template
    ]
    return history + get_template_tag_choices()


def get_folder_template_autocomplete_choices(app) -> list[AutocompleteChoice]:
    """Build autocomplete choices for folder templates."""
    history = [
        AutocompleteChoice(
            value=template,
            kind="history",
            label=template,
            prefix="↺ ",
        )
        for template in (app.settings.folder_template_history or [])
        if template
    ]
    return history + get_template_tag_choices()


def mount_setup_autocompletes(app) -> None:
    """Mount autocomplete widgets for setup inputs."""
    app.mount(
        HistoryReplaceAutoComplete(
            "#input_host",
            lambda: get_host_autocomplete_choices(app),
            id="ac_host",
        )
    )
    app.mount(
        HistoryReplaceAutoComplete(
            "#input_port",
            lambda: get_port_autocomplete_choices(app),
            id="ac_port",
        )
    )
    app.mount(
        TemplateAutoComplete(
            "#input_filename_prefix",
            lambda: get_filename_template_autocomplete_choices(app),
            id="ac_filename_template",
        )
    )
    app.mount(
        TemplateAutoComplete(
            "#input_output_folder",
            lambda: get_folder_template_autocomplete_choices(app),
            id="ac_folder_template",
        )
    )


def refresh_export_template_validation(app) -> None:
    """Validate current filename and folder templates and refresh input styling."""
    filename_template = app.query_one("#input_filename_prefix", Input).value.strip()
    folder_template = app.query_one("#input_output_folder", Input).value.strip()

    app._filename_template_validation = validate_export_template_for_app(
        filename_template or app.settings.filename_template,
        allow_path_separators=False,
    )
    app._folder_template_validation = validate_export_template_for_app(
        folder_template or app.settings.folder_template,
        allow_path_separators=True,
    )

    apply_template_input_state(
        app,
        "#input_filename_prefix",
        app._filename_template_validation,
        kind="filename template",
    )
    apply_template_input_state(
        app,
        "#input_output_folder",
        app._folder_template_validation,
        kind="folder template",
    )
    update_template_preview(
        app,
        "#input_filename_prefix",
        "#preview_filename_template",
        allow_path_separators=False,
        default_template=app.settings.filename_template or "measurement_{date}_{time}",
    )
    update_template_preview(
        app,
        "#input_output_folder",
        "#preview_folder_template",
        allow_path_separators=True,
        default_template=app.settings.folder_template or "measurement",
    )


def debounced_export_template_refresh(app) -> None:
    """Debounced refresh for export template validation and preview updates."""
    app._template_input_timer = None
    refresh_export_template_validation(app)


def handle_export_template_change(app) -> None:
    """Refresh export-template validation when the template inputs change."""
    if app._template_input_timer is not None:
        app._template_input_timer.stop()
    app._template_input_timer = app.set_timer(
        0.15,
        lambda: debounced_export_template_refresh(app),
    )
