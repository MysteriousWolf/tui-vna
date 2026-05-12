"""Tools tab logic helpers for the TINA GUI."""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import numpy as np
from textual.containers import Horizontal
from textual.widgets import Button, Checkbox, Input, Select, Static

from ...gui.components.frequency_entry import FrequencyEntry
from ...gui.modals.help import TEXTUAL_IMAGE_AVAILABLE, ImageWidget
from ...gui.plotting import (
    calculate_plot_range_with_outlier_filtering,
    get_plot_colors,
    get_terminal_font,
    unwrap_phase,
)
from ...tools import DistortionTool, MeasureTool
from ...tools.base import ToolResult
from ...tools.distortion import COMPONENT_NAMES as DISTORTION_COMPONENT_NAMES


def _freeze_cache_value(value: object) -> object:
    """Return a hashable, recursively frozen representation for cache keys."""
    if isinstance(value, dict):
        return tuple(
            (str(key), _freeze_cache_value(item))
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        )
    if isinstance(value, (list, tuple)):
        return tuple(_freeze_cache_value(item) for item in value)
    return value


def _tools_plot_state(app) -> dict:
    """Return the cached Matplotlib state for the Tools plot."""
    state = getattr(app, "_tools_mpl_plot_state", None)
    if state is None:
        state = {}
        app._tools_mpl_plot_state = state
    return state


async def _ensure_tools_plot_widget(container, widget_class, *args, **kwargs):
    """Reuse the existing tools plot widget when the widget type matches."""
    existing_children = list(container.children)
    existing_widget = existing_children[0] if existing_children else None

    if existing_widget is not None and isinstance(existing_widget, widget_class):
        for child in existing_children[1:]:
            await child.remove()
        return existing_widget, True

    await container.remove_children()
    widget = widget_class(*args, **kwargs)
    await container.mount(widget)
    return widget, False


def _clear_tools_overlay_artists(app) -> None:
    """Remove cursor and distortion overlay artists from the cached axes."""
    state = _tools_plot_state(app)
    for artist in state.get("overlay_artists", []):
        try:
            artist.remove()
        except Exception:
            pass
    state["overlay_artists"] = []


def _update_tools_plot_legend(ax, fg: str, grid: str, base_size: float) -> None:
    """Rebuild the legend after base or overlay changes."""
    legend = ax.get_legend()
    if legend is not None:
        legend.remove()

    handles, labels = ax.get_legend_handles_labels()
    if not handles:
        return

    legend = ax.legend(
        edgecolor=grid,
        labelcolor=fg,
        fontsize=base_size * 0.9,
    )
    legend.get_frame().set_alpha(0.5)
    legend.get_frame().set_facecolor("none")


def _style_tools_axes(
    fig,
    ax,
    *,
    freq_unit: str,
    y_label: str,
    plot_title: str,
    fg: str,
    grid: str,
) -> float:
    """Apply consistent styling to the Tools Matplotlib axes."""
    fig.patch.set_alpha(0.0)
    ax.set_facecolor("none")

    _font_family, base_size = get_terminal_font()
    base_size = base_size or 10.0

    ax.set_xlabel(f"Frequency ({freq_unit})", color=fg, fontsize=base_size)
    ax.set_ylabel(y_label, color=fg, fontsize=base_size)
    ax.set_title(plot_title, color=fg, fontsize=base_size * 1.2, pad=15)
    ax.tick_params(colors=fg, labelsize=base_size * 0.85)
    ax.grid(True, alpha=0.2, color=grid, linestyle="-", linewidth=0.5)

    for spine in ax.spines.values():
        spine.set_edgecolor(grid)
        spine.set_linewidth(1)

    return base_size


def _get_tools_base_data(
    sparams: dict[str, tuple[np.ndarray, np.ndarray]],
    trace: str,
    plot_type: str,
) -> tuple[np.ndarray, str, str, object]:
    """Return plotted data and a stable cache key for the base trace."""
    mag, phase = sparams[trace]
    if plot_type == "magnitude":
        return mag, "Magnitude (dB)", f"{trace} Magnitude", (trace, plot_type, id(mag))
    if plot_type == "phase":
        return (
            unwrap_phase(phase),
            "Phase (°)",
            f"{trace} Phase (Unwrapped)",
            (trace, plot_type, id(phase)),
        )
    return phase, "Phase (°)", f"{trace} Phase (Raw)", (trace, plot_type, id(phase))


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
        app.call_after_refresh(app._delayed_tools_refresh)


