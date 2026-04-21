"""Tools tab composition helpers for the TINA GUI."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical, VerticalScroll
from textual.widgets import Button, Label, RadioButton, RadioSet, Select, Static


def compose_tools_tab(app) -> ComposeResult:
    """Compose the Tools tab UI.

    Plots can be tall and scrollable; the Selection and Results frames live in
    the same scrollable area so the whole Tools tab content scrolls together.
    Static FrequencyEntry rows are composed inside the Selection frame so they
    are always available and can be updated by runtime logic via stable inner IDs.
    """

    with Vertical():
        # Single scrollable area that contains just the Plot frame (so the plot
        # can be scrolled independently of the compact Selection/Results panels)
        with VerticalScroll(id="tools_scroll"):
            # Plot frame
            with Container(id="tools_plot_container", classes="panel") as panel:
                panel.border_title = "Plot"
                yield Static(
                    "[dim]No measurement loaded.[/dim]",
                    id="tools_plot_placeholder",
                    markup=True,
                )

            # Selection + Results side by side (inside the main scroll area so the
            # whole Tools tab scrolls as one unit). This keeps dynamic content
            # consistent and avoids per-frame scrollbars.
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
                    # Render static FrequencyEntry rows together with a dynamic subcontainer.
                    # We expose a single outer `#tools_params_container` here so runtime
                    # logic in `rebuild_tools_params` can target the dynamic subcontainer
                    # `#tools_params_dynamic` without losing the always-visible static
                    # FrequencyEntry selectors.
                    from ..components.frequency_entry import FrequencyEntry

                    with Vertical(id="tools_params_container"):
                        # Static part: always-visible FrequencyEntry rows (mirror sandbox layout)
                        with Vertical(id="tools_params_static"):
                            # Cursor 1 (static FrequencyEntry)
                            with Horizontal(classes="plot-controls"):
                                yield FrequencyEntry(
                                    input_id="input_tools_cursor1",
                                    prev_id="btn_freq1_prev",
                                    next_id="btn_freq1_next",
                                    minima_toggle_id="btn_freq1_toggle_min",
                                    smooth_toggle_id="btn_freq1_toggle_smooth",
                                    label="Cursor 1",
                                    freq_unit=(
                                        app.last_measurement.get("freq_unit", "MHz")
                                        if app.last_measurement
                                        else "MHz"
                                    ),
                                    classes="tools-frequency-row tools-cursor-1 tools-compact",
                                )

                            # Cursor 2 (static FrequencyEntry)
                            with Horizontal(classes="plot-controls"):
                                yield FrequencyEntry(
                                    input_id="input_tools_cursor2",
                                    prev_id="btn_freq2_prev",
                                    next_id="btn_freq2_next",
                                    minima_toggle_id="btn_freq2_toggle_min",
                                    smooth_toggle_id="btn_freq2_toggle_smooth",
                                    label="Cursor 2",
                                    freq_unit=(
                                        app.last_measurement.get("freq_unit", "MHz")
                                        if app.last_measurement
                                        else "MHz"
                                    ),
                                    classes="tools-frequency-row tools-cursor-2 tools-compact",
                                )

                        # Dynamic subcontainer for tool-specific controls (populated by rebuild_tools_params).
                        # `rebuild_tools_params` should clear and mount into this subcontainer
                        # (querying "#tools_params_dynamic") when dynamic content is required.
                        with Vertical(id="tools_params_dynamic"):
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
                    classes="toolbar-button",
                    id="btn_tool_measure",
                    variant="primary",
                    flat=True,
                )
                yield Button(
                    "⌇\nDistortion",
                    classes="toolbar-button",
                    id="btn_tool_distortion",
                    variant="primary",
                    flat=True,
                )
