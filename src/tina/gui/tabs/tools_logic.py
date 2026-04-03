"""Tools tab logic helpers for the TINA GUI."""

from __future__ import annotations

import matplotlib.pyplot as plt
import numpy as np
from textual.widgets import Button, Checkbox, Input, Select, Static

from ...gui.modals.help import TEXTUAL_IMAGE_AVAILABLE, ImageWidget
from ...gui.plotting import (
    DISTORTION_OVERLAY_LABELS,
    DISTORTION_OVERLAY_STYLES,
    calculate_plot_range_with_outlier_filtering,
    get_plot_colors,
    get_terminal_font,
    unwrap_phase,
)
from ...tools import DistortionTool, MeasureTool
from ...tools.distortion import COMPONENT_NAMES as DISTORTION_COMPONENT_NAMES


def get_tools_trace(app) -> str:
    """Return the currently selected tools trace, defaulting to S21."""
    try:
        if app.query_one("#tools_radio_s11").value:
            return "S11"
        if app.query_one("#tools_radio_s21").value:
            return "S21"
        if app.query_one("#tools_radio_s12").value:
            return "S12"
        if app.query_one("#tools_radio_s22").value:
            return "S22"
    except Exception:
        pass
    return "S21"


def apply_tool_ui(app) -> None:
    """Update tool button variants to reflect the active tool."""
    active = app.settings.tools_active_tool
    btn_cursor = app.query_one("#btn_tool_measure", Button)
    btn_distortion = app.query_one("#btn_tool_distortion", Button)

    btn_cursor.variant = "success" if active == "cursor" else "primary"
    btn_distortion.variant = "success" if active == "distortion" else "primary"


def set_active_tool(app, tool_name: str) -> None:
    """Toggle the active tool and refresh the tools UI."""
    app.settings.tools_active_tool = (
        None if app.settings.tools_active_tool == tool_name else tool_name
    )
    apply_tool_ui(app)
    app.call_after_refresh(app._rebuild_tools_params)
    if app.last_measurement is not None:
        app.call_after_refresh(app._refresh_tools_plot)
        app.call_after_refresh(app._run_tools_computation)


def get_distortion_comp_enabled(app) -> list[bool]:
    """Return enabled/disabled state for distortion component checkboxes."""
    defaults = [False, True, True, False, False, False]
    result = list(defaults)
    for n in range(6):
        try:
            result[n] = app.query_one(f"#input_distortion_comp_{n}", Checkbox).value
        except Exception:
            pass
    return result


async def rebuild_tools_params(app) -> None:
    """Rebuild the tools parameter panel for the currently active tool."""
    try:
        container = app.query_one("#tools_params_container")
    except Exception:
        return

    await container.remove_children()

    active = app.settings.tools_active_tool
    freq_unit = (
        app.last_measurement.get("freq_unit", "MHz") if app.last_measurement else "MHz"
    )

    if active in ("cursor", "distortion"):
        from textual.containers import Horizontal
        from textual.widgets import Checkbox, Input, Label

        unit_multipliers = {"Hz": 1, "kHz": 1e3, "MHz": 1e6, "GHz": 1e9}
        mult = unit_multipliers.get(freq_unit, 1e6)
        c1_val = (
            str(round(app._tools_cursor1_hz / mult, 6))
            if app._tools_cursor1_hz is not None
            else ""
        )
        c2_val = (
            str(round(app._tools_cursor2_hz / mult, 6))
            if app._tools_cursor2_hz is not None
            else ""
        )

        cursor1_row = Horizontal(classes="plot-controls")
        cursor2_row = Horizontal(classes="plot-controls")
        await container.mount(cursor1_row)
        await container.mount(cursor2_row)

        await cursor1_row.mount(
            Label("Cursor 1:", classes="tools-cursor-1"),
            Input(
                value=c1_val,
                placeholder=f"Frequency ({freq_unit})",
                id="input_tools_cursor1",
            ),
        )
        await cursor2_row.mount(
            Label("Cursor 2:", classes="tools-cursor-2"),
            Input(
                value=c2_val,
                placeholder=f"Frequency ({freq_unit})",
                id="input_tools_cursor2",
            ),
        )

        if active == "distortion":
            comp_row = Horizontal(classes="distortion-row")
            await container.mount(comp_row)
            for n in range(6):
                await comp_row.mount(
                    Checkbox(
                        DISTORTION_COMPONENT_NAMES[n],
                        value=(n in (1, 2)),
                        id=f"input_distortion_comp_{n}",
                        classes="distortion-comp-check",
                    )
                )
    else:
        await container.mount(
            Static(
                "[dim]Activate a tool below to see options.[/dim]",
                id="tools_params_placeholder",
                markup=True,
            )
        )


