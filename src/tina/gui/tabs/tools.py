"""Tools tab composition helpers for the TINA GUI."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical, VerticalScroll
from textual.widgets import Button, Label, RadioButton, RadioSet, Select, Static


def compose_tools_tab(app) -> ComposeResult:
    """Compose the Tools tab UI."""

    with Vertical():
        with VerticalScroll(id="tools_scroll"):
            # Plot frame
            with Container(id="tools_plot_container", classes="panel") as panel:
                panel.border_title = "Plot"
                yield Static(
                    "[dim]No measurement loaded.[/dim]",
                    id="tools_plot_placeholder",
                    markup=True,
                )

            # Selection + Results side by side
            with Horizontal(id="tools_middle_row"):
                # Selection frame
                with Container(classes="panel") as panel:
                    panel.border_title = "Selection"
                    with Horizontal(classes="plot-controls"):
                        yield Label("Type:")
                        yield Select(
                            options=[
                                ("Magnitude", "magnitude"),
                                ("Phase", "phase"),
                                ("Phase (raw)", "phase_raw"),
                            ],
                            value=(
                                app.settings.tools_plot_type
                                if app.settings.tools_plot_type
                                in ("magnitude", "phase", "phase_raw")
                                else "magnitude"
                            ),
                            id="select_tools_plot_type",
                        )
                        yield Label("Trace:")
                        with RadioSet(id="tools_trace_radioset"):
                            yield RadioButton(
                                "S11",
                                id="tools_radio_s11",
                                value=(app.settings.tools_trace == "S11"),
                            )
                            yield RadioButton(
                                "S21",
                                id="tools_radio_s21",
                                value=(app.settings.tools_trace == "S21"),
                            )
                            yield RadioButton(
                                "S12",
                                id="tools_radio_s12",
                                value=(app.settings.tools_trace == "S12"),
                            )
                            yield RadioButton(
                                "S22",
                                id="tools_radio_s22",
                                value=(app.settings.tools_trace == "S22"),
                            )

                    # Dynamic parameters area
                    with Vertical(id="tools_params_container"):
                        yield Static(
                            "[dim]Activate a tool below to see options.[/dim]",
                            id="tools_params_placeholder",
                            markup=True,
                        )

                # Results frame
                with Container(id="tools_results_container", classes="panel") as panel:
                    panel.border_title = (
                        "Tool Results [@click='app.show_tool_help'][on $primary] ? [/]"
                    )
                    yield Static(
                        "[dim]No tool active.[/dim]",
                        id="tools_results_display",
                        markup=True,
                    )

        # Tool selector — below the scroll area
        with Container(id="tools_tool_panel", classes="panel") as panel:
            panel.border_title = "Tool"
            with Horizontal(classes="button-group"):
                yield Button(
                    "⊙\nCursor",
                    id="btn_tool_measure",
                    variant="primary",
                    flat=True,
                )
                yield Button(
                    "⌇\nDistortion",
                    id="btn_tool_distortion",
                    variant="primary",
                    flat=True,
                )
