"""Measurement tab composition helpers for the TINA GUI."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Container, Horizontal, VerticalScroll
from textual.widgets import Button, Checkbox, Input, Label, Select, Static


def compose_measurement_tab(app) -> ComposeResult:
    """Compose the Measurement tab UI."""
    with Container(id="output_file_container", classes="panel") as panel:
        panel.border_title = "Output"
        with Horizontal(classes="plot-controls"):
            yield Static("No file loaded", id="output_file_label", markup=True)
            yield Static(classes="spacer")
            yield Button(
                "📂\nShow",
                id="btn_open_output",
                variant="primary",
                disabled=True,
                flat=True,
            )
            yield Button(
                "◐\nPNG",
                id="btn_export_png",
                variant="success",
                disabled=True,
                flat=True,
            )
            yield Button(
                "◇\nSVG",
                id="btn_export_svg",
                variant="success",
                disabled=True,
                flat=True,
            )

    with VerticalScroll():
        with Container(id="results_container", classes="panel") as panel:
            panel.border_title = "Plot"
            yield Static(
                "[dim]No measurements yet.[/dim]",
                id="results_plot_placeholder",
                markup=True,
            )

        with Container(classes="panel") as panel:
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
                        if app.settings.plot_type in ("magnitude", "phase", "phase_raw")
                        else "magnitude"
                    ),
                    id="select_plot_type",
                )
                yield Label("Show:")
                yield Checkbox("S11", id="check_plot_s11", value=app.settings.plot_s11)
                yield Checkbox("S21", id="check_plot_s21", value=app.settings.plot_s21)
                yield Checkbox("S12", id="check_plot_s12", value=app.settings.plot_s12)
                yield Checkbox("S22", id="check_plot_s22", value=app.settings.plot_s22)

            with Horizontal(classes="plot-controls"):
                with Horizontal(classes="span-axis-group"):
                    yield Label("X:")
                    yield Input(placeholder="Min", id="input_plot_freq_min")
                    yield Label("-")
                    yield Input(placeholder="Max", id="input_plot_freq_max")
                    yield Button(
                        "↻ Reset",
                        id="btn_reset_freq_limits",
                        variant="error",
                        flat=True,
                    )

                with Horizontal(classes="span-axis-group"):
                    yield Label("Y:")
                    yield Input(placeholder="Min", id="input_plot_y_min")
                    yield Label("-")
                    yield Input(placeholder="Max", id="input_plot_y_max")
                    yield Button(
                        "↻ Reset",
                        id="btn_reset_y_limits",
                        variant="error",
                        flat=True,
                    )

                yield Button(
                    "✓ Apply",
                    id="btn_apply_limits",
                    variant="primary",
                    flat=True,
                )