async def delayed_redraw_tools_plot(app) -> None:
    """Trigger a deferred tools plot refresh after layout settles."""
    if app.last_measurement is not None:
        await app._refresh_tools_plot()


async def delayed_tools_refresh(app) -> None:
    """Debounced tools refresh: redraw plot then recompute results."""
    await app._refresh_tools_plot()
    app._run_tools_computation()


async def refresh_tools_plot(app) -> None:
    """Render the Tools tab plot for the currently selected trace."""
    if app.last_measurement is None:
        return

    try:
        container = app.query_one("#tools_plot_container")
    except Exception:
        return

    freqs = app.last_measurement["freqs"]
    sparams = app.last_measurement["sparams"]
    freq_unit = app.last_measurement.get("freq_unit", "MHz")
    unit_multipliers = {"Hz": 1, "kHz": 1e3, "MHz": 1e6, "GHz": 1e9}
    multiplier = unit_multipliers.get(freq_unit, 1e6)

    trace = get_tools_trace(app)

    try:
        plot_type = app.query_one("#select_tools_plot_type", Select).value
    except Exception:
        plot_type = "magnitude"

    if trace not in sparams:
        await container.remove_children()
        await container.mount(
            Static(
                f"[yellow]Trace {trace} not available in current measurement.[/yellow]",
                markup=True,
            )
        )
        return

    mag, phase = sparams[trace]
    if plot_type == "magnitude":
        data = mag
        y_label = "Magnitude (dB)"
        plot_title = f"{trace} Magnitude"
    elif plot_type == "phase":
        data = unwrap_phase(phase)
        y_label = "Phase (°)"
        plot_title = f"{trace} Phase (Unwrapped)"
    else:
        data = phase
        y_label = "Phase (°)"
        plot_title = f"{trace} Phase (Raw)"

    auto_y_min, auto_y_max = calculate_plot_range_with_outlier_filtering(
        data, outlier_percentile=1.0, safety_margin=0.05
    )
    freq_axis = freqs / multiplier
    plot_colors = get_plot_colors(app.get_css_variables())
    trace_color_rgb = plot_colors["traces_rgb"].get(trace, (255, 255, 255))
    trace_color_hex = plot_colors["traces"].get(trace, "#ffffff")

    cursor1_hz = app._tools_cursor1_hz
    cursor2_hz = app._tools_cursor2_hz
    active_tool = app.settings.tools_active_tool
    marker_symbol = app.settings.cursor_marker_style

    cursor1_hex = plot_colors["cursor1"]
    cursor2_hex = plot_colors["cursor2"]
    cursor1_rgb = plot_colors["cursor1_rgb"]
    cursor2_rgb = plot_colors["cursor2_rgb"]

    mpl_markers = {"▼": "v", "✕": "x", "○": "o"}
    mpl_marker = mpl_markers.get(marker_symbol, "v")

    plot_backend = app.settings.plot_backend

    if plot_backend == "terminal":
        from textual_plotext import PlotextPlot

        existing = container.query(PlotextPlot)
        if existing:
            pw = existing.first()
            for child in list(container.children):
                if child is not pw:
                    await child.remove()
            plot_widget = pw
        else:
            await container.remove_children()
            plot_widget = PlotextPlot()
            await container.mount(plot_widget)

        plt_term = plot_widget.plt
        plt_term.clf()
        plt_term.theme("clear")
        plt_term.title(plot_title)
        plt_term.xlabel(f"Frequency ({freq_unit})")
        plt_term.ylabel(y_label)
        plt_term.plot(
            freq_axis.tolist(),
            data.tolist(),
            label=trace,
            marker="braille",
            color=trace_color_rgb,
        )
        plt_term.ylim(auto_y_min, auto_y_max)

        if cursor1_hz is not None:
            x1 = cursor1_hz / multiplier
            plt_term.vline(x1, color=cursor1_rgb)
        if cursor2_hz is not None:
            x2 = cursor2_hz / multiplier
            plt_term.vline(x2, color=cursor2_rgb)

        plot_widget.refresh()

    else:
        plot_file = app.plot_temp_dir / "tools_plot.png"
        dpi = 150
        fixed_width_px = 1920
        fixed_height_px = 1080

        fig, ax = plt.subplots(figsize=(fixed_width_px / dpi, fixed_height_px / dpi))
        fig.patch.set_alpha(0.0)
        ax.set_facecolor("none")

        fg = plot_colors["fg"]
        grid = plot_colors["grid"]

        ax.plot(freq_axis, data, color=trace_color_hex, linewidth=1.5, label=trace)
        ax.set_ylim(auto_y_min, auto_y_max)

        if cursor1_hz is not None:
            x1 = cursor1_hz / multiplier
            ax.axvline(x1, color=cursor1_hex, linewidth=1.2, zorder=3)
            if active_tool in ("cursor", "distortion"):
                y1 = np.interp(cursor1_hz, freqs, data)
                ax.scatter(
                    [x1],
                    [y1],
                    color=cursor1_hex,
                    marker=mpl_marker,
                    s=80,
                    zorder=5,
                )

        if cursor2_hz is not None:
            x2 = cursor2_hz / multiplier
            ax.axvline(x2, color=cursor2_hex, linewidth=1.2, zorder=3)
            if active_tool in ("cursor", "distortion"):
                y2 = np.interp(cursor2_hz, freqs, data)
                ax.scatter(
                    [x2],
                    [y2],
                    color=cursor2_hex,
                    marker=mpl_marker,
                    s=80,
                    zorder=5,
                )

        if (
            active_tool == "distortion"
            and cursor1_hz is not None
            and cursor2_hz is not None
            and cursor1_hz != cursor2_hz
        ):
            result = DistortionTool().compute(
                freqs,
                sparams,
                trace,
                plot_type,
                cursor1_hz,
                cursor2_hz,
            )
            if result.extra:
                ex = result.extra
                coeffs = ex["coeffs"]
                x = np.array(ex["x"])
                f_band_axis = np.array(ex["f_band_hz"]) / multiplier
                f_lo_axis = min(cursor1_hz, cursor2_hz) / multiplier
                f_hi_axis = max(cursor1_hz, cursor2_hz) / multiplier
                ax.axvspan(f_lo_axis, f_hi_axis, alpha=0.08, color=fg, zorder=0)
                comp_enabled = get_distortion_comp_enabled(app)
                overlay_hex = plot_colors["distortion_overlays"]
                for n in range(6):
                    if not comp_enabled[n]:
                        continue
                    cumulative = np.zeros(n + 1)
                    cumulative[:] = coeffs[: n + 1]
                    cumulative_y = np.polynomial.legendre.legval(x, cumulative)
                    ax.plot(
                        f_band_axis,
                        cumulative_y,
                        color=overlay_hex[n],
                        linestyle=DISTORTION_OVERLAY_STYLES[n],
                        linewidth=1.5,
                        label=DISTORTION_OVERLAY_LABELS[n],
                        zorder=4,
                    )

        _font_family, base_size = get_terminal_font()
        base_size = base_size or 10.0
        ax.set_xlabel(f"Frequency ({freq_unit})", color=fg, fontsize=base_size)
        ax.set_ylabel(y_label, color=fg, fontsize=base_size)
        ax.set_title(plot_title, color=fg, fontsize=base_size * 1.2, pad=15)
        ax.tick_params(colors=fg, labelsize=base_size * 0.85)
        ax.grid(True, alpha=0.2, color=grid, linestyle="-", linewidth=0.5)
        legend = ax.legend(
            edgecolor=grid,
            labelcolor=fg,
            fontsize=base_size * 0.9,
        )
        legend.get_frame().set_alpha(0.5)
        legend.get_frame().set_facecolor("none")

        for spine in ax.spines.values():
            spine.set_edgecolor(grid)
            spine.set_linewidth(1)

        plt.tight_layout()
        plt.savefig(
            plot_file,
            dpi=dpi,
            facecolor=fig.get_facecolor(),
            edgecolor="none",
            bbox_inches="tight",
            transparent=True,
        )
        plt.close(fig)

        await container.remove_children()

        if plot_file.exists() and TEXTUAL_IMAGE_AVAILABLE:
            try:
                img_widget = ImageWidget(str(plot_file))
                container_w = container.content_size.width
                if container_w and container_w > 10:
                    display_w = max(40, container_w - 4)
                    aspect = (fixed_width_px / 8) / (fixed_height_px / 16)
                    img_widget.styles.width = display_w
                    img_widget.styles.height = max(10, int(display_w / aspect))
                else:
                    img_widget.styles.width = 120
                    img_widget.styles.height = 60
                await container.mount(img_widget)
            except Exception as e:
                await container.mount(
                    Static(f"[red]Image display error: {e}[/red]", markup=True)
                )
        elif not TEXTUAL_IMAGE_AVAILABLE:
            await container.mount(
                Static(
                    "[yellow]Image backend available, but image display support is missing.[/yellow]",
                    markup=True,
                )
            )
        else:
            await container.mount(
                Static("[red]Failed to generate tools plot image.[/red]", markup=True)
            )