def get_distortion_comp_enabled(app) -> list[bool]:
    """Return enabled/disabled state for distortion component checkboxes."""
    defaults = [False, True, True, False, False, False]
    result = list(getattr(app, "_tools_distortion_comp_enabled", defaults))
    for n in range(6):
        try:
            result[n] = app.query_one(f"#input_distortion_comp_{n}", Checkbox).value
        except Exception:
            pass
    app._tools_distortion_comp_enabled = list(result)
    return result


async def rebuild_tools_params(app) -> None:
    """Rebuild the tools parameter panel for the currently active tool.

    This function updates the always-present FrequencyEntry inputs (rendered at
    compose time) and populates the dynamic subcontainer `#tools_params_dynamic`
    with tool-specific controls such as distortion component checkboxes.
    """
    try:
        container = app.query_one("#tools_params_dynamic")
    except Exception:
        app.log_message("rebuild_tools_params: tools_params_dynamic not found", "error")
        return

    app.log_message(
        "rebuild_tools_params: found tools_params_dynamic, clearing children", "debug"
    )
    active = app.settings.tools_active_tool
    freq_unit = (
        app.last_measurement.get("freq_unit", "MHz") if app.last_measurement else "MHz"
    )
    app.log_message(
        (
            f"rebuild_tools_params: active={active!r} "
            f"freq_unit={freq_unit!r} "
            f"last_measurement={'yes' if app.last_measurement else 'no'}"
        ),
        "debug",
    )

    try:
        for n in (1, 2):
            try:
                fe = app.query_one(f"FrequencyEntry.tools-cursor-{n}", FrequencyEntry)
                fe.set_frequency_hz(getattr(app, f"_tools_cursor{n}_hz", None))
                fe.set_minima_mode(getattr(app, f"_tools_cursor{n}_minima", False))
                fe.set_smoothing_mode(
                    getattr(app, f"_tools_cursor{n}_smoothing", False)
                )
            except Exception:
                pass

        app.log_message("Updated static FrequencyEntry widgets from app state", "debug")
    except Exception as exc_update:
        app.log_message(
            f"Failed updating static FrequencyEntry widgets: {exc_update}", "warning"
        )

    distortion_comp_enabled = get_distortion_comp_enabled(app)

    await container.remove_children()

    if active == "distortion":
        comp_row = Horizontal(classes="distortion-row")
        await container.mount(comp_row)
        for n in range(6):
            await comp_row.mount(
                Checkbox(
                    DISTORTION_COMPONENT_NAMES[n],
                    value=distortion_comp_enabled[n],
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


def _detect_peaks_numpy(search_data: np.ndarray, minima: bool) -> np.ndarray:
    """Detect extrema via derivative sign changes — no SciPy required."""
    d = np.diff(search_data)
    if d.size < 2:
        return np.array([], dtype=int)
    if minima:
        cond = (d[:-1] < 0) & (d[1:] > 0)
    else:
        cond = (d[:-1] > 0) & (d[1:] < 0)
    peaks = np.where(cond)[0] + 1
    if peaks.size == 0:
        return np.array([], dtype=int)
    return np.sort(np.unique(np.asarray(peaks, dtype=int)))


def _smooth_for_extrema(
    data: np.ndarray,
    win: int,
    max_win: int,
    outlier_count: int,
    outlier_thresh: int,
    spsig: Any,
) -> np.ndarray:
    """Apply smoothing to data and return the smoothed array.

    Tries savgol_filter (SciPy), medfilt (SciPy), then boxcar convolution (NumPy)
    in that order, falling back gracefully to the next option on failure.
    """
    wl: int
    poly: int
    if win >= 5:
        wl = min(win, max_win)
    else:
        wl = min(5, max_win)
    if wl % 2 == 0:
        wl += 1
    if wl < 3:
        wl = 3
    poly = min(3, max(1, wl - 2))

    if spsig is not None:
        try:
            if wl >= 5 and hasattr(spsig, "savgol_filter"):
                return np.asarray(
                    cast(Any, spsig).savgol_filter(
                        data, window_length=wl, polyorder=poly
                    ),
                    dtype=float,
                )
            if outlier_count > outlier_thresh and hasattr(spsig, "medfilt"):
                k = win if win % 2 == 1 else win + 1
                return np.asarray(
                    cast(Any, spsig).medfilt(data, kernel_size=k), dtype=float
                )
        except Exception:
            pass

    k = max(3, win)
    kernel = np.ones(k) / float(k)
    return np.asarray(np.convolve(data, kernel, mode="same"), dtype=float)


def _detect_peaks_scipy(
    spsig: Any, target: np.ndarray, distance: int, prominence: float
) -> np.ndarray:
    """Call scipy.signal.find_peaks and return peaks array (empty on failure)."""
    try:
        peaks, _ = cast(Any, spsig).find_peaks(
            target, distance=distance, prominence=prominence
        )
        return np.asarray(peaks, dtype=int)
    except Exception:
        return np.array([], dtype=int)


def _select_top_by_prominence(
    spsig: Any,
    target: np.ndarray,
    peaks: np.ndarray,
    search_data: np.ndarray,
    baseline: float,
    desired_peaks: int,
) -> np.ndarray:
    """Trim peaks to desired_peaks by descending prominence."""
    if spsig is not None and hasattr(spsig, "peak_prominences"):
        try:
            prominences = np.asarray(
                cast(Any, spsig).peak_prominences(target, peaks)[0], dtype=float
            )
        except Exception:
            prominences = np.asarray(np.abs(search_data[peaks] - baseline), dtype=float)
    else:
        prominences = np.asarray(np.abs(search_data[peaks] - baseline), dtype=float)
    order = np.argsort(-prominences)
    return peaks[order[:desired_peaks]]


def _detect_candidates_with_smoothing(
    data, freqs, minima, smoothing, desired_peaks=10, prominence_factor=0.005
):
    """Detect extrema candidates with an adaptive smoothing + prominence filter.

    Returns an array of candidate indices (into original data) meeting the
    prominence criteria. If smoothing is False, simply returns extrema on raw
    data using derivative sign changes.
    """
    data = np.asarray(data, dtype=float)
    freqs = np.asarray(freqs, dtype=float)
    if data.size < 3 or freqs.size != data.size:
        return np.array([], dtype=int)

    win = max(3, int(round(len(data) / float(desired_peaks))))
    if win % 2 == 0:
        win += 1
    max_win = min(len(data) // 2, max(101, len(data) // 4))
    win = min(win, max_win)
    if win < 3:
        win = 3

    try:
        import scipy.signal as spsig
    except Exception:
        spsig = None

    if not smoothing:
        return _detect_peaks_numpy(data, minima)

    med = float(np.median(data))
    mad = float(np.median(np.abs(data - med)))
    outlier_count = int(
        np.count_nonzero(np.abs(data - med) > (3 * mad if mad > 0 else 0))
    )
    outlier_thresh = max(3, int(len(data) * 0.01))

    search_data = _smooth_for_extrema(
        data, win, max_win, outlier_count, outlier_thresh, spsig
    )

    baseline = float(np.median(search_data))
    rng = float(np.max(search_data) - np.min(search_data))
    madsm = float(np.median(np.abs(search_data - baseline)))
    min_prominence = max(prominence_factor * rng, 3 * madsm)

    if spsig is not None and hasattr(spsig, "find_peaks"):
        target = -search_data if minima else search_data
        distance = max(1, win // 2)

        peaks = _detect_peaks_scipy(spsig, target, distance, min_prominence)
        if peaks.size == 0:
            peaks = _detect_peaks_scipy(spsig, target, distance, 0)

        if peaks.size == 0:
            return _detect_peaks_numpy(search_data, minima)

        if peaks.size > desired_peaks:
            peaks = _select_top_by_prominence(
                spsig, target, peaks, search_data, baseline, desired_peaks
            )

        return np.sort(np.unique(np.asarray(peaks, dtype=int)))

    return _detect_peaks_numpy(search_data, minima)


def _get_cached_distortion_result(
    app,
    freqs: np.ndarray,
    sparams: dict,
    trace: str,
    plot_type: str,
    cursor1_hz: float | None,
    cursor2_hz: float | None,
):
    """Return a cached distortion result for the current data and parameters."""
    trace_data = sparams.get(trace)
    if trace_data is None:
        return DistortionTool().compute(
            freqs,
            sparams,
            trace,
            plot_type,
            cursor1_hz,
            cursor2_hz,
        )

    mag, phase = trace_data
    data_key = (id(freqs), id(mag), id(phase))
    if data_key != getattr(app, "_tools_distortion_cache_last_data_key", None):
        app._tools_distortion_cache = {}
        app._tools_distortion_cache_last_data_key = data_key

    cache = getattr(app, "_tools_distortion_cache", None)
    if cache is None:
        cache = {}
        app._tools_distortion_cache = cache

    cache_key = (
        data_key,
        str(trace),
        str(plot_type),
        float(cursor1_hz) if cursor1_hz is not None else None,
        float(cursor2_hz) if cursor2_hz is not None else None,
    )
    if cache_key in cache:
        return cache[cache_key]

    result = DistortionTool().compute(
        freqs,
        sparams,
        trace,
        plot_type,
        cursor1_hz,
        cursor2_hz,
    )
    try:
        cache[cache_key] = result
    except Exception:
        pass
    return result


def _format_copyable_cell(raw_value: str, width: int) -> str:
    """Return a clickable Rich cell that copies the raw value."""
    return f"[@click='app.copy_cell_value(\"{raw_value}\")']{raw_value:>{width}}[/]"


def _format_measure_result_table(
    result: ToolResult,
    *,
    freq_unit: str,
    multiplier: float,
    cursor1_color: str,
    cursor2_color: str,
) -> str:
    """Return the cursor tool results table without mutating UI state."""
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
            f"[bold {cursor1_color}]{'Cursor 1':>{labelw}}[/]  "
            f"{_format_copyable_cell(f1_raw, valw)}  "
            f"{_format_copyable_cell(v1_raw, valw)}"
        )

    if result.cursor2_freq_hz is not None and result.cursor2_value is not None:
        f2_raw = f"{result.cursor2_freq_hz / multiplier:.4f}"
        v2_raw = f"{result.cursor2_value:.4f}"
        lines.append(
            f"[bold {cursor2_color}]{'Cursor 2':>{labelw}}[/]  "
            f"{_format_copyable_cell(f2_raw, valw)}  "
            f"{_format_copyable_cell(v2_raw, valw)}"
        )

    if result.delta_value is not None:
        if result.cursor1_freq_hz is not None and result.cursor2_freq_hz is not None:
            fd_val = abs(float(result.cursor2_freq_hz) - float(result.cursor1_freq_hz))
            fd_raw = f"{fd_val / multiplier:.4f}"
        else:
            fd_raw = ""
        dv_raw = f"{result.delta_value:.4f}"
        lines.append(
            f"[dim]{'Δ':>{labelw}}[/dim]  "
            f"{_format_copyable_cell(fd_raw, valw)}  "
            f"{_format_copyable_cell(dv_raw, valw)}"
        )

    return "\n".join(lines)


def _format_distortion_result_table(
    result: ToolResult,
    *,
    overlay_hex: list[str],
    comp_enabled: list[bool],
) -> str:
    """Return the distortion tool results table without mutating UI state."""
    if not result.extra:
        return ""

    coeffs = result.extra["coeffs"]
    delta_y = result.extra["delta_y"]
    unit = result.unit_label
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
        c_cell = _format_copyable_cell(c_raw, valw)
        if n == 0:
            dy_cell = f"{'—':>{valw}}"
        else:
            dy_raw = f"{delta_y[n]:.4f}"
            dy_cell = _format_copyable_cell(dy_raw, valw)
        lines.append(f"[dim]{str(n):>{nw}}[/dim]  {name_cell}  {c_cell}  {dy_cell}")

    return "\n".join(lines)


def _render_tool_result_markup(
    result: ToolResult,
    *,
    freq_unit: str,
    multiplier: float,
    cursor1_color: str,
    cursor2_color: str,
    overlay_hex: list[str],
    comp_enabled: list[bool],
) -> str:
    """Return the rendered Tools results markup for a precomputed tool result."""
    if result.tool_name == "measure":
        if result.cursor1_value is None and result.cursor2_value is None:
            return "[dim]Enter cursor frequencies above.[/dim]"
        return _format_measure_result_table(
            result,
            freq_unit=freq_unit,
            multiplier=multiplier,
            cursor1_color=cursor1_color,
            cursor2_color=cursor2_color,
        )

    if result.tool_name == "distortion":
        if not result.extra:
            return "[dim]Enter both cursor frequencies above.[/dim]"
        return _format_distortion_result_table(
            result,
            overlay_hex=overlay_hex,
            comp_enabled=comp_enabled,
        )

    return "[dim]No tool active.[/dim]"


def handle_frequency_extrema_navigate(
    app,
    cursor_index: int,
    direction: int,
    minima: bool = False,
    smoothing: bool = False,
) -> None:
    """First-pass extrema navigation.

    cursor_index: 1 or 2
    direction: -1 for previous, +1 for next
    minima: search for minima when True, maxima when False
    smoothing: whether to run a lightweight smoothing pass before detection
    """
    if app.last_measurement is None:
        return

    freqs = app.last_measurement["freqs"]
    sparams = app.last_measurement["sparams"]
    trace = get_tools_trace(app)

    try:
        plot_type = app.query_one("#select_tools_plot_type", Select).value
    except Exception:
        plot_type = app.settings.tools_plot_type or "magnitude"

    if trace not in sparams:
        return

    if plot_type == "magnitude":
        data = np.asarray(sparams[trace][0])
    elif plot_type == "phase":
        data = np.asarray(unwrap_phase(sparams[trace][1]))
    else:
        data = np.asarray(sparams[trace][1])

    if data.size < 3 or freqs.size != data.size:
        return

    if id(data) != getattr(app, "_tools_extrema_cache_last_data_id", None):
        app._tools_extrema_cache = {}
        app._tools_extrema_cache_last_data_id = id(data)

    desired_peaks = int(getattr(app, "_tools_desired_peaks", 10))
    prominence_factor = float(getattr(app, "_tools_prominence_factor", 0.005))
    key = (
        id(data),
        bool(smoothing),
        bool(minima),
        int(desired_peaks),
        float(prominence_factor),
    )

    cache = getattr(app, "_tools_extrema_cache", None)
    if cache is None:
        cache = {}
        app._tools_extrema_cache = cache

    if key in cache:
        candidate_indices = cache[key]
    else:
        candidate_indices = _detect_candidates_with_smoothing(
            data,
            freqs,
            minima,
            smoothing,
            desired_peaks=desired_peaks,
            prominence_factor=prominence_factor,
        )
        try:
            cache[key] = candidate_indices
        except Exception:
            # best-effort cache; ignore failures to avoid breaking navigation
            pass
    if candidate_indices.size == 0:
        return
    cand_idx = candidate_indices

    current_hz = getattr(app, f"_tools_cursor{cursor_index}_hz", None)
    if current_hz is None:
        chosen = cand_idx[0] if direction > 0 else cand_idx[-1]
    else:
        if direction > 0:
            side = cand_idx[freqs[cand_idx] > current_hz]
            chosen = side[0] if side.size > 0 else None
        else:
            side = cand_idx[freqs[cand_idx] < current_hz]
            chosen = side[-1] if side.size > 0 else None

        if chosen is None:
            return

    sel_hz = float(freqs[int(chosen)])
    setattr(app, f"_tools_cursor{cursor_index}_hz", sel_hz)

    freq_unit = app.last_measurement.get("freq_unit", "MHz")
    unit_multipliers = {"Hz": 1, "kHz": 1e3, "MHz": 1e6, "GHz": 1e9}
    mult = unit_multipliers.get(freq_unit, 1e6)
    display_val = f"{sel_hz / mult:.6f}".rstrip("0").rstrip(".")

    try:
        app.query_one(f"#input_tools_cursor{cursor_index}", Input).value = display_val
    except Exception:
        pass

    if app._tools_input_timer is not None:
        app._tools_input_timer.stop()
        app._tools_input_timer = None
    if app._is_tools_tab_active():
        app._tools_input_timer = app.set_timer(0.2, app._delayed_tools_refresh)


def handle_frequency_mode_change(
    app, cursor_index: int, minima: bool, smoothing: bool
) -> None:
    """Store per-cursor mode flags for use by extrema navigation.

    These flags are intentionally simple and serve as the first-pass storage
    so UI debugging and later wiring can read them.
    """
    setattr(app, f"_tools_cursor{cursor_index}_minima", bool(minima))
    setattr(app, f"_tools_cursor{cursor_index}_smoothing", bool(smoothing))


async def delayed_redraw_tools_plot(app) -> None:
    """Trigger a deferred tools plot refresh after layout settles."""
    if app.last_measurement is None:
        return

    cache_key = get_tools_plot_cache_key(app)
    display_key = get_tools_plot_display_key(app)
    plot_file = app.plot_temp_dir / "tools_plot.png"
    if (
        cache_key == getattr(app, "_tools_plot_cache_key", None)
        and display_key == getattr(app, "_tools_plot_display_key", None)
        and plot_file.exists()
    ):
        return

    await app._refresh_tools_plot()


def get_tools_plot_display_key(app) -> tuple[int, int]:
    """Return the current Tools plot container size used for display decisions."""
    try:
        container = app.query_one("#tools_plot_container")
        return (
            int(container.content_size.width or 0),
            int(container.content_size.height or 0),
        )
    except Exception:
        return (0, 0)


def get_tools_plot_cache_key(app) -> tuple[object, ...] | None:
    """Return a cache key describing the current Tools plot inputs."""
    if app.last_measurement is None:
        return None

    freqs = app.last_measurement["freqs"]
    sparams = app.last_measurement["sparams"]
    trace = get_tools_trace(app)
    try:
        plot_type_value = app.query_one("#select_tools_plot_type", Select).value
    except Exception:
        plot_type_value = app.settings.tools_plot_type or "magnitude"
    plot_type = (
        str(plot_type_value) if isinstance(plot_type_value, str) else "magnitude"
    )
    colors = get_plot_colors(app.get_css_variables())
    distortion_components = tuple(app._get_distortion_comp_enabled())

    return (
        app.settings.plot_backend,
        trace,
        plot_type,
        app.settings.tools_active_tool,
        app.settings.cursor_marker_style,
        app._tools_cursor1_hz,
        app._tools_cursor2_hz,
        distortion_components,
        _freeze_cache_value(colors),
        id(freqs),
        tuple(
            (name, id(values[0]), id(values[1]))
            for name, values in sorted(sparams.items())
        ),
    )


async def delayed_tools_refresh(app) -> None:
    """Debounced tools refresh: redraw plot then recompute results."""
    if not app._is_tools_tab_active():
        return
    await app._refresh_tools_plot()
    app._run_tools_computation()


async def apply_tools_render_result(
    app,
    result: dict[str, object] | None = None,
    error: str | None = None,
) -> None:
    """Apply a worker-rendered Tools image result to the UI."""
    if app.last_measurement is None:
        return

    try:
        container = app.query_one("#tools_plot_container")
    except Exception:
        return

    plot_file = app.plot_temp_dir / "tools_plot.png"
    if isinstance(result, dict):
        result_path = result.get("path")
        if isinstance(result_path, str) and result_path:
            plot_file = app.plot_temp_dir / Path(result_path).name

    if error is not None:
        msg_widget, _ = await _ensure_tools_plot_widget(
            container,
            Static,
            f"[red]Failed to generate tools plot image.[/red]\n[dim]Error: {error}[/dim]",
            markup=True,
        )
        msg_widget.update(
            f"[red]Failed to generate tools plot image.[/red]\n[dim]Error: {error}[/dim]"
        )
        return

    if plot_file.exists() and TEXTUAL_IMAGE_AVAILABLE:
        try:
            img_widget, _ = await _ensure_tools_plot_widget(
                container,
                ImageWidget,
                str(plot_file),
            )
            img_widget.image = str(plot_file)
            container_w = container.content_size.width
            if container_w and container_w > 10:
                img_widget.set_class(False, "tools-image-fallback")
                img_widget.set_class(True, "tools-image-display")
            else:
                img_widget.set_class(False, "tools-image-display")
                img_widget.set_class(True, "tools-image-fallback")
            img_widget.refresh()
        except Exception as exc:
            err_widget, _ = await _ensure_tools_plot_widget(
                container,
                Static,
                f"[red]Image display error: {exc}[/red]",
                markup=True,
            )
            err_widget.update(f"[red]Image display error: {exc}[/red]")
    elif not TEXTUAL_IMAGE_AVAILABLE:
        msg = "[yellow]Image backend available, but image display support is missing.[/yellow]"
        msg_widget, _ = await _ensure_tools_plot_widget(
            container,
            Static,
            msg,
            markup=True,
        )
        msg_widget.update(msg)
    else:
        msg = "[red]Failed to generate tools plot image.[/red]"
        msg_widget, _ = await _ensure_tools_plot_widget(
            container,
            Static,
            msg,
            markup=True,
        )
        msg_widget.update(msg)


async def refresh_tools_plot(app, *, tool_result: dict | None = None) -> None:
    """Render the Tools tab plot for the currently selected trace.

    Parameters:
        app: The running VNAApp instance.
        tool_result: Pre-computed tool result dict (from TOOLS_COMPUTE); when
            provided the terminal backend draws cursor markers and distortion
            overlays in addition to the base trace and cursor vlines.
    """
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

    data, y_label, plot_title, base_data_key = _get_tools_base_data(
        sparams, trace, plot_type
    )

    auto_y_min, auto_y_max = calculate_plot_range_with_outlier_filtering(
        data, outlier_percentile=1.0, safety_margin=0.05
    )
    freq_axis = freqs / multiplier
    plot_colors = get_plot_colors(app.get_css_variables())
    trace_color_rgb = plot_colors["traces_rgb"].get(trace, (255, 255, 255))
    cursor1_hz = app._tools_cursor1_hz
    cursor2_hz = app._tools_cursor2_hz
    cursor1_rgb = plot_colors["cursor1_rgb"]
    cursor2_rgb = plot_colors["cursor2_rgb"]

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

        cursor_marker_map = {"▼": "v", "✕": "x", "○": "o"}
        term_marker = cursor_marker_map.get(app.settings.cursor_marker_style, "x")
        if cursor1_hz is not None:
            x1 = cursor1_hz / multiplier
            plt_term.vline(x1, color=cursor1_rgb)
            if tool_result is not None and app.settings.tools_active_tool in (
                "cursor",
                "distortion",
            ):
                y1 = float(np.interp(cursor1_hz, freqs, data))
                plt_term.scatter([x1], [y1], color=cursor1_rgb, marker=term_marker)
        if cursor2_hz is not None:
            x2 = cursor2_hz / multiplier
            plt_term.vline(x2, color=cursor2_rgb)
            if tool_result is not None and app.settings.tools_active_tool in (
                "cursor",
                "distortion",
            ):
                y2 = float(np.interp(cursor2_hz, freqs, data))
                plt_term.scatter([x2], [y2], color=cursor2_rgb, marker=term_marker)

        # Distortion overlay curves
        if (
            tool_result is not None
            and app.settings.tools_active_tool == "distortion"
            and cursor1_hz is not None
            and cursor2_hz is not None
            and cursor1_hz != cursor2_hz
        ):
            extra = tool_result.get("extra") or {}
            coeffs = extra.get("coeffs")
            x_norm = extra.get("x_norm")
            f_band_hz = extra.get("f_band_hz")
            if (
                isinstance(coeffs, list)
                and isinstance(x_norm, list)
                and isinstance(f_band_hz, list)
            ):
                distortion_components = get_distortion_comp_enabled(app)
                overlay_colors_rgb = plot_colors.get("distortion_overlays_rgb", [])
                band_axis = (np.array(f_band_hz, dtype=float) / multiplier).tolist()
                x_values = np.array(x_norm, dtype=float)
                for idx in range(min(6, len(coeffs), len(distortion_components))):
                    if not distortion_components[idx]:
                        continue
                    cumulative = np.array(coeffs[: idx + 1], dtype=float)
                    curve_y = np.polynomial.legendre.legval(
                        x_values, cumulative
                    ).tolist()
                    color = (
                        overlay_colors_rgb[idx]
                        if idx < len(overlay_colors_rgb)
                        else trace_color_rgb
                    )
                    plt_term.plot(band_axis, curve_y, color=color)

        plot_widget.refresh()

    else:
        # Image rendering is handled by the caller (_refresh_tools_plot in main.py)
        return


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
        display.update(
            _render_tool_result_markup(
                result,
                freq_unit=freq_unit,
                multiplier=multiplier,
                cursor1_color=plot_colors["cursor1"],
                cursor2_color=plot_colors["cursor2"],
                overlay_hex=plot_colors["distortion_overlays"],
                comp_enabled=get_distortion_comp_enabled(app),
            )
        )
        return

    if active == "distortion":
        result = _get_cached_distortion_result(
            app,
            freqs,
            sparams,
            trace,
            plot_type,
            app._tools_cursor1_hz,
            app._tools_cursor2_hz,
        )
        plot_colors = get_plot_colors(app.get_css_variables())
        display.update(
            _render_tool_result_markup(
                result,
                freq_unit=freq_unit,
                multiplier=multiplier,
                cursor1_color=plot_colors["cursor1"],
                cursor2_color=plot_colors["cursor2"],
                overlay_hex=plot_colors["distortion_overlays"],
                comp_enabled=get_distortion_comp_enabled(app),
            )
        )
        return

    display.update("[dim]No tool active.[/dim]")


def render_tools_computation_result(app, result: ToolResult | dict | None) -> None:
    """Render a precomputed tools result into the existing results display."""
    try:
        display = app.query_one("#tools_results_display", Static)
    except Exception:
        return

    if result is None:
        display.update("[dim]No tool active.[/dim]")
        return

    if isinstance(result, dict):
        result = ToolResult(**result)

    freq_unit = (
        app.last_measurement.get("freq_unit", "MHz") if app.last_measurement else "MHz"
    )
    unit_multipliers = {"Hz": 1, "kHz": 1e3, "MHz": 1e6, "GHz": 1e9}
    multiplier = unit_multipliers.get(freq_unit, 1e6)
    plot_colors = get_plot_colors(app.get_css_variables())
    display.update(
        _render_tool_result_markup(
            result,
            freq_unit=freq_unit,
            multiplier=multiplier,
            cursor1_color=plot_colors["cursor1"],
            cursor2_color=plot_colors["cursor2"],
            overlay_hex=plot_colors["distortion_overlays"],
            comp_enabled=get_distortion_comp_enabled(app),
        )
    )


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
        app._tools_input_timer = None
    if app._is_tools_tab_active():
        app._tools_input_timer = app.set_timer(0.2, app._delayed_tools_refresh)


def handle_distortion_comp_change(app) -> None:
    """Refresh tools plot when a distortion component overlay checkbox changes."""
    if app.last_measurement is None:
        return
    app.call_after_refresh(app._delayed_tools_refresh)


async def handle_tools_trace_changed(app) -> None:
    """Update tools plot and results when the trace selection changes."""
    if app.last_measurement is None:
        return
    app.call_after_refresh(app._delayed_tools_refresh)


async def on_tools_plot_type_change(app) -> None:
    """Handle changes to the tools plot type."""
    if app.last_measurement is None:
        return
    app.call_after_refresh(app._delayed_tools_refresh)
