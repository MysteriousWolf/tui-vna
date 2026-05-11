"""Measurement tab composition helpers for the TINA GUI."""

from __future__ import annotations

from typing import TYPE_CHECKING

from textual.app import ComposeResult
from textual.containers import Container, Horizontal, VerticalScroll
from textual.widgets import (
    Button,
    Checkbox,
    Input,
    Label,
    Markdown,
    Rule,
    Select,
    Static,
    TextArea,
)

if TYPE_CHECKING:
    from tina.main import VNAApp


def compose_measurement_tab(app: "VNAApp") -> ComposeResult:
    """Compose the Measurement tab UI.

    Parameters:
        app: The running VNAApp instance.  The function reads
            ``app.settings`` (plot_type, plot_s11/s21/s12/s22, output_folder,
            filename_prefix, export_s11/s21/s12/s22, etc.) to seed initial
            widget values, and yields widgets that call back into ``app``
            methods such as ``app.action_show_output_help`` and
            ``app.action_open_output_folder``.

    Returns:
        A Textual ``ComposeResult`` that yields the full Measurement tab
        widget tree.  Key widget IDs exposed for runtime use:
        - ``#output_file_label`` – current output file path label
        - ``#btn_open_output`` – opens the output folder in the file manager
        - ``#select_plot_type``, ``#select_export_s_params`` – plot/export selectors
        - ``#notes_area`` – freeform notes TextArea
        - ``#plot_container`` – container for the live plot widget
    """
    with Container(id="output_file_container", classes="panel") as panel:
        panel.border_title = "Output"
        with Horizontal(classes="plot-controls"):
            yield Static("No file loaded", id="output_file_label", markup=False)
            yield Static(classes="spacer")
            yield Button(
                "📂\nShow",
                id="btn_open_output",
                variant="primary",
                disabled=True,
                flat=True,
                classes="panel-button",
            )
            yield Button(
                "▢\nMin",
                id="btn_minimal_export",
                variant="default",
                flat=True,
                classes="panel-button",
            )
            yield Button(
                "⇩\nSxP",
                id="btn_export_touchstone",
                variant="success",
                disabled=True,
                flat=True,
                classes="panel-button",
            )
            yield Button(
                "≣\nCSV",
                id="btn_export_csv",
                variant="success",
                disabled=True,
                flat=True,
                classes="panel-button",
            )
            yield Button(
                "◐\nPNG",
                id="btn_export_png",
                variant="success",
                disabled=True,
                flat=True,
                classes="panel-button",
            )
            yield Button(
                "◇\nSVG",
                id="btn_export_svg",
                variant="success",
                disabled=True,
                flat=True,
                classes="panel-button",
            )

    with VerticalScroll():
        with Container(id="results_container", classes="panel") as panel:
            panel.border_title = "Plot"
            yield Static(
                "[dim]No measurements yet.[/dim]",
                id="results_plot_placeholder",
                markup=True,
            )

        with Horizontal(id="measurement_controls_row"):
            with Container(
                id="measurement_options_container", classes="panel"
            ) as panel:
                panel.border_title = "Options"

                with Horizontal(classes="plot-controls"):
                    yield Label("Type:")
                    yield Select(
                        options=[
                            ("Magnitude", "magnitude"),
                            ("Phase", "phase"),
                            ("Phase Raw", "phase_raw"),
                        ],
                        value=(
                            app.settings.plot_type
                            if app.settings.plot_type
                            in ("magnitude", "phase", "phase_raw")
                            else "magnitude"
                        ),
                        id="select_plot_type",
                    )
                    yield Label("Show:")
                    yield Checkbox(
                        "S11", id="check_plot_s11", value=app.settings.plot_s11
                    )
                    yield Checkbox(
                        "S21", id="check_plot_s21", value=app.settings.plot_s21
                    )
                    yield Checkbox(
                        "S12", id="check_plot_s12", value=app.settings.plot_s12
                    )
                    yield Checkbox(
                        "S22", id="check_plot_s22", value=app.settings.plot_s22
                    )

                with Horizontal(classes="plot-controls"):
                    yield Label("X:")
                    yield Input(placeholder="Min", id="input_plot_freq_min")
                    yield Label("-")
                    yield Input(placeholder="Max", id="input_plot_freq_max")
                    yield Button(
                        "↻ Reset",
                        id="btn_reset_freq_limits",
                        variant="error",
                        flat=True,
                        classes="plot-control-button",
                    )

                with Horizontal(classes="plot-controls"):
                    yield Label("Y:")
                    yield Input(placeholder="Min", id="input_plot_y_min")
                    yield Label("-")
                    yield Input(placeholder="Max", id="input_plot_y_max")
                    yield Button(
                        "↻ Reset",
                        id="btn_reset_y_limits",
                        variant="error",
                        flat=True,
                        classes="plot-control-button",
                    )

                with Horizontal(classes="plot-controls"):
                    yield Static(classes="spacer")
                    yield Button(
                        "✓ Apply",
                        id="btn_apply_limits",
                        variant="primary",
                        flat=True,
                        classes="plot-control-button",
                    )

            with Container(id="measurement_notes_container", classes="panel") as panel:
                # Notes panel title. Removed the in-title save affordance to
                # avoid duplicated/hidden controls; saving is handled via
                # Ctrl+S or the explicit Save button elsewhere in the UI.
                panel.border_title = "Notes"
                with Horizontal(id="measurement_notes_split"):
                    with Container(id="measurement_notes_editor_wrap"):
                        yield TextArea(
                            "",
                            id="measurement_notes_editor",
                        )
                    yield Rule(orientation="vertical", id="measurement_notes_separator")
                    with Container(id="measurement_notes_preview_wrap"):
                        yield Markdown(
                            "No notes yet",
                            id="measurement_notes_preview",
                        )