def run_tools_computation(app) -> None:
    """Run the currently selected tools module and populate the results display."""
    try:
        display = app.query_one("#tools_results_display", Static)
    except Exception:
        return

    active = app.settings.tools_active_tool
    if not active:
        display.update("[dim]No tool active.[/dim]")
        return
    if app.last_measurement is None:
        display.update("[dim]No measurement loaded.[/dim]")
        return

    freqs = app.last_measurement["freqs"]
    sparams = app.last_measurement["sparams"]
    freq_unit = app.last_measurement.get("freq_unit", "MHz")
    unit_multipliers = {"Hz": 1, "kHz": 1e3, "MHz": 1e6, "GHz": 1e9}
    multiplier = unit_multipliers.get(freq_unit, 1e6)

    trace = get_tools_trace(app)
    try:
        plot_type = app.query_one("#select_tools_plot_type", Select).value
    except Exception:
        plot_type = "magnitude"

    if active == "cursor":
        result = MeasureTool().compute(
            freqs,
            sparams,
            trace,
            plot_type,
            app._tools_cursor1_hz,
            app._tools_cursor2_hz,
        )
        if result.cursor1_value is None and result.cursor2_value is None:
            display.update("[dim]Enter cursor frequencies above.[/dim]")
            return

        plot_colors = get_plot_colors(app.get_css_variables())
        c1col = plot_colors["cursor1"]
        c2col = plot_colors["cursor2"]
        labelw, valw = 8, 9
        hdr = (
            f"[dim]{'':>{labelw}}  "
            f"{'Freq (' + freq_unit + ')':>{valw}}  "
            f"{result.unit_label:>{valw}}[/dim]"
        )
        sep = f"[dim]{'─' * (labelw + 2 + valw + 2 + valw)}[/dim]"
        lines = [hdr, sep]

        if result.cursor1_freq_hz is not None and result.cursor1_value is not None:
            f1_raw = f"{result.cursor1_freq_hz / multiplier:.4f}"
            v1_raw = f"{result.cursor1_value:.4f}"
            lines.append(
                f"[bold {c1col}]{'Cursor 1':>{labelw}}[/]  "
                f"[@click='app.copy_cell_value(\"{f1_raw}\")']{f1_raw:>{valw}}[/]  "
                f"[@click='app.copy_cell_value(\"{v1_raw}\")']{v1_raw:>{valw}}[/]"
            )

        if result.cursor2_freq_hz is not None and result.cursor2_value is not None:
            f2_raw = f"{result.cursor2_freq_hz / multiplier:.4f}"
            v2_raw = f"{result.cursor2_value:.4f}"
            lines.append(
                f"[bold {c2col}]{'Cursor 2':>{labelw}}[/]  "
                f"[@click='app.copy_cell_value(\"{f2_raw}\")']{f2_raw:>{valw}}[/]  "
                f"[@click='app.copy_cell_value(\"{v2_raw}\")']{v2_raw:>{valw}}[/]"
            )

        if result.delta_value is not None:
            fd_raw = f"{abs(result.cursor2_freq_hz - result.cursor1_freq_hz) / multiplier:.4f}"
            dv_raw = f"{result.delta_value:.4f}"
            lines.append(
                f"[dim]{'Δ':>{labelw}}[/dim]  "
                f"[@click='app.copy_cell_value(\"{fd_raw}\")']{fd_raw:>{valw}}[/]  "
                f"[@click='app.copy_cell_value(\"{dv_raw}\")']{dv_raw:>{valw}}[/]"
            )

        display.update("\n".join(lines))
        return

    if active == "distortion":
        result = DistortionTool().compute(
            freqs,
            sparams,
            trace,
            plot_type,
            app._tools_cursor1_hz,
            app._tools_cursor2_hz,
        )
        if not result.extra:
            display.update("[dim]Enter both cursor frequencies above.[/dim]")
            return

        ex = result.extra
        coeffs = ex["coeffs"]
        delta_y = ex["delta_y"]
        unit = result.unit_label
        overlay_hex = get_plot_colors(app.get_css_variables())["distortion_overlays"]
        comp_enabled = get_distortion_comp_enabled(app)
        nw, namew, valw = 1, 10, 9
        hdr = (
            f"[dim]{'n':>{nw}}  {'Component':<{namew}}  "
            f"{'cₙ (' + unit + ')':>{valw}}  {'Δyₙ (' + unit + ')':>{valw}}[/dim]"
        )
        sep = f"[dim]{'─' * (nw + 2 + namew + 2 + valw + 2 + valw)}[/dim]"
        lines = [hdr, sep]

        for n, name in enumerate(DISTORTION_COMPONENT_NAMES):
            c_raw = f"{coeffs[n]:.4f}"
            color = overlay_hex[n] if comp_enabled[n] else None
            name_cell = (
                f"[bold {color}]{name:<{namew}}[/]"
                if color
                else f"[dim]{name:<{namew}}[/dim]"
            )
            c_cell = f"[@click='app.copy_cell_value(\"{c_raw}\")']{c_raw:>{valw}}[/]"
            if n == 0:
                dy_cell = f"{'—':>{valw}}"
            else:
                dy_raw = f"{delta_y[n]:.4f}"
                dy_cell = (
                    f"[@click='app.copy_cell_value(\"{dy_raw}\")']{dy_raw:>{valw}}[/]"
                )
            lines.append(f"[dim]{str(n):>{nw}}[/dim]  {name_cell}  {c_cell}  {dy_cell}")

        display.update("\n".join(lines))
        return

    display.update("[dim]No tool active.[/dim]")


def handle_tool_measure_pressed(app) -> None:
    """Activate or deactivate the cursor tool."""
    set_active_tool(app, "cursor")


def handle_tool_distortion_pressed(app) -> None:
    """Activate or deactivate the distortion tool."""
    set_active_tool(app, "distortion")


def handle_tools_cursor_change(app) -> None:
    """Update internal cursor frequencies from the tools input fields."""
    if app.last_measurement is None:
        return

    freq_unit = app.last_measurement.get("freq_unit", "MHz")
    unit_multipliers = {"Hz": 1, "kHz": 1e3, "MHz": 1e6, "GHz": 1e9}
    multiplier = unit_multipliers.get(freq_unit, 1e6)

    def _parse(widget_id: str) -> float | None:
        try:
            val = app.query_one(widget_id, Input).value.strip()
            return float(val) * multiplier if val else None
        except Exception:
            return None

    app._tools_cursor1_hz = _parse("#input_tools_cursor1")
    app._tools_cursor2_hz = _parse("#input_tools_cursor2")

    if app._tools_input_timer is not None:
        app._tools_input_timer.stop()
    app._tools_input_timer = app.set_timer(0.2, app._delayed_tools_refresh)


def handle_distortion_comp_change(app) -> None:
    """Refresh tools plot when a distortion component overlay checkbox changes."""
    if app.last_measurement is None:
        return
    if app._tools_input_timer is not None:
        app._tools_input_timer.stop()
    app._tools_input_timer = app.set_timer(0.2, app._delayed_tools_refresh)


async def handle_tools_trace_changed(app) -> None:
    """Update tools plot and results when the trace selection changes."""
    if app.last_measurement is None:
        return
    await app._refresh_tools_plot()
    app._run_tools_computation()


async def on_tools_plot_type_change(app) -> None:
    """Handle changes to the tools plot type."""
    if app.last_measurement is None:
        return
    await app._refresh_tools_plot()
    app._run_tools_computation()
