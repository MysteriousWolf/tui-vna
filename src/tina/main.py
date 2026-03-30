"""
tina - Terminal UI Network Analyzer
"""

import asyncio
import importlib.resources
import os
import platform
import queue
import re
import subprocess
import sys
import tempfile
import tkinter as tk
from datetime import datetime
from functools import partial
from pathlib import Path
from tkinter import filedialog

import matplotlib
import matplotlib.pyplot as plt
import numpy as np
import skrf as rf
from rich.markup import escape as rich_escape
from textual import on, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.command import Hit, Hits, Provider
from textual.containers import Container, Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import (
    Button,
    Checkbox,
    Footer,
    Header,
    Input,
    Label,
    Markdown,
    ProgressBar,
    RadioButton,
    RadioSet,
    RichLog,
    Select,
    Static,
    TabbedContent,
    TabPane,
)

# Set matplotlib to non-interactive backend
matplotlib.use("Agg")

from . import __version__
from .config.settings import SettingsManager
from .drivers import VNAConfig
from .tools import DistortionTool, MeasureTool
from .tools.distortion import COMPONENT_NAMES as _DISTORTION_COMPONENT_NAMES
from .utils import TouchstoneExporter
from .utils.update_checker import (
    fetch_test_update_data,
    get_changelogs_since,
    get_update_info,
    load_last_acknowledged_version,
    load_notified_prerelease,
    save_last_acknowledged_version,
    save_notified_prerelease,
)
from .worker import (
    LogMessage,
    MeasurementResult,
    MeasurementWorker,
    MessageType,
    ParamsResult,
    ProgressUpdate,
    StatusResult,
)

try:
    from pylatexenc.latex2text import LatexNodes2Text as _LatexNodes2Text

    _latex_converter = _LatexNodes2Text()
except ImportError:
    _latex_converter = None

# GUI-only imports - done at module level to ensure proper terminal detection
try:
    from textual_image.widget import Image as ImageWidget

    TEXTUAL_IMAGE_AVAILABLE = True
except ImportError:
    ImageWidget = None
    TEXTUAL_IMAGE_AVAILABLE = False

# S-parameter to theme variable mapping.
# Each S-param maps to a Textual CSS variable name.
# These must be distinct colors across all built-in Textual themes.
SPARAM_THEME_KEYS = {
    "S11": "error",
    "S21": "primary",
    "S12": "accent",
    "S22": "success",
}

# Fallback colors if theme variables are not available.
SPARAM_FALLBACK_COLORS = {
    "S11": "#ff6b6b",
    "S21": "#4ecdc4",
    "S12": "#ffe66d",
    "S22": "#c77dff",
}
TRACE_COLOR_DEFAULT = "#ffffff"

# Fixed hue-wheel palette for distortion overlays — guaranteed distinct regardless of theme.
DISTORTION_OVERLAY_COLORS: list[str] = [
    "#888888",  # n=0 constant  (~0° sat, neutral gray)
    "#cc8800",  # n=1 linear    (~45°,  amber)
    "#22aa44",  # n=2 parabolic (~135°, green)
    "#cc2233",  # n=3 cubic     (~350°, red)
    "#00aacc",  # n=4 quartic   (~190°, cyan)
    "#7733cc",  # n=5 quintic   (~275°, violet)
]
_DISTORTION_OVERLAY_STYLES: list = [
    "-",
    "--",
    "-.",
    ":",
    (0, (5, 2)),
    (0, (3, 1, 1, 1)),
]
_DISTORTION_OVERLAY_LABELS: list[str] = [
    "constant",
    "linear",
    "parabolic",
    "cubic",
    "quartic",
    "quintic",
]


def _hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    """Convert a hex color string to an (R, G, B) tuple."""
    h = hex_color.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _get_plot_colors(theme_vars: dict[str, str] | None = None) -> dict:
    """Build plot color scheme from Textual theme variables.

    Returns a dict with keys:
      'traces': dict of S-param hex colors
      'traces_rgb': dict of S-param (R,G,B) tuples (for plotext)
      'fg', 'bg', 'grid', 'surface': hex strings
      'default_trace': hex fallback
    """
    if theme_vars:
        traces = {}
        for param, key in SPARAM_THEME_KEYS.items():
            hex_val = theme_vars.get(key)
            traces[param] = hex_val if hex_val else SPARAM_FALLBACK_COLORS[param]
        fg = theme_vars.get("foreground", theme_vars.get("text", "#e6e1dc"))
        bg = theme_vars.get("background", "#0e1419")
        surface = theme_vars.get("surface", bg)
        grid = theme_vars.get("panel", theme_vars.get("surface-darken-1", "#2d3640"))
    else:
        traces = dict(SPARAM_FALLBACK_COLORS)
        fg = "#e6e1dc"
        bg = "#0e1419"
        surface = bg
        grid = "#2d3640"

    # Build RGB tuples for plotext (which doesn't support hex strings)
    traces_rgb = {}
    for param, hex_val in traces.items():
        try:
            traces_rgb[param] = _hex_to_rgb(hex_val)
        except (ValueError, IndexError):
            traces_rgb[param] = (255, 255, 255)

    def _resolve_color(
        theme_color: str | None, fallback: str
    ) -> tuple[str, tuple[int, int, int]]:
        """Return (hex, rgb) using theme_color if it's a valid hex, else fallback."""
        if theme_color:
            try:
                return theme_color, _hex_to_rgb(theme_color)
            except (ValueError, IndexError):
                pass
        return fallback, _hex_to_rgb(fallback)

    # Distortion overlay colors are fixed — guaranteed distinct across the hue wheel.
    distortion_overlays = list(DISTORTION_OVERLAY_COLORS)
    distortion_overlays_rgb = [_hex_to_rgb(h) for h in DISTORTION_OVERLAY_COLORS]

    # Cursor colors: cursor1 = warning, cursor2 = primary (matches CSS .tools-cursor-1/2)
    cursor1_hex, cursor1_rgb = _resolve_color(
        theme_vars.get("warning") if theme_vars else None, "#ffa500"
    )
    cursor2_hex, cursor2_rgb = _resolve_color(
        theme_vars.get("primary") if theme_vars else None, "#00d7ff"
    )

    return {
        "traces": traces,
        "traces_rgb": traces_rgb,
        "fg": fg,
        "bg": bg,
        "surface": surface,
        "grid": grid,
        "default_trace": TRACE_COLOR_DEFAULT,
        "distortion_overlays": distortion_overlays,
        "distortion_overlays_rgb": distortion_overlays_rgb,
        "cursor1": cursor1_hex,
        "cursor1_rgb": cursor1_rgb,
        "cursor2": cursor2_hex,
        "cursor2_rgb": cursor2_rgb,
    }


def _get_terminal_font() -> tuple[str, float | None]:
    """Detect the terminal's font family and size by parsing its config file.

    Uses TERM_PROGRAM to identify the terminal emulator, then reads its
    configuration file to extract the font family and size.
    Falls back to ('monospace', None).

    Supported terminals: Ghostty, Kitty, Alacritty, WezTerm, iTerm2,
    Windows Terminal.
    """
    import json
    import re

    import matplotlib.font_manager as fm

    available_fonts = {f.name for f in fm.fontManager.ttflist}
    term = os.environ.get("TERM_PROGRAM", "").lower()
    home = Path.home()
    font_name = None
    font_size = None

    def _parse_ghostty_config() -> None:
        """Read font-family and font-size from the Ghostty config file if present."""
        nonlocal font_name, font_size
        cfg = home / ".config" / "ghostty" / "config"
        if cfg.exists():
            for line in cfg.read_text().splitlines():
                line = line.strip()
                if line.startswith("#"):
                    continue
                if line.startswith("font-family") and not font_name:
                    font_name = line.split("=", 1)[1].strip().strip("\"'")
                elif line.startswith("font-size") and not font_size:
                    try:
                        font_size = float(line.split("=", 1)[1].strip().strip("\"'"))
                    except ValueError:
                        pass
            # Ghostty default font-size is 13
            if not font_size:
                font_size = 13.0

    try:
        if "ghostty" in term:
            _parse_ghostty_config()

        elif "kitty" in term:
            # ~/.config/kitty/kitty.conf:
            #   font_family Font Name
            #   font_size 12.0
            cfg = home / ".config" / "kitty" / "kitty.conf"
            if cfg.exists():
                for line in cfg.read_text().splitlines():
                    line = line.strip()
                    if line.startswith("font_family") and not font_name:
                        font_name = line.split(None, 1)[1].strip().strip("\"'")
                    elif line.startswith("font_size") and not font_size:
                        try:
                            font_size = float(line.split(None, 1)[1].strip())
                        except (ValueError, IndexError):
                            pass

        elif "alacritty" in term:
            # ~/.config/alacritty/alacritty.toml:
            #   [font] size = 12.0
            #   [font.normal] family = "Font"
            for name in ("alacritty.toml", "alacritty.yml"):
                cfg = home / ".config" / "alacritty" / name
                if cfg.exists():
                    text = cfg.read_text()
                    if name.endswith(".toml"):
                        m = re.search(
                            r'\[font\.normal\]\s*\n\s*family\s*=\s*["\']([^"\']+)',
                            text,
                        )
                        if m:
                            font_name = m.group(1)
                        m = re.search(
                            r"\[font\]\s*\n(?:.*\n)*?\s*size\s*=\s*([\d.]+)", text
                        )
                        if m:
                            font_size = float(m.group(1))
                    else:
                        m = re.search(
                            r'font:\s*\n\s*normal:\s*\n\s*family:\s*["\']?([^\n"\']+)',
                            text,
                        )
                        if m:
                            font_name = m.group(1).strip()
                        m = re.search(r"font:\s*\n(?:.*\n)*?\s*size:\s*([\d.]+)", text)
                        if m:
                            font_size = float(m.group(1))
                    if font_name:
                        break

        elif "wezterm" in term:
            # ~/.config/wezterm/wezterm.lua or ~/.wezterm.lua:
            #   font = wezterm.font("Font Name")
            #   font_size = 12.0
            for cfg in (
                home / ".config" / "wezterm" / "wezterm.lua",
                home / ".wezterm.lua",
            ):
                if cfg.exists():
                    text = cfg.read_text()
                    m = re.search(
                        r'font\s*=\s*wezterm\.font\s*\(\s*["\']([^"\']+)', text
                    )
                    if m:
                        font_name = m.group(1)
                    m = re.search(r"font_size\s*=\s*([\d.]+)", text)
                    if m:
                        font_size = float(m.group(1))
                    if font_name:
                        break

        elif "iterm" in term:
            # macOS: defaults read com.googlecode.iterm2
            if platform.system() == "Darwin":
                result = subprocess.run(
                    ["defaults", "read", "com.googlecode.iterm2", "Normal Font"],
                    capture_output=True,
                    text=True,
                    timeout=2,
                )
                if result.returncode == 0:
                    # Output like: "HackNF-Regular 13"
                    raw = result.stdout.strip()
                    parts = raw.rsplit(" ", 1)
                    font_name = parts[0].replace("-Regular", "")
                    if len(parts) == 2:
                        try:
                            font_size = float(parts[1])
                        except ValueError:
                            pass

        elif platform.system() == "Windows":
            # Windows Terminal: settings.json
            local_app = os.environ.get("LOCALAPPDATA", "")
            if local_app:
                wt_dir = Path(local_app) / "Packages"
                if wt_dir.exists():
                    for pkg in wt_dir.iterdir():
                        if "WindowsTerminal" in pkg.name:
                            settings = pkg / "LocalState" / "settings.json"
                            if settings.exists():
                                data = json.loads(settings.read_text())
                                profiles = data.get("profiles", {})
                                defaults = profiles.get("defaults", {})
                                font_cfg = defaults.get("font", {})
                                face = font_cfg.get("face")
                                if face:
                                    font_name = face
                                size = font_cfg.get("size")
                                if size:
                                    font_size = float(size)
                                break

        # Fallback: if TERM_PROGRAM didn't match any known terminal,
        # try detecting from config files that exist on disk.
        if not font_name:
            _parse_ghostty_config()

    except Exception:
        pass

    resolved_name = "monospace"
    if font_name:
        # Exact match first
        if font_name in available_fonts:
            resolved_name = font_name
        else:
            # Fuzzy match: try case-insensitive, then substring matching.
            # Nerd Font variants often register under slightly different names
            # (e.g. "SauceCodePro Nerd Font" vs "SauceCodePro Nerd Font Mono").
            lower_name = font_name.lower()
            for af in available_fonts:
                if af.lower() == lower_name:
                    resolved_name = af
                    break
            else:
                # Substring: pick the shortest available name that contains
                # the config name (or vice versa) to find the closest match
                candidates = [
                    af
                    for af in available_fonts
                    if lower_name in af.lower() or af.lower() in lower_name
                ]
                if candidates:
                    resolved_name = min(candidates, key=len)

    return resolved_name, font_size


def _truncate_path_intelligently(path_str: str, max_width: int) -> str:
    """
    Intelligently truncate a file path to fit within a given width.

    Strategy:
    1. If path fits, return as-is
    2. Progressively drop folders from the left (e.g., /a/b/c/file.txt -> .../b/c/file.txt -> .../c/file.txt)
    3. Try showing only first letter of remaining folders
    4. Try showing only filename (no folders)
    5. Truncate filename with ellipsis

    Args:
        path_str: The full path string
        max_width: Maximum character width

    Returns:
        Truncated path string
    """
    # Account for the 📁 emoji (2 chars) + space
    effective_width = max_width - 2

    if len(path_str) <= effective_width:
        return path_str

    path = Path(path_str)
    parts = list(path.parts)

    if len(parts) <= 1:
        # Just a filename, truncate with ellipsis
        filename = path.name
        if len(filename) > effective_width and effective_width > 3:
            return filename[: effective_width - 3] + "..."
        return filename[:effective_width]

    # Strategy 2: Progressively drop folders from the left
    for i in range(1, len(parts) - 1):
        truncated = ".../" + "/".join(parts[i:])
        if len(truncated) <= effective_width:
            return truncated

    # Strategy 3: First letter of remaining folders + full filename
    if len(parts) > 1:
        abbreviated = "/".join(p[0] for p in parts[:-1]) + "/" + parts[-1]
        if len(abbreviated) <= effective_width:
            return abbreviated
        # Try with ellipsis prefix
        abbreviated_with_ellipsis = (
            ".../"
            + "/".join(p[0] for p in parts[1:-1])
            + ("/" if len(parts) > 2 else "")
            + parts[-1]
        )
        if len(abbreviated_with_ellipsis) <= effective_width:
            return abbreviated_with_ellipsis

    # Strategy 4: Just the filename
    filename = path.name
    if len(filename) <= effective_width:
        return filename

    # Strategy 5: Truncate filename with ellipsis
    if effective_width > 3:
        return filename[: effective_width - 3] + "..."
    else:
        return filename[:effective_width]


def _calculate_plot_range_with_outlier_filtering(
    data: np.ndarray, outlier_percentile: float = 1.0, safety_margin: float = 0.05
) -> tuple[float, float]:
    """
    Calculate plot range while filtering out outliers.

    This prevents extreme outliers from compressing the useful data range.

    Args:
        data: Array of values to analyze
        outlier_percentile: Percentage of outliers to ignore on each end (default 2%)
        safety_margin: Additional margin beyond filtered range (default 5%)

    Returns:
        Tuple of (min_value, max_value) for plot range
    """
    if len(data) == 0:
        return (0.0, 1.0)

    # Calculate percentiles to filter outliers
    lower_percentile = outlier_percentile
    upper_percentile = 100.0 - outlier_percentile

    min_val = np.percentile(data, lower_percentile)
    max_val = np.percentile(data, upper_percentile)

    # Add safety margin
    data_range = max_val - min_val
    if data_range == 0:
        # Handle case where all values are the same
        data_range = abs(min_val) * 0.1 if min_val != 0 else 1.0

    margin = data_range * safety_margin
    min_val -= margin
    max_val += margin

    return (float(min_val), float(max_val))


def _unwrap_phase(phase_deg: np.ndarray) -> np.ndarray:
    """
    Unwrap phase data to remove discontinuities.

    Converts phase from [-180, 180] range to continuous values by removing
    360-degree jumps.

    Args:
        phase_deg: Phase data in degrees

    Returns:
        Unwrapped phase in degrees
    """
    # Convert to radians for numpy's unwrap function
    phase_rad = np.deg2rad(phase_deg)

    # Unwrap phase (removes 2*pi discontinuities)
    unwrapped_rad = np.unwrap(phase_rad)

    # Convert back to degrees
    unwrapped_deg = np.rad2deg(unwrapped_rad)

    return unwrapped_deg


def _create_matplotlib_plot(
    freqs: np.ndarray,
    sparams: dict,
    plot_params: list,
    plot_type: str,
    output_path: Path,
    dpi: int = 150,
    pixel_width: int | None = None,
    pixel_height: int | None = None,
    transparent: bool = False,
    render_scale: int = 1,
    colors: dict | None = None,
    y_min: float | None = None,
    y_max: float | None = None,
    font_family: str = "monospace",
    font_size: float | None = None,
) -> None:
    """
    Create a plot using matplotlib with dark theme matching terminal UI.

    Args:
        freqs: Frequency array in Hz
        sparams: Dictionary of S-parameters {param_name: (magnitude_db, phase_deg)}
        plot_params: List of parameters to plot (e.g., ['S11', 'S21'])
        plot_type: 'magnitude', 'phase', or 'phase_raw'
        output_path: Path to save the plot
        dpi: DPI for the output image
        pixel_width: Desired image width in pixels
        pixel_height: Desired image height in pixels
        transparent: If True, use transparent background
    """

    # Use the same font as the terminal for visual consistency
    font_family, font_size = _get_terminal_font()
    plt.rcParams["font.family"] = font_family
    # Base font size: use detected terminal size, or default to 10pt.
    # Divide by render_scale since we render at higher resolution and
    # the image gets scaled down for display.
    base_size = (font_size if font_size else 10.0) / render_scale

    if colors is None:
        colors = _get_plot_colors()
    fg_color = colors["fg"]
    grid_color = colors["grid"]

    # Calculate figure size in inches from pixel dimensions
    if pixel_width and pixel_height:
        fig_width = pixel_width / dpi
        fig_height = pixel_height / dpi
    else:
        fig_width = 10
        fig_height = 5

    # Create figure
    fig, ax = plt.subplots(figsize=(fig_width, fig_height))
    fig.patch.set_alpha(0.0 if transparent else 1.0)
    if not transparent:
        fig.patch.set_facecolor(colors["bg"])
    ax.set_facecolor("none" if transparent else colors["bg"])

    # Convert frequency to MHz
    freq_mhz = freqs / 1e6

    # Plot data based on plot type and collect all Y data for outlier filtering
    all_y_data = []
    for param in plot_params:
        if plot_type == "magnitude":
            data = sparams[param][0]  # Magnitude in dB
            ylabel = "Magnitude (dB)"
            title = "S-Parameter Magnitude"
        elif plot_type == "phase":
            data = _unwrap_phase(sparams[param][1])  # Unwrapped phase
            ylabel = "Phase (degrees)"
            title = "S-Parameter Phase (Unwrapped)"
        else:  # phase_raw
            data = sparams[param][1]  # Raw phase
            ylabel = "Phase (degrees)"
            title = "S-Parameter Phase (Raw)"

        all_y_data.append(data)
        ax.plot(
            freq_mhz,
            data,
            label=param,
            color=colors["traces"].get(param, colors["default_trace"]),
            linewidth=1.5,
        )

    # Apply outlier filtering to Y-axis range or use provided limits
    if all_y_data:
        combined_data = np.concatenate(all_y_data)
        if y_min is None or y_max is None:
            # Auto-detect if not provided
            auto_y_min, auto_y_max = _calculate_plot_range_with_outlier_filtering(
                combined_data, outlier_percentile=1.0, safety_margin=0.05
            )
            final_y_min = y_min if y_min is not None else auto_y_min
            final_y_max = y_max if y_max is not None else auto_y_max
        else:
            final_y_min = y_min
            final_y_max = y_max
        ax.set_ylim(final_y_min, final_y_max)

    # Styling — scale font sizes relative to detected terminal font
    ax.set_xlabel("Frequency (MHz)", color=fg_color, fontsize=base_size)
    ax.set_ylabel(ylabel, color=fg_color, fontsize=base_size)
    ax.set_title(title, color=fg_color, fontsize=base_size * 1.2, pad=15)
    ax.tick_params(colors=fg_color, labelsize=base_size * 0.85)
    ax.grid(True, alpha=0.2, color=grid_color, linestyle="-", linewidth=0.5)
    legend = ax.legend(
        edgecolor=grid_color,
        labelcolor=fg_color,
        fontsize=base_size * 0.9,
    )
    legend.get_frame().set_alpha(0.5 if transparent else 1.0)
    if not transparent:
        legend.get_frame().set_facecolor(colors["bg"])
    else:
        legend.get_frame().set_facecolor("none")

    # Spine colors
    for spine in ax.spines.values():
        spine.set_edgecolor(grid_color)
        spine.set_linewidth(1)

    # Tight layout
    plt.tight_layout()

    # Save figure
    plt.savefig(
        output_path,
        dpi=dpi,
        facecolor=fig.get_facecolor(),
        edgecolor="none",
        bbox_inches="tight",
        transparent=transparent,
    )
    plt.close(fig)


def _create_smith_chart(
    freqs: np.ndarray,
    sparams: dict,
    plot_params: list,
    output_path: Path,
    dpi: int = 150,
    pixel_width: int | None = None,
    pixel_height: int | None = None,
    transparent: bool = False,
    render_scale: int = 1,
    colors: dict | None = None,
) -> None:
    """
    Create a Smith chart using scikit-rf with dark theme matching terminal UI.

    Args:
        freqs: Frequency array in Hz
        sparams: Dictionary of S-parameters {param_name: (magnitude_db, phase_deg)}
        plot_params: List of parameters to plot (e.g., ['S11', 'S21'])
        output_path: Path to save the plot
        dpi: DPI for the output image
        pixel_width: Desired image width in pixels
        pixel_height: Desired image height in pixels
        transparent: If True, use transparent background
        render_scale: Scale factor for rendering (for high-DPI displays)
        colors: Color scheme dictionary
    """
    # Use the same font as the terminal for visual consistency
    font_family, font_size = _get_terminal_font()
    plt.rcParams["font.family"] = font_family
    base_size = (font_size if font_size else 10.0) / render_scale

    if colors is None:
        colors = _get_plot_colors()
    fg_color = colors["fg"]
    grid_color = colors["grid"]

    # Calculate figure size in inches from pixel dimensions
    # Smith charts MUST be square to display correctly
    if pixel_width and pixel_height:
        # Use the smaller dimension to create a square
        square_size_px = min(pixel_width, pixel_height)
        fig_width = square_size_px / dpi
        fig_height = square_size_px / dpi
    else:
        fig_width = 10
        fig_height = 10  # Square for Smith chart

    # Create figure with regular axes (scikit-rf doesn't use matplotlib projection)
    fig, ax = plt.subplots(figsize=(fig_width, fig_height))
    fig.patch.set_alpha(0.0 if transparent else 1.0)
    if not transparent:
        fig.patch.set_facecolor(colors["bg"])
    ax.set_facecolor("none" if transparent else colors["bg"])

    # Force square aspect ratio for Smith chart
    ax.set_aspect("equal")

    # Draw Smith chart grid with labels
    # chart_type: 'z' for impedance (default), 'y' for admittance
    # ref_imm: reference impedance (50 ohms standard)
    # draw_labels: show impedance/admittance values on grid
    rf.plotting.smith(
        ax=ax,
        chart_type="z",  # Impedance Smith chart
        draw_labels=True,  # Show grid labels
        ref_imm=50.0,  # 50 ohm reference impedance
        draw_vswr=None,  # Don't draw VSWR circles by default
    )

    # Mark special points on Smith chart
    # Open circuit (Γ = 1+0j, at right edge)
    # Short circuit (Γ = -1+0j, at left edge)
    # Matched load (Γ = 0+0j, at center)
    ax.scatter(
        [1.0],
        [0.0],
        marker="o",
        s=50,
        color=grid_color,
        edgecolor=fg_color,
        linewidth=1.5,
        zorder=10,
        label="Open",
    )
    ax.scatter(
        [-1.0],
        [0.0],
        marker="s",
        s=50,
        color=grid_color,
        edgecolor=fg_color,
        linewidth=1.5,
        zorder=10,
        label="Short",
    )
    ax.scatter(
        [0.0],
        [0.0],
        marker="*",
        s=100,
        color="gold",
        edgecolor=fg_color,
        linewidth=1.5,
        zorder=10,
        label="Match (50Ω)",
    )

    # Plot each S-parameter on Smith chart
    for param in plot_params:
        # Convert magnitude (dB) and phase (degrees) to complex reflection coefficient
        mag_db = sparams[param][0]
        phase_deg = sparams[param][1]

        # Convert dB to linear magnitude
        mag_linear = 10 ** (mag_db / 20)

        # Convert to complex reflection coefficient
        phase_rad = np.deg2rad(phase_deg)
        s_complex = mag_linear * np.exp(1j * phase_rad)

        # Create Network object from S-parameter data
        # scikit-rf expects frequency in Hz and S-parameters as complex arrays
        network = rf.Network(
            frequency=rf.Frequency.from_f(freqs, unit="Hz"),
            s=s_complex.reshape(-1, 1, 1),  # Shape: (n_freqs, n_ports, n_ports)
            name=param,
        )

        # Plot on Smith chart using scikit-rf's method
        trace_color = colors["traces"].get(param, colors["default_trace"])
        network.plot_s_smith(
            m=0,
            n=0,  # Plot S[0,0] (first port to first port)
            ax=ax,
            label=param,
            color=trace_color,
            linewidth=1.5,
            draw_labels=False,  # Don't draw frequency labels (too cluttered)
            show_legend=False,  # We'll create our own legend
        )

        # Add start/end frequency markers on the trace
        # Start frequency marker (triangle pointing right)
        ax.scatter(
            s_complex[0].real,
            s_complex[0].imag,
            marker=">",
            s=80,
            color=trace_color,
            edgecolor=fg_color,
            linewidth=1,
            zorder=15,
        )
        # End frequency marker (square)
        ax.scatter(
            s_complex[-1].real,
            s_complex[-1].imag,
            marker="s",
            s=60,
            color=trace_color,
            edgecolor=fg_color,
            linewidth=1,
            zorder=15,
        )

        # Annotate start frequency
        freq_start_mhz = freqs[0] / 1e6
        freq_end_mhz = freqs[-1] / 1e6
        ax.annotate(
            f"{freq_start_mhz:.0f} MHz",
            (s_complex[0].real, s_complex[0].imag),
            xytext=(10, 10),
            textcoords="offset points",
            color=trace_color,
            fontsize=base_size * 0.7,
            bbox=dict(
                boxstyle="round,pad=0.3",
                facecolor=colors["bg"],
                edgecolor=trace_color,
                alpha=0.8,
            ),
        )
        # Annotate end frequency
        ax.annotate(
            f"{freq_end_mhz:.0f} MHz",
            (s_complex[-1].real, s_complex[-1].imag),
            xytext=(-10, -10),
            textcoords="offset points",
            color=trace_color,
            fontsize=base_size * 0.7,
            bbox=dict(
                boxstyle="round,pad=0.3",
                facecolor=colors["bg"],
                edgecolor=trace_color,
                alpha=0.8,
            ),
        )

    # Customize Smith chart appearance
    ax.set_title("Smith Chart", color=fg_color, fontsize=base_size * 1.2, pad=15)

    # Update Smith chart grid colors to match theme
    # The Smith chart uses matplotlib collections for grid
    for collection in ax.collections:
        collection.set_edgecolor(grid_color)
        collection.set_alpha(0.3)

    # Update text colors
    for text in ax.texts:
        text.set_color(fg_color)
        text.set_fontsize(base_size * 0.7)

    # Create legend
    if len(plot_params) > 0:
        legend = ax.legend(
            edgecolor=grid_color,
            labelcolor=fg_color,
            fontsize=base_size * 0.9,
            loc="upper right",
        )
        legend.get_frame().set_alpha(0.5 if transparent else 1.0)
        if not transparent:
            legend.get_frame().set_facecolor(colors["bg"])
        else:
            legend.get_frame().set_facecolor("none")

    # Tight layout
    plt.tight_layout()

    # Save figure
    plt.savefig(
        output_path,
        dpi=dpi,
        facecolor=fig.get_facecolor(),
        edgecolor="none",
        bbox_inches="tight",
        transparent=transparent,
    )
    plt.close(fig)


class UpdateNotificationScreen(ModalScreen):
    """Reusable modal for update-related notifications (new release or post-update welcome)."""

    DEFAULT_CSS = """
    UpdateNotificationScreen {
        align: center middle;
    }
    #notif-dialog {
        width: 70;
        height: auto;
        background: $surface;
        border: thick $primary;
        padding: 1 2;
    }
    UpdateNotificationScreen.--welcome #notif-dialog {
        border: thick $success;
    }
    UpdateNotificationScreen #notif-title {
        text-style: bold;
        width: 1fr;
    }
    UpdateNotificationScreen.--welcome #notif-title {
        color: $success;
    }
    UpdateNotificationScreen #notif-badge {
        margin-left: 1;
    }
    UpdateNotificationScreen .badge-stable {
        background: $success;
        color: $background;
        padding: 0 1;
    }
    UpdateNotificationScreen .badge-pre {
        background: $warning;
        color: $background;
        padding: 0 1;
    }
    UpdateNotificationScreen #notif-body {
        height: auto;
        max-height: 60vh;
        border: solid $panel;
        padding: 0 1;
        margin: 0;
    }
    UpdateNotificationScreen #notif-body Markdown {
        margin: 0;
        padding: 0;
    }
    UpdateNotificationScreen #notif-body Markdown > * {
        margin-top: 0;
    }
    UpdateNotificationScreen #notif-footer {
        height: auto;
        align-horizontal: right;
    }
    """

    def __init__(
        self,
        title: str,
        body: str,
        button_label: str,
        button_variant: str = "primary",
        badge: str | None = None,
        badge_class: str | None = None,
        welcome: bool = False,
    ) -> None:
        """Initialise the notification screen with title, markdown body, and button config."""
        super().__init__()
        self._title = title
        self._body = body or "_No changelog provided._"
        self._button_label = button_label
        self._button_variant = button_variant
        self._badge = badge
        self._badge_class = badge_class
        if welcome:
            self.add_class("--welcome")

    def compose(self) -> ComposeResult:
        """Compose the modal layout: title row, scrollable body, and dismiss button."""
        with Vertical(id="notif-dialog"):
            with Horizontal():
                yield Label(self._title, id="notif-title")
                if self._badge:
                    yield Label(
                        f" {self._badge} ",
                        id="notif-badge",
                        classes=self._badge_class or "",
                    )
            with VerticalScroll(id="notif-body"):
                yield Markdown(self._body)
            with Horizontal(id="notif-footer"):
                yield Button(
                    self._button_label,
                    variant=self._button_variant,
                    id="btn-notif-dismiss",
                )

    @on(Button.Pressed, "#btn-notif-dismiss")
    def dismiss_notification(self) -> None:
        """Dismiss the modal when the button is pressed."""
        self.dismiss()


# ---------------------------------------------------------------------------
# Help viewer helpers
# ---------------------------------------------------------------------------


def _pixel_graphics_available() -> bool:
    """Return True only if the terminal supports real pixel graphics (Sixel or Kitty TGP).

    Half-cell and Unicode block renderers are excluded — they are not acceptable
    quality for mathematical notation.
    """
    if not TEXTUAL_IMAGE_AVAILABLE:
        return False
    try:
        from textual_image.renderable import Image as _AutoRenderable
        from textual_image.renderable.sixel import Image as _SixelRenderable
        from textual_image.renderable.tgp import Image as _TGPRenderable

        return _AutoRenderable in (_SixelRenderable, _TGPRenderable)
    except Exception:
        return False


def _preprocess_inline_latex(text: str) -> str:
    """Convert inline ``$...$`` math spans to backtick-wrapped Unicode text.

    Each ``$expr$`` is replaced with `` `unicode` `` so Textual's
    ``Markdown`` widget renders it as inline code rather than raw LaTeX.
    When *pylatexenc* is unavailable the raw expression is kept as-is inside
    the backticks.  Cross-line spans (containing a newline) are intentionally
    left untouched.

    Args:
        text: A markdown text segment that may contain ``$...$`` spans.
            Must NOT contain ``$$...$$`` display-math blocks (those are split
            out before this function is called in ``HelpScreen.compose``).

    Returns:
        The text with all inline math spans converted to backtick strings.
    """
    if _latex_converter is None:
        return re.sub(r"\$([^$\n]+?)\$", r"`\1`", text)

    def replace_inline(m: re.Match) -> str:
        return f"`{_latex_converter.latex_to_text(m.group(1)).strip()}`"

    return re.sub(r"\$([^$\n]+?)\$", replace_inline, text)


class HelpScreen(ModalScreen):
    """Help viewer modal with hybrid LaTeX rendering.

    Display math ($$...$$) is rendered as a matplotlib image when the terminal
    supports graphics, with a plain-text code-block fallback.  Inline math
    ($...$) is always converted to Unicode via pylatexenc.
    """

    DEFAULT_CSS = """
    HelpScreen {
        align: center middle;
    }
    #help-dialog {
        width: 90%;
        height: 90%;
        background: $surface;
        border: thick $primary;
        padding: 1 2;
    }
    #help-title {
        text-style: bold;
        color: $primary;
        width: 1fr;
    }
    #help-body {
        height: 1fr;
        border: solid $panel;
        padding: 0 1;
        margin: 0;
    }
    #help-body Markdown {
        margin: 0;
        padding: 0;
    }
    #help-body Markdown > * {
        margin-top: 0;
    }
    .math-img-row {
        height: auto;
        width: 100%;
        align-horizontal: center;
        margin: 0 0 1 0;
    }
    #help-footer {
        height: auto;
        align-horizontal: right;
    }
    """

    def __init__(self, title: str, content: str) -> None:
        """Initialise the help viewer.

        Args:
            title: Heading shown at the top of the modal.
            content: Raw markdown text, optionally containing ``$$...$$``
                display-math blocks and ``$...$`` inline math.
        """
        super().__init__()
        self._title = title
        self._raw_content = content
        self._temp_files: list[Path] = []

    @staticmethod
    def _prep_for_mathtext(expr: str) -> str:
        """Sanitise a LaTeX expression for matplotlib's mathtext engine.

        matplotlib's mathtext parser is a strict subset of LaTeX.  This method
        rewrites or removes constructs that would cause a ``ParseFatalException``:

        * ``\\boxed{…}`` — unsupported; command is stripped, braced content kept.
        * ``\\text{…}`` — replaced with ``\\mathrm{…}`` which mathtext supports.
        * ``\\lvert`` / ``\\rvert`` — replaced with plain ``|``.
        * Size decorators (``\\bigl``, ``\\bigr``, ``\\left``, ``\\right``, …) — removed.
        * ``\\max_{…}`` / ``\\min_{…}`` — subscript dropped; bare ``\\max``/``\\min`` kept.

        Args:
            expr: Raw LaTeX string (without surrounding ``$`` delimiters).

        Returns:
            Sanitised expression safe to pass to ``fig.text(… usetex=False)``.
        """
        # \boxed is unsupported — drop the command, keep the braced content as a group
        expr = expr.replace("\\boxed", "")
        # \text{X} -> \mathrm{X}  (mathtext supports \mathrm)
        expr = re.sub(r"\\text\{([^{}]*)\}", r"\\mathrm{\1}", expr)
        # \lvert \rvert -> |
        expr = expr.replace("\\lvert", "|").replace("\\rvert", "|")
        # Size/bracket decorators that confuse the parser
        for cmd in ("\\bigl", "\\bigr", "\\Bigl", "\\Bigr", "\\left", "\\right"):
            expr = expr.replace(cmd, "")
        # \max / \min with subscripts — drop the subscript
        expr = re.sub(r"\\(max|min)_\{[^{}]*\}", r"\\\1", expr)
        return expr

    def _render_math_image(self, latex_expr: str) -> tuple[Path, int, int] | None:
        """Render a display-math expression to a tightly cropped temp PNG.

        Returns (path, pixel_width, pixel_height) on success, or None on failure.
        Renders on a transparent background then uses the alpha channel for
        pixel-precise cropping via Pillow, before compositing onto the theme
        surface colour.  Uses a monospace font context and sanitises the
        expression for matplotlib's mathtext engine.
        """
        try:
            from io import BytesIO

            from PIL import Image as PILImage
            from PIL import ImageColor

            v = self.app.get_css_variables()
            bg_hex = v.get("surface", "#1a1a1a")
            fg_hex = v.get("foreground", "#ffffff")

            expr = self._prep_for_mathtext(latex_expr.strip())

            with plt.rc_context({"font.family": "monospace"}):
                fig = plt.figure(figsize=(9, 1.5))
                fig.patch.set_facecolor("none")
                fig.text(
                    0.5,
                    0.5,
                    f"${expr}$",
                    ha="center",
                    va="center",
                    fontsize=14,
                    color=fg_hex,
                    usetex=False,
                )
                buf = BytesIO()
                fig.savefig(
                    buf,
                    format="png",
                    dpi=130,
                    bbox_inches="tight",
                    pad_inches=0.05,
                    transparent=True,
                )
                plt.close(fig)

            buf.seek(0)
            img = PILImage.open(buf).convert("RGBA")

            # Alpha-based crop — transparent pixels are background
            _, _, _, alpha = img.split()
            content_bbox = alpha.getbbox()
            if content_bbox:
                pad_px = 5
                content_bbox = (
                    max(0, content_bbox[0] - pad_px),
                    max(0, content_bbox[1] - pad_px),
                    min(img.width, content_bbox[2] + pad_px),
                    min(img.height, content_bbox[3] + pad_px),
                )
                img = img.crop(content_bbox)

            # Composite onto solid theme background
            bg_rgba = ImageColor.getrgb(bg_hex) + (255,)
            bg_layer = PILImage.new("RGBA", img.size, bg_rgba)
            final = PILImage.alpha_composite(bg_layer, img)

            fd, tmp_path = tempfile.mkstemp(suffix=".png")
            os.close(fd)
            final.convert("RGB").save(tmp_path, "PNG")
            tmp = Path(tmp_path)
            self._temp_files.append(tmp)
            return tmp, final.width, final.height
        except Exception:
            plt.close("all")
            return None

    def compose(self) -> ComposeResult:
        """Compose the help modal, rendering display math as pixel images where possible."""
        use_images = _pixel_graphics_available()
        parts = re.split(r"\$\$(.*?)\$\$", self._raw_content, flags=re.DOTALL)
        with Vertical(id="help-dialog"):
            yield Label(self._title, id="help-title")
            with VerticalScroll(id="help-body"):
                for i, part in enumerate(parts):
                    if i % 2 == 0:
                        # Text segment — convert inline math to Unicode
                        processed = _preprocess_inline_latex(part)
                        if processed.strip():
                            yield Markdown(processed)
                    else:
                        # Display math — pixel image or plain-text fallback
                        result = self._render_math_image(part) if use_images else None
                        if result is not None:
                            img_path, img_w_px, img_h_px = result
                            try:
                                from textual_image.widget._base import (
                                    get_cell_size as _gtcs,
                                )

                                tc = _gtcs()
                                cw = tc.width if tc.width > 0 else 8
                                ch = tc.height if tc.height > 0 else 16
                            except Exception:
                                cw, ch = 8, 16
                            w_cells = max(8, round(img_w_px / cw))
                            h_cells = max(1, round(img_h_px / ch))
                            img_widget = ImageWidget(str(img_path))
                            img_widget.styles.width = w_cells
                            img_widget.styles.height = h_cells
                            with Horizontal(classes="math-img-row"):
                                yield img_widget
                        else:
                            fallback = (
                                _latex_converter.latex_to_text(part).strip()
                                if _latex_converter is not None
                                else part.strip()
                            )
                            yield Markdown(f"\n```\n{fallback}\n```\n")
            with Horizontal(id="help-footer"):
                yield Button("Close", variant="primary", id="btn-help-close")

    def on_unmount(self) -> None:
        """Remove temporary math image files."""
        for f in self._temp_files:
            try:
                f.unlink(missing_ok=True)
            except Exception:
                pass

    @on(Button.Pressed, "#btn-help-close")
    def close_help(self) -> None:
        """Dismiss the help modal."""
        self.dismiss()


def _update_screen(release_info) -> UpdateNotificationScreen:
    """Build an UpdateNotificationScreen for a new-release notification."""
    rel = release_info
    if rel.is_prerelease:
        intro = f"A new pre-release **v{rel.version}** is available.\n\n"
        body = intro + (
            rel.changelog if rel.changelog else f"[View on GitHub]({rel.html_url})"
        )
        badge, badge_class = "PRE-RELEASE", "badge-pre"
    else:
        body = rel.changelog or "_No changelog provided._"
        badge, badge_class = "STABLE", "badge-stable"
    return UpdateNotificationScreen(
        title=f"Update available:  v{rel.version}",
        body=body,
        button_label="Dismiss",
        badge=badge,
        badge_class=badge_class,
    )


def _welcome_screen(version: str, changelog: str) -> UpdateNotificationScreen:
    """Build an UpdateNotificationScreen for the post-update welcome."""
    return UpdateNotificationScreen(
        title=f"Thanks for updating to v{version}!",
        body=changelog,
        button_label="Got it!",
        button_variant="success",
        welcome=True,
    )


_POLL_OPTIONS = [
    ("Status poll: Off", 0),
    ("Status poll: 1 second", 1),
    ("Status poll: 2 seconds", 2),
    ("Status poll: 5 seconds", 5),
    ("Status poll: 10 seconds", 10),
    ("Status poll: 30 seconds", 30),
]


class StatusPollProvider(Provider):
    """Command palette provider for changing the status bar poll interval."""

    async def discover(self) -> Hits:
        """Yield all available poll-interval options unconditionally."""
        for label, value in _POLL_OPTIONS:
            yield Hit(
                1.0,
                label,
                partial(self._apply, value),
                help="Set status bar refresh interval",
            )

    async def search(self, query: str) -> Hits:
        """Yield poll-interval options whose labels match *query*."""
        matcher = self.matcher(query)
        for label, value in _POLL_OPTIONS:
            score = matcher.match(label)
            if score > 0:
                yield Hit(score, matcher.highlight(label), partial(self._apply, value))

    def _apply(self, value: int) -> None:
        """Apply the selected poll interval to settings and restart the poll timer."""
        app = self.app
        app.settings.status_poll_interval = value
        app.query_one("#sb_poll_interval", Select).value = value
        if app.connected:
            app._start_status_polling(value)


_BACKEND_OPTIONS = [
    ("Plot backend: Terminal", "terminal"),
    ("Plot backend: Image", "image"),
]


class PlotBackendProvider(Provider):
    """Command palette provider for switching the global plot backend."""

    async def discover(self) -> Hits:
        """Yield all backend options unconditionally."""
        for label, value in _BACKEND_OPTIONS:
            yield Hit(
                1.0,
                label,
                partial(self._apply, value),
                help="Set plot rendering backend",
            )

    async def search(self, query: str) -> Hits:
        """Yield backend options whose labels match *query*."""
        matcher = self.matcher(query)
        for label, value in _BACKEND_OPTIONS:
            score = matcher.match(label)
            if score > 0:
                yield Hit(score, matcher.highlight(label), partial(self._apply, value))

    def _apply(self, value: str) -> None:
        """Apply the selected backend globally and refresh the plot."""
        app = self.app
        app.settings.plot_backend = value
        app._update_plot_type_options()
        app.settings_manager.save(app.settings)
        if app.last_measurement is not None:
            app.call_after_refresh(
                app._update_results,
                app.last_measurement["freqs"],
                app.last_measurement["sparams"],
                app.last_measurement["output_path"],
            )


_CURSOR_MARKER_OPTIONS = [
    ("Cursor marker: ▼ (arrow down)", "▼"),
    ("Cursor marker: ✕ (cross)", "✕"),
    ("Cursor marker: ○ (circle)", "○"),
]


class CursorMarkerProvider(Provider):
    """Command palette provider for selecting the cursor marker symbol."""

    async def discover(self) -> Hits:
        for label, value in _CURSOR_MARKER_OPTIONS:
            yield Hit(
                1.0,
                label,
                partial(self._apply, value),
                help="Set cursor marker style for Tools tab",
            )

    async def search(self, query: str) -> Hits:
        matcher = self.matcher(query)
        for label, value in _CURSOR_MARKER_OPTIONS:
            score = matcher.match(label)
            if score > 0:
                yield Hit(score, matcher.highlight(label), partial(self._apply, value))

    def _apply(self, value: str) -> None:
        app = self.app
        app.settings.cursor_marker_style = value
        app.settings_manager.save(app.settings)
        if app.last_measurement is not None:
            app.call_after_refresh(app._refresh_tools_plot)


_SB_ITEMS = ("sb_cal", "sb_smooth", "sb_ifbw", "sb_power", "sb_trigger")

# Short human-readable names for common SCPI error codes (IEEE 488.2 / SCPI 1999).
_SCPI_ERROR_NAMES: dict[str, str] = {
    "+0": "OK",
    "0": "OK",
    "-100": "CMD",
    "-113": "UNDEF",
    "-222": "RANGE",
    "-224": "ILLEGAL",
    "-310": "SYS",
    "-350": "QUEUE",
    "-400": "QUERY",
    "-420": "UNTMN",
    "-430": "DEADLK",
}


def _scpi_mnemonic(cmd: str) -> str:
    """Return a compact display mnemonic for a SCPI command.

    Strips parameter values (text after a space), trailing ``?``, and any
    channel-number suffix on the first node (e.g. ``SENS1`` → removed so
    ``SENS1:CORR:STAT?`` becomes ``CORR:STAT``).
    """
    base = cmd.split(" ")[0].rstrip("?")
    parts = base.split(":")
    if parts and parts[0] and parts[0][-1].isdigit():
        parts = parts[1:]
    return ":".join(parts) or base


_ALL_SB_STATE_CLASSES = (
    "--stale",
    "--state-ok",
    "--state-off",
    "--smo-on",
    "--trig-INT",
    "--trig-MAN",
    "--trig-EXT",
    "--trig-BUS",
)


class StatusFooter(Footer):
    """Textual Footer with VNA status items appended after the key bindings."""

    DEFAULT_CSS = Footer.DEFAULT_CSS + """
    StatusFooter #sb_spacer {
        width: 1fr;
        height: 1;
    }
    StatusFooter #sb_status_container {
        width: auto;
        height: 1;
        padding: 0 1 0 0;
    }
    StatusFooter .sb-item {
        width: auto;
        height: 1;
        padding: 0 1;
        content-align: left middle;
        background: $panel-lighten-1;
    }
    StatusFooter .sb-sep {
        width: 1;
        height: 1;
    }
    StatusFooter .sb-item.--stale {
        background: $panel-lighten-1;
        color: $text-muted;
        text-style: dim;
    }
    StatusFooter .sb-item.--state-ok  { background: $success;   color: $background; }
    StatusFooter .sb-item.--state-off { background: $error;     color: $background; }
    StatusFooter .sb-item.--smo-on    { background: $accent;    color: $background; }
    StatusFooter .sb-item.--trig-INT  { background: $primary;   color: $background; }
    StatusFooter .sb-item.--trig-MAN  { background: $warning;   color: $background; }
    StatusFooter .sb-item.--trig-EXT  { background: $secondary; color: $background; }
    StatusFooter .sb-item.--trig-BUS  { background: $success;   color: $background; }
    StatusFooter #sb_debug_group {
        display: none;
        width: auto;
        height: 1;
    }
    StatusFooter #sb_debug_group.--visible {
        display: block;
    }
    """

    # Initial placeholder text shown before first poll
    _PLACEHOLDERS: dict[str, str] = {
        "sb_cal": "CAL",
        "sb_smooth": "SMTH",
        "sb_ifbw": "IFBW",
        "sb_power": "PWR",
        "sb_trigger": "TRIG",
    }

    def __init__(self, **kwargs):
        """Initialise state stores for chip text/class and debug chip visibility."""
        super().__init__(**kwargs)
        # (text, css_class) — class "" means no coloured background
        self._sb_state: dict[str, tuple[str, str]] = {
            k: (self._PLACEHOLDERS[k], "--stale") for k in _SB_ITEMS
        }
        # Debug chip state — persists across Footer recomposes
        self._debug_visible: bool = False
        self._debug_chip_state: tuple[str, str] = ("ERR OK", "--state-ok")

    def compose(self) -> ComposeResult:
        """Build footer: key bindings (left), debug chip, spacer, status chips (right)."""
        yield from super().compose()  # q Quit leftmost; ^p palette docked right
        # Debug error chip — left-aligned next to q Quit, hidden until debug active.
        # Classes are set from stored state so recomposes (triggered by Footer
        # internals on focus changes) preserve visibility and chip content.
        debug_text, debug_css = self._debug_chip_state
        grp_classes = "--visible" if self._debug_visible else ""
        with Horizontal(id="sb_debug_group", classes=grp_classes):
            yield Static(" ", classes="sb-sep")
            yield Static(
                debug_text,
                id="sb_lasterr",
                classes=f"sb-item {debug_css}".strip(),
            )
        yield Static("", id="sb_spacer")  # pushes status items to the right
        with Horizontal(id="sb_status_container"):
            for i, item_id in enumerate(_SB_ITEMS):
                if i > 0:
                    yield Static(" ", classes="sb-sep")
                text, css_class = self._sb_state[item_id]
                yield Static(text, id=item_id, classes=f"sb-item {css_class}".strip())

    def _set_item(self, item_id: str, text: str, css_class: str = "") -> None:
        """Update a single status chip's text and CSS class in state and in the DOM."""
        self._sb_state[item_id] = (text, css_class)
        try:
            w = self.query_one(f"#{item_id}", Static)
            w.update(text)
            w.remove_class(*_ALL_SB_STATE_CLASSES)
            if css_class:
                w.add_class(css_class)
        except Exception:
            pass

    def _apply_debug_chip(self) -> None:
        """Push stored debug chip state to the live widgets."""
        try:
            self.query_one("#sb_debug_group").set_class(
                self._debug_visible, "--visible"
            )
            # Only update chip content when visible — avoids a colour flash
            # when the group is being hidden (class change rendered before hide).
            if not self._debug_visible:
                return
            text, css_class = self._debug_chip_state
            chip = self.query_one("#sb_lasterr", Static)
            chip.update(text)
            chip.remove_class(*_ALL_SB_STATE_CLASSES)
            if css_class:
                chip.add_class(css_class)
        except Exception:
            pass

    def set_disconnected(self) -> None:
        """Mark all items as stale; preserve last-known text."""
        for item_id in _SB_ITEMS:
            text, _ = self._sb_state[item_id]
            self._sb_state[item_id] = (text, "--stale")
            try:
                w = self.query_one(f"#{item_id}", Static)
                w.remove_class(*_ALL_SB_STATE_CLASSES)
                w.add_class("--stale")
            except Exception:
                pass
        # Gray out debug chip while disconnected
        prev_text, _ = self._debug_chip_state
        self._debug_chip_state = (prev_text, "--stale")
        self._apply_debug_chip()

    def set_debug_mode(self, enabled: bool, connected: bool = True) -> None:
        """Show or hide the last-error debug chip."""
        self._debug_visible = enabled
        if not enabled:
            self._debug_chip_state = ("ERR OK", "--state-ok")
        elif not connected:
            self._debug_chip_state = ("ERR OK", "--stale")
        self._apply_debug_chip()

    def update_last_error(self, command: str, raw_error: str) -> None:
        """Update the debug error chip from a SYST:ERR? response.

        Args:
            command:   The SCPI command that preceded the SYST:ERR? check.
            raw_error: Stripped SYST:ERR? response, e.g. ``+0,"No error"``
                       or ``-113,"Undefined header"``.
        """
        if raw_error.startswith("+0") or raw_error.startswith("0,"):
            self._debug_chip_state = ("ERR OK", "--state-ok")
        else:
            code = raw_error.split(",")[0].strip()
            name = _SCPI_ERROR_NAMES.get(code, code)
            mnem = _scpi_mnemonic(command)
            self._debug_chip_state = (f"{mnem} {name}", "--state-off")
        self._apply_debug_chip()

    def update_status(self, result: "StatusResult") -> None:
        """Refresh all status chips from a fresh StatusResult."""
        # Calibration
        if result.cal_enabled is None:
            self._set_item("sb_cal", self._sb_state["sb_cal"][0], "--stale")
        elif result.cal_enabled:
            self._set_item("sb_cal", (result.cal_type or "CAL").strip(), "--state-ok")
        else:
            self._set_item("sb_cal", "CAL", "--state-off")

        # Smoothing
        if result.smoothing_enabled is None:
            self._set_item("sb_smooth", self._sb_state["sb_smooth"][0], "--stale")
        elif result.smoothing_enabled and result.smoothing_aperture is not None:
            self._set_item(
                "sb_smooth", f"SMTH {result.smoothing_aperture:.1f}%", "--smo-on"
            )
        else:
            self._set_item("sb_smooth", "SMTH", "--state-off")

        # IF bandwidth
        hz = result.if_bandwidth_hz
        if hz is None:
            self._set_item("sb_ifbw", self._sb_state["sb_ifbw"][0], "--stale")
        elif hz >= 1e6:
            self._set_item("sb_ifbw", f"{hz / 1e6:.3g} MHz")
        elif hz >= 1e3:
            self._set_item("sb_ifbw", f"{hz / 1e3:.3g} kHz")
        else:
            self._set_item("sb_ifbw", f"{hz:.3g} Hz")

        # Port power
        if result.port_power_dbm is None:
            self._set_item("sb_power", self._sb_state["sb_power"][0], "--stale")
        else:
            self._set_item("sb_power", f"{result.port_power_dbm:+.1f} dBm")

        # Trigger source
        if result.trigger_source is None:
            self._set_item("sb_trigger", self._sb_state["sb_trigger"][0], "--stale")
        else:
            src = result.trigger_source.strip().upper()
            css = f"--trig-{src}" if f"--trig-{src}" in _ALL_SB_STATE_CLASSES else ""
            self._set_item("sb_trigger", src, css)


class VNAApp(App):
    """tina - Terminal uI Network Analyzer"""

    # Maps log level names to their filter checkbox widget IDs.
    # Both primary and secondary levels are listed here; composite levels
    # (e.g. "tx/poll") require both halves to be enabled to show.
    _LOG_FILTER_IDS: dict[str, str] = {
        "tx": "#check_log_tx",
        "rx": "#check_log_rx",
        "info": "#check_log_info",
        "progress": "#check_log_progress",
        "success": "#check_log_success",
        "error": "#check_log_error",
        "debug": "#check_log_debug",
        "poll": "#check_log_poll",
    }

    CSS = """
    Screen {
        background: $surface;
    }

    #content {
        height: 100%;
        margin: 1;
        margin-bottom: 0;
    }

    .panel {
        border: solid $primary;
        border-title-color: $accent;
        border-title-style: bold;
        height: auto;
        padding: 0 1;
        margin-bottom: 1;
    }

    .field {
        height: auto;
        margin-bottom: 0;
        align: left middle;
    }

    .field Label {
        width: auto;
        padding-right: 1;
        content-align: left middle;
        height: 100%;
    }

    .field Input {
        width: 1fr;
    }

    .field Select {
        width: 1fr;
    }

    .field Checkbox {
        width: auto;
        margin-right: 2;
        height: 3;
        border: none;
        content-align: left middle;
    }

    Checkbox {
        border: none;
        height: 3;
        content-align: left middle;
    }

    .param-row {
        height: 3;
        margin-bottom: 0;
        align: left middle;
    }

    .param-row .col-label {
        width: 12;
        content-align: left middle;
        height: 100%;
    }

    .param-row Label {
        content-align: center middle;
        height: 100%;
    }

    .param-row .col-input {
        width: 1fr;
    }

    .param-row .col-input Input {
        width: 1fr;
    }

    .param-row .col-check {
        width: 17;
    }

    .filter-row {
        height: auto;
    }

    .filter-row Checkbox {
        width: auto;
        margin-right: 0;
    }

    .filter-spacer {
        width: 1fr;
    }

    .secondary-filter {
        opacity: 0.5;
    }

    .button-group {
        height: auto;
        margin-top: 1;
        margin-bottom: 0;
        align: center middle;
    }

    Button {
        margin: 1 0 0 0;
        width: 100%;
    }

    .plot-controls {
        height: auto;
        margin-bottom: 0;
        align: left middle;
    }

    .plot-controls Label {
        width: auto;
        padding-right: 1;
        content-align: left middle;
        height: 3;
    }

    .plot-controls Select {
        width: 20;
        margin-right: 2;
    }

    .plot-controls Checkbox {
        width: auto;
        margin-right: 1;
        height: 3;
        border: none;
    }

    .plot-controls .spacer {
        width: 1fr;
    }

    .plot-controls Button {
        width: auto;
        min-width: 8;
        margin-left: 1;
    }

    .plot-controls Input {
        width: 1fr;
        margin-right: 1;
    }

    .span-axis-group {
        width: 1fr;
        height: auto;
        margin-right: 2;
    }

    .span-axis-group:last-child {
        margin-right: 0;
    }

    #btn_reset_freq_limits,
    #btn_reset_y_limits,
    #btn_apply_limits {
        padding: 0 2;
    }

    #btn_import_results {
        min-width: 16;
    }

    #btn_open_output,
    #btn_export_png,
    #btn_export_svg {
        width: auto;
        min-width: 12;
    }

    #output_file_label {
        width: auto;
        height: 3;
        content-align: left middle;
    }

    #controls_panel {
        dock: bottom;
        width: 100%;
        height: auto;
        margin: 0;
        padding: 0;
        border: none;
    }

    #action_bar {
        width: 100%;
        height: auto;
        align: right middle;
        background: $boost;
        padding: 0 1 1 1;
    }

    #progress_container {
        width: 1fr;
        height: auto;
    }

    #progress_container {
        width: 1fr;
        height: auto;
        padding: 0;
        margin: 0;
    }

    #progress_label {
        height: 1;
        padding: 0;
        margin: 0;
    }

    #progress_bar {
        width: 100%;
        height: 1;
        padding: 0;
        margin: 0;
    }

    #progress_bar PercentageStatus {
        display: none;
    }

    #progress_bar ETAStatus {
        display: none;
    }

    #progress_bar Bar {
        width: 1fr;
        height: 1;
    }

    #progress_bar Bar > .bar--indeterminate {
        color: $surface-lighten-1;
    }

    #progress_bar Bar > .bar--background {
        color: $surface-lighten-1;
    }

    #progress_bar Bar > .bar--bar {
        color: $primary;
    }

    #progress_bar Bar > .bar--complete {
        color: $success;
    }

    #action_bar Button {
        width: auto;
        min-width: 16;
        margin: 0 0 0 1;
        height: 2;
        border: none;
        padding: 0 2;
    }

    .spacer {
        width: 1fr;
    }

    #log_content {
        height: 1fr;
        border: solid $primary;
        border-title-color: $accent;
        border-title-style: bold;
        margin: 1 0 0 0;
    }


    #results_text {
        height: 100%;
        padding: 1;
    }

    TabbedContent {
        height: 100%;
    }

    #footer_separator {
        dock: bottom;
        height: 1;
        background: $secondary;
    }

    .log-info {
        color: $text;
    }

    .log-success {
        color: $success;
    }

    .log-error {
        color: $error;
    }

    .log-progress {
        color: $warning;
    }

    .log-tx {
        color: $accent;
    }

    .log-rx {
        color: $primary;
    }

    DataTable {
        width: 100%;
        height: auto;
    }

    #results_container {
        width: 100%;
        align: center top;
    }

    PlotextPlot {
        width: 100%;
        height: 25;
        margin: 1 0;
    }

    ImageWidget {
        margin: 1 0;
    }

    #tools_plot_container {
        width: 100%;
        align: center top;
        height: auto;
        padding: 0;
    }

    #tools_plot_placeholder, #results_plot_placeholder {
        padding: 1 1;
        content-align: center middle;
        width: 100%;
    }

    #tools_params_container {
        height: auto;
        padding: 0;
        margin: 0;
    }

    #tools_scroll {
        height: 1fr;
    }

    #tools_tool_panel {
        height: 3;
        border: none;
        margin-bottom: 0;
    }

    #output_file_container {
        dock: bottom;
        margin-bottom: 0;
        height: 3;
        border: none;
        padding-bottom: 1;
    }


    #tools_tool_panel Button, #output_file_container Button {
        height: 2;
        border: none;
        padding: 0 2;
    }

    #tools_tool_panel .button-group {
        margin-top: 0;
    }

    #tools_middle_row {
        layout: grid;
        grid-size: 2 1;
        grid-columns: 2fr 1fr;
        height: auto;
    }

    #tools_middle_row > Container {
        height: 100%;
        margin-bottom: 0;
    }

    #tools_results_container {
        align: center middle;
    }

    #tools_params_placeholder {
        padding: 1 0;
        width: 100%;
        content-align: center middle;
    }

    #tools_results_display {
        padding: 1 0;
        width: auto;
        height: auto;
        content-align: center middle;
        link-style: none;
        link-style-hover: none;
        link-color-hover: $background;
        link-background-hover: $foreground;
    }

    .tools-cursor-1 {
        color: $warning;
    }

    .tools-cursor-2 {
        color: $primary;
    }

    .distortion-comp-row {
        height: 3;
        border: none;
        background: transparent;
        margin: 0;
        padding: 0;
        layout: horizontal;
        align: center middle;
    }

    .distortion-comp-row Checkbox {
        height: 1;
        border: none;
        background: transparent;
        padding: 0 1;
        width: auto;
        content-align: left middle;
    }

    #tools_trace_radioset {
        height: 3;
        border: none;
        background: transparent;
        margin: 0;
        padding: 0;
        layout: horizontal;
    }

    #tools_trace_radioset RadioButton {
        height: 3;
        border: none;
        background: transparent;
        padding: 0 1;
        width: auto;
        content-align: left middle;
    }

    #btn_tool_measure,
    #btn_tool_distortion {
        width: 1fr;
        margin: 0 1 0 0;
    }

    #btn_tool_distortion {
        margin-right: 0;
    }

    """

    COMMANDS = App.COMMANDS | {
        StatusPollProvider,
        PlotBackendProvider,
        CursorMarkerProvider,
    }

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("ctrl+d", "toggle_debug_scpi", "SCPI Debug", show=False),
    ]

    TITLE = "tina - Terminal UI Network Analyzer"

    def __init__(self, test_updates: bool = False):
        """Initialise application state, settings, worker thread, and timers."""
        super().__init__()

        self._test_updates = test_updates
        self.settings_manager = SettingsManager()
        self.settings = self.settings_manager.load()
        self.worker = MeasurementWorker()
        self.config = VNAConfig()
        self.connected = False
        self.measuring = False
        self.last_measurement = None  # Store last measurement data
        self.last_output_path = None  # Store last output file path
        self.last_plot_path = None  # Store last plot image path
        self.log_messages = []  # Store all log messages for filtering
        self._message_check_timer = None  # Timer for checking worker messages
        self._resize_timer = None  # Timer for debouncing resize events
        self._path_update_timer = None  # Timer for updating path label on resize
        self._poll_timer = None  # Timer for status bar polling
        self._status_poll_in_flight = False  # True while a STATUS_POLL is outstanding
        self._debug_scpi = self.settings.debug_scpi

        # Tools tab state
        self._tools_cursor1_hz: float | None = None
        self._tools_cursor2_hz: float | None = None
        self._tools_resize_timer = None
        self._tools_input_timer = None  # Timer for debouncing cursor input changes

        # Create temporary directory for plot images
        self.plot_temp_dir = Path("/tmp/tui-vna-plots")
        self.plot_temp_dir.mkdir(parents=True, exist_ok=True)

        # Detect terminal and font once at boot
        self.terminal_font, self.terminal_font_size = _get_terminal_font()
        self.terminal_program = os.getenv("TERM_PROGRAM", "unknown")

    def compose(self) -> ComposeResult:
        """Create child widgets."""
        yield Header()

        with TabbedContent(id="content"):
            # Measurement Tab
            with TabPane("Setup", id="tab_measure"):
                with VerticalScroll():
                    # Connection Settings
                    with Container(classes="panel") as panel:
                        panel.border_title = "Connection"
                        with Horizontal(classes="field"):
                            yield Label("Host:")
                            yield Input(
                                value=self.settings.last_host,
                                placeholder="IP address (e.g., 192.168.1.100)",
                                id="input_host",
                            )
                            yield Label("Port:")
                            yield Input(
                                value=self.settings.last_port,
                                placeholder="inst0",
                                id="input_port",
                            )
                        with Horizontal(classes="param-row"):
                            yield Label("Status poll:", classes="col-label")
                            yield Select(
                                options=[
                                    ("Off", 0),
                                    ("1 s", 1),
                                    ("2 s", 2),
                                    ("5 s", 5),
                                    ("10 s", 10),
                                    ("30 s", 30),
                                ],
                                value=self.settings.status_poll_interval,
                                id="sb_poll_interval",
                                classes="col-input",
                            )
                            yield Static("", classes="col-check")

                    # Measurement Settings
                    with Container(classes="panel") as panel:
                        panel.border_title = "Measurement Parameters"
                        with Horizontal(classes="param-row"):
                            yield Label("Unit:", classes="col-label")
                            yield Select(
                                options=[
                                    ("Hz", "Hz"),
                                    ("kHz", "kHz"),
                                    ("MHz", "MHz"),
                                    ("GHz", "GHz"),
                                ],
                                value=self.settings.freq_unit,
                                id="select_freq_unit",
                                classes="col-input",
                            )
                            yield Static("", classes="col-check")
                        with Horizontal(classes="param-row"):
                            yield Label("Frequency:", classes="col-label")
                            yield Input(
                                value=str(self.settings.start_freq_mhz),
                                placeholder="Start",
                                id="input_start_freq",
                                classes="col-input",
                            )
                            yield Label("-")
                            yield Input(
                                value=str(self.settings.stop_freq_mhz),
                                placeholder="Stop",
                                id="input_stop_freq",
                                classes="col-input",
                            )
                            yield Checkbox(
                                "Override",
                                id="check_set_freq",
                                value=self.settings.set_freq_range,
                                classes="col-check",
                            )
                        with Horizontal(classes="param-row"):
                            yield Label("Points:", classes="col-label")
                            yield Input(
                                value=str(self.settings.sweep_points),
                                placeholder="601",
                                id="input_points",
                                classes="col-input",
                            )
                            yield Label(" ")
                            yield Static("", classes="col-input")
                            yield Checkbox(
                                "Override",
                                id="check_set_points",
                                value=self.settings.set_sweep_points,
                                classes="col-check",
                            )
                        with Horizontal(classes="param-row"):
                            yield Label("Averaging:", classes="col-label")
                            yield Input(
                                value=str(self.settings.averaging_count),
                                placeholder="16",
                                id="input_avg_count",
                                classes="col-input",
                            )
                            yield Checkbox(
                                "Enable",
                                id="check_averaging",
                                value=self.settings.enable_averaging,
                                classes="col-input",
                            )
                            yield Checkbox(
                                "Override",
                                id="check_set_avg_count",
                                value=self.settings.set_averaging_count,
                                classes="col-check",
                            )

                    # Output Settings
                    with Container(classes="panel") as panel:
                        panel.border_title = "Output"
                        with Horizontal(classes="param-row"):
                            yield Label("Prefix:", classes="col-label")
                            yield Input(
                                value=self.settings.filename_prefix,
                                placeholder="measurement",
                                id="input_filename_prefix",
                                classes="col-input",
                            )
                            yield Static("", classes="col-check")
                        with Horizontal(classes="param-row"):
                            yield Label("Folder:", classes="col-label")
                            yield Input(
                                value=self.settings.output_folder,
                                placeholder="measurement",
                                id="input_output_folder",
                                classes="col-input",
                            )
                            yield Static("", classes="col-check")
                        with Horizontal(classes="param-row"):
                            yield Label("Filename:", classes="col-label")
                            yield Input(
                                value=self.settings.custom_filename,
                                placeholder="(auto-generated)",
                                id="input_custom_filename",
                                classes="col-input",
                                disabled=not self.settings.use_custom_filename,
                            )
                            yield Checkbox(
                                "Custom",
                                id="check_custom_filename",
                                value=self.settings.use_custom_filename,
                                classes="col-check",
                            )
                        with Horizontal(classes="param-row"):
                            yield Label("Export:", classes="col-label")
                            yield Checkbox(
                                "S11",
                                id="check_export_s11",
                                value=self.settings.export_s11,
                            )
                            yield Checkbox(
                                "S21",
                                id="check_export_s21",
                                value=self.settings.export_s21,
                            )
                            yield Checkbox(
                                "S12",
                                id="check_export_s12",
                                value=self.settings.export_s12,
                            )
                            yield Checkbox(
                                "S22",
                                id="check_export_s22",
                                value=self.settings.export_s22,
                            )
                            yield Static("", classes="col-check")

            # Measurement Tab
            with TabPane("Measurement", id="tab_results"):
                # Output File panel — docked to bottom
                with Container(id="output_file_container", classes="panel") as panel:
                    panel.border_title = "Output"
                    with Horizontal(classes="plot-controls"):
                        yield Static(
                            "No file loaded", id="output_file_label", markup=True
                        )
                        yield Static(classes="spacer")
                        yield Button(
                            "📂\nShow",
                            id="btn_open_output",
                            variant="primary",
                            disabled=True,
                        )
                        yield Button(
                            "◐\nPNG",
                            id="btn_export_png",
                            variant="success",
                            disabled=True,
                        )
                        yield Button(
                            "◇\nSVG",
                            id="btn_export_svg",
                            variant="success",
                            disabled=True,
                        )
                with VerticalScroll():
                    # Plot container (results/graph)
                    with Container(id="results_container", classes="panel") as panel:
                        panel.border_title = "Plot"
                        yield Static(
                            "[dim]No measurements yet.[/dim]",
                            id="results_plot_placeholder",
                            markup=True,
                        )
                    # Options panel (plot parameter selection)
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
                                    self.settings.plot_type
                                    if self.settings.plot_type
                                    in ["magnitude", "phase", "phase_raw"]
                                    else "magnitude"
                                ),
                                id="select_plot_type",
                            )
                            yield Label("Show:")
                            yield Checkbox(
                                "S11", id="check_plot_s11", value=self.settings.plot_s11
                            )
                            yield Checkbox(
                                "S21", id="check_plot_s21", value=self.settings.plot_s21
                            )
                            yield Checkbox(
                                "S12", id="check_plot_s12", value=self.settings.plot_s12
                            )
                            yield Checkbox(
                                "S22", id="check_plot_s22", value=self.settings.plot_s22
                            )
                        with Horizontal(classes="plot-controls"):
                            with Horizontal(classes="span-axis-group"):
                                yield Label("X:")
                                yield Input(
                                    placeholder="Min",
                                    id="input_plot_freq_min",
                                )
                                yield Label("-")
                                yield Input(
                                    placeholder="Max",
                                    id="input_plot_freq_max",
                                )
                                yield Button(
                                    "↻ Reset",
                                    id="btn_reset_freq_limits",
                                    variant="default",
                                )
                            with Horizontal(classes="span-axis-group"):
                                yield Label("Y:")
                                yield Input(
                                    placeholder="Min",
                                    id="input_plot_y_min",
                                )
                                yield Label("-")
                                yield Input(
                                    placeholder="Max",
                                    id="input_plot_y_max",
                                )
                                yield Button(
                                    "↻ Reset",
                                    id="btn_reset_y_limits",
                                    variant="default",
                                )
                            yield Button(
                                "✓ Apply",
                                id="btn_apply_limits",
                                variant="primary",
                            )

            # Tools Tab
            with TabPane("Tools", id="tab_tools"):
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
                        # Selection frame (left half)
                        with Container(classes="panel") as panel:
                            panel.border_title = "Selection"
                            with Horizontal(classes="plot-controls"):
                                yield Label("Type:")
                                yield Select(
                                    options=[
                                        ("Magnitude", "magnitude"),
                                        ("Phase", "phase"),
                                    ],
                                    value=(
                                        self.settings.tools_plot_type
                                        if self.settings.tools_plot_type
                                        in ("magnitude", "phase")
                                        else "magnitude"
                                    ),
                                    id="select_tools_plot_type",
                                )
                                yield Label("Trace:")
                                with RadioSet(id="tools_trace_radioset"):
                                    yield RadioButton(
                                        "S11",
                                        id="tools_radio_s11",
                                        value=(self.settings.tools_trace == "S11"),
                                    )
                                    yield RadioButton(
                                        "S21",
                                        id="tools_radio_s21",
                                        value=(self.settings.tools_trace == "S21"),
                                    )
                                    yield RadioButton(
                                        "S12",
                                        id="tools_radio_s12",
                                        value=(self.settings.tools_trace == "S12"),
                                    )
                                    yield RadioButton(
                                        "S22",
                                        id="tools_radio_s22",
                                        value=(self.settings.tools_trace == "S22"),
                                    )
                            # Dynamic parameters area (populated when a tool is active)
                            with Container(id="tools_params_container"):
                                yield Static(
                                    "[dim]Activate a tool below to see options.[/dim]",
                                    id="tools_params_placeholder",
                                    markup=True,
                                )
                        # Results frame (right half)
                        with Container(
                            id="tools_results_container", classes="panel"
                        ) as panel:
                            panel.border_title = "Tool Results [@click='app.show_tool_help'][on $primary] ? [/]"
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
                        )
                        yield Button(
                            "⌇\nDistortion",
                            id="btn_tool_distortion",
                            variant="primary",
                        )

            # Log Tab
            with TabPane("Log", id="tab_log"):
                # Log filters
                with Container(classes="panel") as panel:
                    panel.border_title = "Filter"
                    with Horizontal(classes="filter-row"):
                        yield Checkbox("↑ TX", id="check_log_tx", value=True)
                        yield Checkbox("↓ RX", id="check_log_rx", value=True)
                        yield Checkbox("i Info", id="check_log_info", value=True)
                        yield Checkbox("⋯ Busy", id="check_log_progress", value=True)
                        yield Checkbox("✓ Good", id="check_log_success", value=True)
                        yield Checkbox("✗ Bad", id="check_log_error", value=True)
                        yield Static("", classes="filter-spacer")
                        yield Checkbox(
                            "• Debug",
                            id="check_log_debug",
                            value=False,
                            classes="secondary-filter",
                        )
                        yield Checkbox(
                            "~ Poll",
                            id="check_log_poll",
                            value=False,
                            classes="secondary-filter",
                        )
                log_area = RichLog(
                    id="log_content", markup=True, highlight=False, wrap=False
                )
                log_area.border_title = "Log  [@click='app.copy_log'][reverse] ⎘ [/][/]"
                yield log_area

        yield Static("", id="footer_separator")

        # Controls panel with progress bar (left) and buttons (right)
        with Container(id="controls_panel"):
            with Horizontal(id="action_bar"):
                with Vertical(id="progress_container"):
                    yield Label("Disconnected", id="progress_label")
                    yield ProgressBar(id="progress_bar")
                yield Button("📡\nConnect", id="btn_connect", variant="primary")
                yield Button(
                    "🔍\nRead Parameters",
                    id="btn_read_params",
                    variant="default",
                    disabled=True,
                )
                yield Button(
                    "📊\nMeasure", id="btn_measure", variant="success", disabled=True
                )
                yield Button(
                    "📁\nImport File",
                    id="btn_import_results",
                    variant="warning",
                )

        yield StatusFooter()

    def on_mount(self) -> None:
        """Called when app starts."""
        self._update_title()
        self.query_one(StatusFooter).set_debug_mode(self._debug_scpi, connected=False)
        self.call_after_refresh(self._log_startup)
        # Initialize progress bar to 0 (not indeterminate)
        self.query_one("#progress_bar", ProgressBar).update(total=100, progress=0)
        # Initialize plot type dropdown based on backend
        self._update_plot_type_options()
        # Apply active tool UI state at startup
        self._apply_tool_ui()
        # Start worker thread
        self.worker.start()
        # Start message polling
        self._start_message_polling()
        # Check for updates in background (after UI is ready)
        self.call_after_refresh(self._check_for_updates)

    def _log_startup(self) -> None:
        """Log startup message after UI is ready."""
        self.log_message("VNA Control ready. Connect to start.", "info")
        # Log detected terminal and font info
        font_info = self.terminal_font
        if self.terminal_font_size:
            font_info += f" {self.terminal_font_size}pt"
        self.log_message(
            f"Detected terminal: {self.terminal_program} | Font: {font_info}", "debug"
        )

    @work
    async def _check_for_updates(self) -> None:
        """Check GitHub for newer releases and show modals as appropriate."""
        loop = asyncio.get_event_loop()

        # --- Test mode: show all three modals with lorem ipsum content -------
        if self._test_updates:
            welcome_cl, stable_fake, pre_fake = await loop.run_in_executor(
                None, fetch_test_update_data, __version__
            )
            await self.push_screen_wait(_welcome_screen(__version__, welcome_cl))
            await self.push_screen_wait(_update_screen(stable_fake))
            await self.push_screen_wait(_update_screen(pre_fake))
            return

        # --- Post-update welcome (shown once per version after upgrading) ---
        last_ack = load_last_acknowledged_version()
        if last_ack and last_ack != __version__:
            changelog = await loop.run_in_executor(
                None, get_changelogs_since, last_ack, __version__
            )
            await self.push_screen_wait(_welcome_screen(__version__, changelog))
            save_last_acknowledged_version(__version__)
        elif not last_ack:
            # First run — just record the version silently, no welcome shown
            save_last_acknowledged_version(__version__)

        # --- Check for newer releases ---
        stable, pre = await loop.run_in_executor(None, get_update_info, __version__)

        if stable:
            await self.push_screen_wait(_update_screen(stable))
        elif pre:
            notified = load_notified_prerelease()
            if notified != pre.version:
                await self.push_screen_wait(_update_screen(pre))
                save_notified_prerelease(pre.version)

    def _update_plot_type_options(self) -> None:
        """Update plot type dropdown options based on selected backend."""
        plot_backend = self.settings.plot_backend
        plot_type_select = self.query_one("#select_plot_type", Select)
        current_type = plot_type_select.value

        if plot_backend == "terminal":
            # Text-based backend: magnitude, phase, phase_raw
            new_options = [
                ("Magnitude", "magnitude"),
                ("Phase", "phase"),
                ("Phase Raw", "phase_raw"),
            ]
        else:  # image backend
            # Image-based backend: magnitude, phase, phase_raw, smith
            new_options = [
                ("Magnitude", "magnitude"),
                ("Phase", "phase"),
                ("Phase Raw", "phase_raw"),
                ("Smith Chart", "smith"),
            ]

        # Update options
        plot_type_select.set_options(new_options)

        # Try to preserve the current selection if it's still valid
        valid_values = [opt[1] for opt in new_options]
        if current_type in valid_values:
            plot_type_select.value = current_type
        else:
            # Default to magnitude if current type not available
            plot_type_select.value = "magnitude"

    def on_app_theme_changed(self) -> None:
        """Invalidate cached style map and rerender log with updated theme colors."""
        self._cached_style_map = None
        self._refresh_log_display()
        if self.last_measurement is not None:
            self.call_after_refresh(self._refresh_tools_plot)

    def on_unmount(self) -> None:
        """Called when app is shutting down."""
        # Save settings before exit
        self._save_current_settings()
        # Stop worker thread gracefully
        if self.worker:
            self.worker.stop(timeout=5.0)

    def _save_current_settings(self) -> None:
        """Save current UI state to settings."""
        try:
            # Connection settings
            self.settings.last_host = self.query_one("#input_host", Input).value.strip()
            self.settings.last_port = (
                self.query_one("#input_port", Input).value.strip() or "inst0"
            )

            # Measurement parameters
            self.settings.freq_unit = self.query_one("#select_freq_unit", Select).value
            self.settings.start_freq_mhz = float(
                self.query_one("#input_start_freq", Input).value or "1.0"
            )
            self.settings.stop_freq_mhz = float(
                self.query_one("#input_stop_freq", Input).value or "1100.0"
            )
            self.settings.sweep_points = int(
                self.query_one("#input_points", Input).value or "601"
            )
            self.settings.averaging_count = int(
                self.query_one("#input_avg_count", Input).value or "16"
            )

            # Override flags
            self.settings.set_freq_range = self.query_one(
                "#check_set_freq", Checkbox
            ).value
            self.settings.set_sweep_points = self.query_one(
                "#check_set_points", Checkbox
            ).value
            self.settings.enable_averaging = self.query_one(
                "#check_averaging", Checkbox
            ).value
            self.settings.set_averaging_count = self.query_one(
                "#check_set_avg_count", Checkbox
            ).value

            # Output settings
            self.settings.output_folder = self.query_one(
                "#input_output_folder", Input
            ).value
            self.settings.filename_prefix = self.query_one(
                "#input_filename_prefix", Input
            ).value
            self.settings.use_custom_filename = self.query_one(
                "#check_custom_filename", Checkbox
            ).value
            self.settings.custom_filename = self.query_one(
                "#input_custom_filename", Input
            ).value
            self.settings.export_s11 = self.query_one(
                "#check_export_s11", Checkbox
            ).value
            self.settings.export_s21 = self.query_one(
                "#check_export_s21", Checkbox
            ).value
            self.settings.export_s12 = self.query_one(
                "#check_export_s12", Checkbox
            ).value
            self.settings.export_s22 = self.query_one(
                "#check_export_s22", Checkbox
            ).value

            # Plot settings
            self.settings.plot_s11 = self.query_one("#check_plot_s11", Checkbox).value
            self.settings.plot_s21 = self.query_one("#check_plot_s21", Checkbox).value
            self.settings.plot_s12 = self.query_one("#check_plot_s12", Checkbox).value
            self.settings.plot_s22 = self.query_one("#check_plot_s22", Checkbox).value
            self.settings.plot_type = self.query_one("#select_plot_type", Select).value

            # Tools tab settings
            self.settings.tools_trace = self._get_tools_trace()
            try:
                self.settings.tools_plot_type = self.query_one(
                    "#select_tools_plot_type", Select
                ).value
            except Exception:
                pass

            # Save to disk
            self.settings_manager.save(self.settings)
        except Exception:
            # Silently fail during shutdown to avoid errors
            pass

    def _start_message_polling(self):
        """Start polling worker thread for messages."""
        self._message_check_timer = self.set_interval(0.05, self._check_worker_messages)

    def _start_status_polling(self, interval_s: int) -> None:
        """Start (or restart) periodic VNA status polling."""
        if self._poll_timer is not None:
            self._poll_timer.stop()
            self._poll_timer = None
        if interval_s > 0:
            self._poll_timer = self.set_interval(interval_s, self._do_status_poll)

    def _stop_status_polling(self) -> None:
        """Stop status polling and clear the status bar."""
        if self._poll_timer is not None:
            self._poll_timer.stop()
            self._poll_timer = None
        self.query_one(StatusFooter).set_disconnected()

    def _do_status_poll(self) -> None:
        """Send a status poll request to the worker.

        Skipped when disconnected, measuring, or a previous poll has not yet
        returned a STATUS_UPDATE — prevents backlog when polls take longer than
        the polling interval.
        """
        if self.connected and not self.measuring and not self._status_poll_in_flight:
            self._status_poll_in_flight = True
            self.worker.send_command(MessageType.STATUS_POLL)

    def _check_worker_messages(self):
        """Check for messages from worker thread (called periodically)."""
        try:
            while True:
                msg = self.worker.get_response(timeout=0.001)
                self._handle_worker_message(msg)
        except queue.Empty:
            pass

    def _handle_worker_message(self, msg):
        """Handle message from worker thread."""
        if msg.type == MessageType.LOG:
            log_msg: LogMessage = msg.data
            self.log_message(log_msg.message, log_msg.level)

        elif msg.type == MessageType.PROGRESS:
            update: ProgressUpdate = msg.data
            self.set_progress(update.message, update.progress_pct)

        elif msg.type == MessageType.CONNECTED:
            display_name = msg.data
            self.connected = True
            self.sub_title = display_name
            self._update_title()
            self.log_message(f"Connected: {display_name}", "success")
            self.update_connect_button()
            self.enable_buttons_for_state()
            self.reset_progress()
            self._start_status_polling(self.settings.status_poll_interval)
            if self._debug_scpi:
                self.worker.send_command(MessageType.SET_DEBUG_SCPI, data=True)
            # Immediate first poll without waiting for the interval
            self._status_poll_in_flight = True
            self.worker.send_command(MessageType.STATUS_POLL)

        elif msg.type == MessageType.DISCONNECTED:
            self.connected = False
            self._status_poll_in_flight = False
            self.sub_title = ""
            self._update_title()
            self.log_message("Disconnected from VNA", "success")
            self.update_connect_button()
            self.enable_buttons_for_state()
            self.reset_progress()
            self._stop_status_polling()

        elif msg.type == MessageType.PARAMS_READ:
            result: ParamsResult = msg.data
            self._update_params_ui(result)
            self.log_message("Parameters retrieved successfully", "success")
            self.enable_buttons_for_state()
            self.reset_progress()

        elif msg.type == MessageType.MEASUREMENT_COMPLETE:
            result: MeasurementResult = msg.data
            self.log_message(
                f"Received measurement complete with {len(result.frequencies)} points",
                "debug",
            )
            # Schedule the async handler
            asyncio.create_task(self._handle_measurement_complete(result))

        elif msg.type == MessageType.STATUS_UPDATE:
            self._status_poll_in_flight = False
            result: StatusResult = msg.data
            self.query_one(StatusFooter).update_status(result)

        elif msg.type == MessageType.SCPI_ERROR_UPDATE:
            if self._debug_scpi:
                self.query_one(StatusFooter).update_last_error(
                    msg.data["command"], msg.data["error"]
                )

        elif msg.type == MessageType.ERROR:
            self.log_message(msg.error, "error")
            if "Connection failed" in msg.error or "Disconnect failed" in msg.error:
                self.connected = False
                self.sub_title = ""
                self._update_title()
                self.update_connect_button()
                self._stop_status_polling()
            self.enable_buttons_for_state()
            self.reset_progress()
            self.measuring = False

    @on(Select.Changed, "#sb_poll_interval")
    def on_poll_interval_change(self, event: Select.Changed) -> None:
        """Handle status poll interval change."""
        if event.value == Select.BLANK:
            return
        self.settings.status_poll_interval = event.value
        if self.connected:
            self._start_status_polling(event.value)

    @on(Checkbox.Changed, "#check_custom_filename")
    def on_custom_filename_change(self, event: Checkbox.Changed) -> None:
        """Enable/disable custom filename input based on checkbox."""
        custom_input = self.query_one("#input_custom_filename", Input)
        custom_input.disabled = not event.value

    @on(TabbedContent.TabActivated)
    def on_tab_activated(self, event: TabbedContent.TabActivated) -> None:
        """Handle tab activation - scroll log to bottom when Log tab is opened, redraw plots when Results tab is opened."""
        if event.pane.id == "tab_log":
            # Scroll log to bottom when opening log tab
            log_content = self.query_one("#log_content", RichLog)
            log_content.scroll_end(animate=False)
        elif event.pane.id == "tab_results":
            # Redraw plot with correct sizing when switching to results tab
            if self.last_measurement is not None:
                self.set_timer(0.3, self._delayed_redraw_plot)
        elif event.pane.id == "tab_tools":
            # Redraw tools plot when switching to tools tab
            if self.last_measurement is not None:
                self.set_timer(0.3, self._delayed_redraw_tools_plot)

    @on(
        Checkbox.Changed,
        "#check_log_tx, #check_log_rx, #check_log_info, #check_log_progress, #check_log_success, #check_log_error, #check_log_debug, #check_log_poll",
    )
    def on_log_filter_change(self, event: Checkbox.Changed) -> None:
        """Handle log filter checkbox changes."""
        self._refresh_log_display()

    # Cached level→(icon, Rich style) map; None means rebuild on next use.
    # Invalidated by on_app_theme_changed so colors always match the active theme.
    _cached_style_map: dict[str, tuple[str, str]] | None = None

    def _build_style_map(self) -> dict[str, tuple[str, str]]:
        """Build the level→(icon, style) map from current Textual theme variables."""
        v = self.get_css_variables()
        c_tx = v.get("accent", "#ffa62b")
        c_rx = v.get("secondary", "#0178D4")
        c_suc = v.get("success", "#4EBF71")
        c_err = v.get("error", "#ba3c5b")
        return {
            "tx": ("↑", c_tx),
            "rx": ("↓", c_rx),
            "tx/poll": ("↑~", f"dim {c_tx}"),
            "rx/poll": ("↓~", f"dim {c_rx}"),
            "tx/debug": ("↑•", "dim"),
            "rx/debug": ("↓•", "dim"),
            "info": ("i", "default"),
            "success": ("✓", f"bold {c_suc}"),
            "error": ("✗", f"bold {c_err}"),
            "progress": ("⋯", "dim italic"),
            "debug": ("•", "dim"),
        }

    def _format_log_entry(self, entry: dict) -> str:
        """Render a stored log entry to Rich markup.

        The style map is cached after the first call and only rebuilt when the
        theme changes, so ``get_css_variables()`` is not called per-entry
        during a full log redraw.
        """
        if self._cached_style_map is None:
            self._cached_style_map = self._build_style_map()
        icon, style = self._cached_style_map.get(entry["level"], ("•", "default"))
        safe_msg = rich_escape(entry["message"])
        return f"[dim]{entry['timestamp']}[/dim] [{style}]{icon}[/] {safe_msg}"

    def log_message(self, message: str, level: str = "info"):
        """Add message to log."""
        log_entry = {
            "timestamp": datetime.now().strftime("%H:%M:%S"),
            "level": level,
            "message": message,
        }
        self.log_messages.append(log_entry)

        if self._should_show_log(level):
            log_content = self.query_one("#log_content", RichLog)
            log_content.write(self._format_log_entry(log_entry))
            log_content.scroll_end(animate=False)

    def _should_show_log(self, level: str) -> bool:
        """Return True if *level* passes all active log filter checkboxes.

        Composite levels (e.g. ``"tx/poll"``) require both the primary and
        secondary checkbox to be checked.  Unknown levels are shown by default.
        """
        try:
            if "/" in level:
                primary, secondary = level.split("/", 1)
                primary_id = self._LOG_FILTER_IDS.get(primary)
                secondary_id = self._LOG_FILTER_IDS.get(secondary)
                primary_ok = (
                    self.query_one(primary_id, Checkbox).value if primary_id else True
                )
                secondary_ok = (
                    self.query_one(secondary_id, Checkbox).value
                    if secondary_id
                    else True
                )
                return primary_ok and secondary_ok

            checkbox_id = self._LOG_FILTER_IDS.get(level)
            if checkbox_id:
                return self.query_one(checkbox_id, Checkbox).value
            return True  # Unknown levels are always shown
        except Exception:
            # During initialization, show everything
            return True

    def _refresh_log_display(self):
        """Rebuild log display from stored entries using current theme colors and filters."""
        log_content = self.query_one("#log_content", RichLog)
        log_content.clear()
        for entry in self.log_messages:
            if self._should_show_log(entry["level"]):
                log_content.write(self._format_log_entry(entry))
        log_content.scroll_end(animate=False)

    def set_progress(self, label: str, progress: float = 0):
        """Update progress bar and label. Progress is 0-100."""
        self.query_one("#progress_label", Label).update(f"{label} ({progress:.0f}%)")
        progress_bar = self.query_one("#progress_bar", ProgressBar)
        progress_bar.update(total=100, progress=progress)

    def reset_progress(self):
        """Reset progress bar based on connection state."""
        if self.connected:
            self.query_one("#progress_label", Label).update("Ready")
        else:
            self.query_one("#progress_label", Label).update("Disconnected")
        progress_bar = self.query_one("#progress_bar", ProgressBar)
        progress_bar.update(total=100, progress=0)

    def disable_all_buttons(self):
        """Disable all action buttons during operations."""
        self.query_one("#btn_connect", Button).disabled = True
        self.query_one("#btn_read_params", Button).disabled = True
        self.query_one("#btn_measure", Button).disabled = True

    def enable_buttons_for_state(self):
        """Enable buttons based on connection state."""
        self.query_one("#btn_connect", Button).disabled = False
        self.query_one("#btn_read_params", Button).disabled = not self.connected
        self.query_one("#btn_measure", Button).disabled = not self.connected

    def update_connect_button(self):
        """Update connect button label based on connection state."""
        btn = self.query_one("#btn_connect", Button)
        if self.connected:
            btn.label = "🔌\nDisconnect"
            btn.variant = "error"
        else:
            btn.label = "📡\nConnect"
            btn.variant = "primary"

    def action_show_tool_help(self) -> None:
        """Open the help viewer for the currently active tool."""
        active = self.settings.tools_active_tool
        help_map = {
            "cursor": ("cursor.md", "Cursor Tool Help"),
            "distortion": ("distortion.md", "Distortion Tool Help"),
        }
        if active not in help_map:
            self.notify("Activate a tool to see its help.", timeout=2)
            return
        filename, title = help_map[active]
        try:
            # Use importlib.resources to load help files from installed package
            if sys.version_info >= (3, 9):
                help_files = importlib.resources.files("tina") / "help"
                content = (help_files / filename).read_text(encoding="utf-8")
            else:
                # Fallback for Python 3.8
                content = importlib.resources.read_text("tina.help", filename, encoding="utf-8")
        except (OSError, FileNotFoundError, ModuleNotFoundError):
            content = "_Help file not found._"
        self.push_screen(HelpScreen(title, content))

    def action_copy_cell_value(self, value: str) -> None:
        """Copy a distortion table cell value to the system clipboard."""
        self.copy_to_clipboard(value)
        self.notify(f"Copied: {value}", timeout=1.5)

    def action_copy_log(self) -> None:
        """Copy visible log entries as plain text to the system clipboard."""
        style_map = self._cached_style_map or self._build_style_map()
        lines = [
            f"{e['timestamp']} {style_map.get(e['level'], ('•', ''))[0]} {e['message']}"
            for e in self.log_messages
            if self._should_show_log(e["level"])
        ]
        self.copy_to_clipboard("\n".join(lines))
        self.notify("Log copied to clipboard", timeout=2)

    @on(Button.Pressed, "#btn_connect")
    def handle_connect(self) -> None:
        """Connect or disconnect from VNA."""
        self.disable_all_buttons()

        if self.connected:
            # Stop polling immediately so no more STATUS_POLLs queue up
            self.connected = False
            self._update_title()
            if self._poll_timer is not None:
                self._poll_timer.stop()
                self._poll_timer = None
            # Disconnect
            self.set_progress("Disconnecting...", 50)
            self.log_message("Disconnecting from VNA...", "progress")
            self.worker.clear_commands()
            self.worker.send_command(MessageType.DISCONNECT)
        else:
            # Connect
            try:
                self.config.host = self.query_one("#input_host", Input).value.strip()
                self.config.port = (
                    self.query_one("#input_port", Input).value.strip() or "inst0"
                )

                # Validate host is provided
                if not self.config.host:
                    self.log_message("Please enter VNA IP address", "error")
                    self.enable_buttons_for_state()
                    self.reset_progress()
                    return

                # Add host to history
                self.settings_manager.add_host_to_history(self.config.host)

                # Add port to history
                self.settings_manager.add_port_to_history(self.config.port)

                # Save settings on successful connection attempt
                self._save_current_settings()

                self.log_message(f"Connecting to {self.config.host}...", "progress")
                self.sub_title = "Connecting..."

                self.worker.send_command(MessageType.CONNECT, self.config)

            except Exception as e:
                self.log_message(f"Connection setup failed: {str(e)}", "error")
                self.enable_buttons_for_state()
                self.reset_progress()

    def action_toggle_debug_scpi(self) -> None:
        """Toggle per-command SCPI error checking (debug mode)."""
        self._debug_scpi = not self._debug_scpi
        self.settings.debug_scpi = self._debug_scpi
        self.worker.send_command(MessageType.SET_DEBUG_SCPI, data=self._debug_scpi)
        self._update_title()
        self.query_one(StatusFooter).set_debug_mode(self._debug_scpi, self.connected)
        state = "ON" if self._debug_scpi else "OFF"
        self.log_message(
            f"SCPI debug mode {state} — queries SYST:ERR? after each command", "info"
        )

    def _update_title(self) -> None:
        """Reflect connection and debug mode state in the app title."""
        base = "tina" if self.connected else "tina - Terminal UI Network Analyzer"
        self.title = f"{base} 🐛" if self._debug_scpi else base

    @on(Button.Pressed, "#btn_read_params")
    def handle_read_params(self) -> None:
        """Read current settings from VNA and populate inputs."""
        self.disable_all_buttons()
        self.log_message("Reading VNA parameters...", "progress")
        self.worker.send_command(MessageType.READ_PARAMS)

    def _update_params_ui(self, result):
        """Update UI with parameters read from VNA."""
        freq_unit = self.query_one("#select_freq_unit", Select).value
        unit_multipliers = {"Hz": 1, "kHz": 1e3, "MHz": 1e6, "GHz": 1e9}
        multiplier = unit_multipliers.get(freq_unit, 1e6)

        start_val = result.start_freq / multiplier
        stop_val = result.stop_freq / multiplier

        self.query_one("#input_start_freq", Input).value = f"{start_val:.2f}"
        self.query_one("#input_stop_freq", Input).value = f"{stop_val:.2f}"
        self.query_one("#input_points", Input).value = str(result.points)
        self.query_one("#check_averaging", Checkbox).value = result.averaging_enabled
        self.query_one("#input_avg_count", Input).value = str(result.averaging_count)

    @on(Button.Pressed, "#btn_measure")
    def handle_measure(self) -> None:
        """Handle measure button."""
        if self.measuring:
            return

        self.measuring = True
        self.disable_all_buttons()

        try:
            # Get frequency unit and convert to Hz
            freq_unit = self.query_one("#select_freq_unit", Select).value
            unit_multipliers = {"Hz": 1, "kHz": 1e3, "MHz": 1e6, "GHz": 1e9}
            multiplier = unit_multipliers.get(freq_unit, 1e6)

            # Update config from inputs
            self.config.start_freq_hz = (
                float(self.query_one("#input_start_freq", Input).value) * multiplier
            )
            self.config.stop_freq_hz = (
                float(self.query_one("#input_stop_freq", Input).value) * multiplier
            )
            self.config.sweep_points = int(self.query_one("#input_points", Input).value)
            self.config.averaging_count = int(
                self.query_one("#input_avg_count", Input).value
            )

            # Update config toggles
            self.config.set_freq_range = self.query_one(
                "#check_set_freq", Checkbox
            ).value
            self.config.set_sweep_points = self.query_one(
                "#check_set_points", Checkbox
            ).value
            self.config.enable_averaging = self.query_one(
                "#check_averaging", Checkbox
            ).value
            self.config.set_averaging_count = self.query_one(
                "#check_set_avg_count", Checkbox
            ).value

        except ValueError as e:
            self.log_message(f"Invalid configuration: {e}", "error")
            self.measuring = False
            self.enable_buttons_for_state()
            self.reset_progress()
            return

        # Save settings before measurement
        self._save_current_settings()

        self.sub_title = "Measuring..."
        self.log_message("Starting measurement...", "progress")

        # Send measurement command to worker
        self.worker.send_command(MessageType.MEASURE, self.config)

    async def _handle_measurement_complete(self, result: MeasurementResult):
        """Handle completed measurement from worker thread."""
        try:
            self.log_message("Processing measurement result...", "debug")
            freqs = result.frequencies
            sparams = result.sparams

            self.log_message(
                f"Result contains {len(freqs)} frequencies, {len(sparams)} S-parameters",
                "debug",
            )

            self.log_message(
                f"Measurement complete: {len(freqs)} points captured", "success"
            )

            # Filter S-parameters based on export checkboxes
            self.log_message("Filtering S-parameters for export...", "debug")
            export_params = {}
            if self.query_one("#check_export_s11", Checkbox).value:
                export_params["S11"] = sparams["S11"]
            if self.query_one("#check_export_s21", Checkbox).value:
                export_params["S21"] = sparams["S21"]
            if self.query_one("#check_export_s12", Checkbox).value:
                export_params["S12"] = sparams["S12"]
            if self.query_one("#check_export_s22", Checkbox).value:
                export_params["S22"] = sparams["S22"]

            self.log_message(
                f"Exporting {len(export_params)} S-parameters: {', '.join(export_params.keys())}",
                "debug",
            )

            if not export_params:
                self.log_message("No S-parameters selected for export", "error")
                self.sub_title = "Connected"
                return

            # Export to touchstone
            self.set_progress("Exporting...", 80)
            self.log_message("Exporting to Touchstone format...", "progress")

            freq_unit = self.query_one("#select_freq_unit", Select).value
            exporter = TouchstoneExporter(freq_unit=freq_unit)

            # Determine filename and prefix
            use_custom = self.query_one("#check_custom_filename", Checkbox).value
            prefix = self.query_one("#input_filename_prefix", Input).value.strip()
            if not prefix:
                prefix = "measurement"

            if use_custom:
                filename = self.query_one("#input_custom_filename", Input).value.strip()
                if not filename:
                    filename = None
            else:
                filename = None

            output_folder = self.query_one("#input_output_folder", Input).value.strip()
            if not output_folder:
                output_folder = "measurement"

            output_path = await asyncio.get_event_loop().run_in_executor(
                None,
                exporter.export,
                freqs,
                export_params,
                output_folder,
                filename,
                prefix,
            )

            self.log_message(f"Saved: {output_path}", "success")

            # Store measurement data with frequency unit
            freq_unit = self.query_one("#select_freq_unit", Select).value
            self.last_measurement = {
                "freqs": freqs,
                "sparams": sparams,
                "output_path": output_path,
                "freq_unit": freq_unit,
            }
            self.last_output_path = output_path

            # Set plot checkboxes to match export parameters
            self.query_one("#check_plot_s11", Checkbox).value = self.query_one(
                "#check_export_s11", Checkbox
            ).value
            self.query_one("#check_plot_s21", Checkbox).value = self.query_one(
                "#check_export_s21", Checkbox
            ).value
            self.query_one("#check_plot_s12", Checkbox).value = self.query_one(
                "#check_export_s12", Checkbox
            ).value
            self.query_one("#check_plot_s22", Checkbox).value = self.query_one(
                "#check_export_s22", Checkbox
            ).value

            # Generate plot and update results
            self.set_progress("Updating results...", 90)
            self.log_message("Updating results display...", "debug")
            await self._update_results(freqs, sparams, output_path)
            self.log_message("Results display updated", "debug")

            # Also refresh tools tab with new data
            await self._refresh_tools_plot()
            self._run_tools_computation()

            self.set_progress("Done", 100)
            self.sub_title = "Measurement complete"

        except Exception as e:
            self.log_message(f"Post-measurement processing failed: {str(e)}", "error")
            self.sub_title = f"Error: {str(e)}"

        finally:
            self.measuring = False
            self.enable_buttons_for_state()
            self.reset_progress()

    @on(Button.Pressed, "#btn_import_results")
    def handle_import_results(self) -> None:
        """Import and display results from a Touchstone file."""
        try:
            # Use tkinter file dialog (hidden root window)
            root = tk.Tk()
            root.withdraw()
            root.attributes("-topmost", True)

            file_path = filedialog.askopenfilename(
                title="Select Touchstone File",
                filetypes=[
                    ("Touchstone Files", "*.s2p"),
                    ("All Files", "*.*"),
                ],
                initialdir=(
                    self.settings.output_folder if self.settings.output_folder else "."
                ),
            )
            root.destroy()

            if not file_path:
                return  # User cancelled

            self.log_message(f"Importing: {file_path}", "progress")

            # Import file using TouchstoneExporter
            freqs, sparams = TouchstoneExporter.import_file(file_path)

            self.log_message(
                f"Imported {len(freqs)} points, {len(sparams)} S-parameters", "success"
            )

            # Store measurement data (imported files use MHz by default)
            self.last_measurement = {
                "freqs": freqs,
                "sparams": sparams,
                "output_path": file_path,
                "freq_unit": "MHz",  # Touchstone files typically use MHz
            }
            self.last_output_path = file_path

            # Update plot checkboxes based on available parameters
            self.query_one("#check_plot_s11", Checkbox).value = "S11" in sparams
            self.query_one("#check_plot_s21", Checkbox).value = "S21" in sparams
            self.query_one("#check_plot_s12", Checkbox).value = "S12" in sparams
            self.query_one("#check_plot_s22", Checkbox).value = "S22" in sparams

            # Display results
            asyncio.create_task(self._update_results(freqs, sparams, file_path))
            # Also refresh tools tab with imported data
            asyncio.create_task(self._refresh_tools_plot())
            self._run_tools_computation()

        except FileNotFoundError as e:
            self.log_message(str(e), "error")
        except ValueError as e:
            self.log_message(f"Invalid file format: {e}", "error")
        except Exception as e:
            self.log_message(f"Import failed: {e}", "error")

    @on(Button.Pressed, "#btn_export_png")
    def handle_export_png(self) -> None:
        """Export current plot as PNG."""
        if not self.last_measurement:
            self.log_message("No measurement data to export", "error")
            return

        try:
            # Use tkinter file dialog
            root = tk.Tk()
            root.withdraw()
            root.attributes("-topmost", True)

            # Use s2p filename as default if available
            if self.last_output_path:
                default_name = Path(self.last_output_path).stem + ".png"
            else:
                default_name = "plot.png"

            file_path = filedialog.asksaveasfilename(
                title="Export Plot as PNG",
                defaultextension=".png",
                filetypes=[("PNG Image", "*.png"), ("All Files", "*.*")],
                initialdir=(
                    self.settings.output_folder if self.settings.output_folder else "."
                ),
                initialfile=default_name,
            )
            root.destroy()

            if not file_path:
                return  # User cancelled

            # Get current plot settings
            plot_type = self.query_one("#select_plot_type", Select).value
            plot_params = []
            if self.query_one("#check_plot_s11", Checkbox).value:
                plot_params.append("S11")
            if self.query_one("#check_plot_s21", Checkbox).value:
                plot_params.append("S21")
            if self.query_one("#check_plot_s12", Checkbox).value:
                plot_params.append("S12")
            if self.query_one("#check_plot_s22", Checkbox).value:
                plot_params.append("S22")

            # Generate plot
            if plot_type == "smith":
                _create_smith_chart(
                    self.last_measurement["freqs"],
                    self.last_measurement["sparams"],
                    plot_params,
                    Path(file_path),
                    dpi=300,  # High DPI for export
                    colors=_get_plot_colors(self.get_css_variables()),
                )
            else:
                _create_matplotlib_plot(
                    self.last_measurement["freqs"],
                    self.last_measurement["sparams"],
                    plot_params,
                    plot_type,
                    Path(file_path),
                    dpi=300,  # High DPI for export
                    colors=_get_plot_colors(self.get_css_variables()),
                )

            self.log_message(f"Exported PNG: {file_path}", "success")

        except Exception as e:
            self.log_message(f"PNG export failed: {e}", "error")

    @on(Button.Pressed, "#btn_export_svg")
    def handle_export_svg(self) -> None:
        """Export current plot as SVG."""
        if not self.last_measurement:
            self.log_message("No measurement data to export", "error")
            return

        try:
            # Use tkinter file dialog
            root = tk.Tk()
            root.withdraw()
            root.attributes("-topmost", True)

            # Use s2p filename as default if available
            if self.last_output_path:
                default_name = Path(self.last_output_path).stem + ".svg"
            else:
                default_name = "plot.svg"

            file_path = filedialog.asksaveasfilename(
                title="Export Plot as SVG",
                defaultextension=".svg",
                filetypes=[("SVG Vector Image", "*.svg"), ("All Files", "*.*")],
                initialdir=(
                    self.settings.output_folder if self.settings.output_folder else "."
                ),
                initialfile=default_name,
            )
            root.destroy()

            if not file_path:
                return  # User cancelled

            # Get current plot settings
            plot_type = self.query_one("#select_plot_type", Select).value
            plot_params = []
            if self.query_one("#check_plot_s11", Checkbox).value:
                plot_params.append("S11")
            if self.query_one("#check_plot_s21", Checkbox).value:
                plot_params.append("S21")
            if self.query_one("#check_plot_s12", Checkbox).value:
                plot_params.append("S12")
            if self.query_one("#check_plot_s22", Checkbox).value:
                plot_params.append("S22")

            # SVG export - matplotlib will detect .svg and use SVG backend
            if plot_type == "smith":
                _create_smith_chart(
                    self.last_measurement["freqs"],
                    self.last_measurement["sparams"],
                    plot_params,
                    Path(file_path),
                    dpi=150,  # DPI doesn't matter much for vector
                    colors=_get_plot_colors(self.get_css_variables()),
                )
            else:
                _create_matplotlib_plot(
                    self.last_measurement["freqs"],
                    self.last_measurement["sparams"],
                    plot_params,
                    plot_type,
                    Path(file_path),
                    dpi=150,  # DPI doesn't matter much for vector
                    colors=_get_plot_colors(self.get_css_variables()),
                )

            self.log_message(f"Exported SVG: {file_path}", "success")

        except Exception as e:
            self.log_message(f"SVG export failed: {e}", "error")

    @on(Button.Pressed, "#btn_reset_freq_limits")
    async def handle_reset_freq_limits(self) -> None:
        """Reset frequency limits to original measurement range."""
        if self.last_measurement is None:
            return

        # Clear the frequency input fields
        self.query_one("#input_plot_freq_min", Input).value = ""
        self.query_one("#input_plot_freq_max", Input).value = ""

        # Redraw plot with full frequency range
        await self._update_results(
            self.last_measurement["freqs"],
            self.last_measurement["sparams"],
            self.last_measurement["output_path"],
        )

    @on(Button.Pressed, "#btn_reset_y_limits")
    async def handle_reset_y_limits(self) -> None:
        """Reset Y-axis limits to auto-detected range."""
        if self.last_measurement is None:
            return

        # Clear the Y-axis input fields
        self.query_one("#input_plot_y_min", Input).value = ""
        self.query_one("#input_plot_y_max", Input).value = ""

        # Redraw plot with auto Y range
        await self._update_results(
            self.last_measurement["freqs"],
            self.last_measurement["sparams"],
            self.last_measurement["output_path"],
        )

    @on(Button.Pressed, "#btn_open_output")
    def handle_open_output(self) -> None:
        """Open the output file location in file explorer."""
        if not self.last_output_path or not os.path.exists(self.last_output_path):
            self.log_message("Output file not found", "error")
            return

        try:
            file_path = os.path.abspath(self.last_output_path)
            folder_path = os.path.dirname(file_path)

            system = platform.system()
            if system == "Windows":
                # Open folder and select file
                subprocess.run(["explorer", "/select,", file_path])
            elif system == "Darwin":  # macOS
                # Open folder and select file
                subprocess.run(["open", "-R", file_path])
            elif system == "Linux":
                # Try various file managers
                # First try to select the file if file manager supports it
                try:
                    subprocess.run(
                        [
                            "dbus-send",
                            "--print-reply",
                            "--dest=org.freedesktop.FileManager1",
                            "/org/freedesktop/FileManager1",
                            "org.freedesktop.FileManager1.ShowItems",
                            f"array:string:file://{file_path}",
                            "string:",
                        ]
                    )
                except Exception:
                    # Fall back to just opening the folder
                    for fm in ["xdg-open", "nautilus", "dolphin", "thunar", "nemo"]:
                        try:
                            subprocess.run([fm, folder_path])
                            break
                        except FileNotFoundError:
                            continue

            self.log_message(f"Opened: {folder_path}", "success")
        except Exception as e:
            self.log_message(f"Failed to open file location: {e}", "error")

    def on_resize(self, event) -> None:
        """Handle window resize - redraw plot if measurement exists."""
        if self.last_measurement is not None:
            # Cancel any pending resize timer
            if self._resize_timer is not None:
                self._resize_timer.stop()
            # Debounce: redraw only after 300ms of no resize events
            self._resize_timer = self.set_timer(0.3, self._redraw_plot)

        # Debounce tools plot redraw
        if self.last_measurement is not None:
            if self._tools_resize_timer is not None:
                self._tools_resize_timer.stop()
            self._tools_resize_timer = self.set_timer(0.3, self._refresh_tools_plot)

        # Update output file path label
        if self.last_output_path is not None:
            if self._path_update_timer is not None:
                self._path_update_timer.stop()
            self._path_update_timer = self.set_timer(
                0.3, self._update_output_path_label
            )

    async def _delayed_redraw_plot(self) -> None:
        """Delayed plot redraw to ensure proper container sizing."""
        if self.last_measurement is not None:
            await self._update_results(
                self.last_measurement["freqs"],
                self.last_measurement["sparams"],
                self.last_measurement["output_path"],
            )

    async def _redraw_plot(self) -> None:
        """Redraw the plot with current terminal size."""
        if self.last_measurement is not None:
            await self._update_results(
                self.last_measurement["freqs"],
                self.last_measurement["sparams"],
                self.last_measurement["output_path"],
            )

    # ------------------------------------------------------------------ #
    # Tools tab helpers
    # ------------------------------------------------------------------ #

    def _get_tools_trace(self) -> str:
        """Return the currently selected trace from the Tools RadioSet."""
        for param in ("S11", "S21", "S12", "S22"):
            try:
                rb = self.query_one(f"#tools_radio_{param.lower()}", RadioButton)
                if rb.value:
                    return param
            except Exception:
                pass
        return "S11"

    def _apply_tool_ui(self) -> None:
        """Sync button variants and params to the current tools_active_tool value."""
        active = self.settings.tools_active_tool
        try:
            self.query_one("#btn_tool_measure", Button).variant = (
                "success" if active == "cursor" else "primary"
            )
            self.query_one("#btn_tool_distortion", Button).variant = (
                "success" if active == "distortion" else "primary"
            )
        except Exception:
            pass
        self.call_after_refresh(self._rebuild_tools_params)

    def _set_active_tool(self, tool_name: str) -> None:
        """Toggle a tool on/off; update button variants and rebuild params."""
        if self.settings.tools_active_tool == tool_name:
            self.settings.tools_active_tool = ""
        else:
            self.settings.tools_active_tool = tool_name
        self._apply_tool_ui()
        if self.last_measurement is not None:
            self._run_tools_computation()
            self.call_after_refresh(self._refresh_tools_plot)

    def _get_distortion_comp_enabled(self) -> list[bool]:
        """Return a 6-element list of which Legendre component overlays are enabled."""
        defaults = [False, True, True, False, False, False]
        result = list(defaults)
        for n in range(6):
            try:
                result[n] = self.query_one(
                    f"#input_distortion_comp_{n}", Checkbox
                ).value
            except Exception:
                pass
        return result

    async def _rebuild_tools_params(self) -> None:
        """Rebuild the #tools_params_container based on the active tool."""
        try:
            container = self.query_one("#tools_params_container", Container)
        except Exception:
            return

        await container.remove_children()

        active = self.settings.tools_active_tool
        freq_unit = (
            self.last_measurement.get("freq_unit", "MHz")
            if self.last_measurement
            else "MHz"
        )

        if active in ("cursor", "distortion"):
            unit_multipliers = {"Hz": 1, "kHz": 1e3, "MHz": 1e6, "GHz": 1e9}
            mult = unit_multipliers.get(freq_unit, 1e6)
            c1_val = (
                str(round(self._tools_cursor1_hz / mult, 6))
                if self._tools_cursor1_hz is not None
                else ""
            )
            c2_val = (
                str(round(self._tools_cursor2_hz / mult, 6))
                if self._tools_cursor2_hz is not None
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
                comp_row = Horizontal(classes="distortion-comp-row")
                await container.mount(comp_row)
                for n in range(6):
                    await comp_row.mount(
                        Checkbox(
                            _DISTORTION_COMPONENT_NAMES[n],
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

    async def _delayed_redraw_tools_plot(self) -> None:
        """Delayed tools-tab redraw to allow container sizing to settle."""
        if self.last_measurement is not None:
            await self._refresh_tools_plot()

    async def _delayed_tools_refresh(self) -> None:
        """Debounced handler: refresh tools plot then run computation."""
        await self._refresh_tools_plot()
        self._run_tools_computation()

    async def _refresh_tools_plot(self) -> None:
        """Render the tools-tab plot for the selected single trace with cursor markers."""
        if self.last_measurement is None:
            return

        try:
            container = self.query_one("#tools_plot_container", Container)
        except Exception:
            return

        freqs = self.last_measurement["freqs"]
        sparams = self.last_measurement["sparams"]
        freq_unit = self.last_measurement.get("freq_unit", "MHz")
        unit_multipliers = {"Hz": 1, "kHz": 1e3, "MHz": 1e6, "GHz": 1e9}
        multiplier = unit_multipliers.get(freq_unit, 1e6)

        trace = self._get_tools_trace()

        try:
            plot_type = self.query_one("#select_tools_plot_type", Select).value
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
            data = _unwrap_phase(phase)
            y_label = "Phase (°)"
            plot_title = f"{trace} Phase (Unwrapped)"
        else:
            data = phase
            y_label = "Phase (°)"
            plot_title = f"{trace} Phase (Raw)"

        auto_y_min, auto_y_max = _calculate_plot_range_with_outlier_filtering(
            data, outlier_percentile=1.0, safety_margin=0.05
        )
        freq_axis = freqs / multiplier
        plot_colors = _get_plot_colors(self.get_css_variables())
        trace_color_rgb = plot_colors["traces_rgb"].get(trace, (255, 255, 255))
        trace_color_hex = plot_colors["traces"].get(trace, "#ffffff")

        cursor1_hz = self._tools_cursor1_hz
        cursor2_hz = self._tools_cursor2_hz
        active_tool = self.settings.tools_active_tool
        marker_symbol = self.settings.cursor_marker_style

        cursor1_hex = plot_colors["cursor1"]
        cursor2_hex = plot_colors["cursor2"]
        cursor1_rgb = plot_colors["cursor1_rgb"]
        cursor2_rgb = plot_colors["cursor2_rgb"]

        # Map Unicode marker to matplotlib marker code
        mpl_markers = {"▼": "v", "✕": "x", "○": "o"}
        mpl_marker = mpl_markers.get(marker_symbol, "v")

        plot_backend = self.settings.plot_backend

        if plot_backend == "terminal":
            from textual_plotext import PlotextPlot

            # Reuse an existing PlotextPlot to avoid a blank-container flash
            existing = container.query(PlotextPlot)
            if existing:
                pw = existing.first()
                for child in list(container.children):
                    if child is not pw:
                        await child.remove()
            else:
                await container.remove_children()
                pw = PlotextPlot()
                await container.mount(pw)
            plt_term = pw.plt
            plt_term.clf()

            plt_term.plot(
                freq_axis.tolist(),
                data.tolist(),
                label=trace,
                marker="braille",
                color=trace_color_rgb,
            )
            plt_term.ylim(auto_y_min, auto_y_max)

            if active_tool in ("cursor", "distortion"):
                if cursor1_hz is not None:
                    v1 = float(np.interp(cursor1_hz, freqs, data))
                    c1_axis = cursor1_hz / multiplier
                    plt_term.plot(
                        freq_axis.tolist(),
                        [v1] * len(freq_axis),
                        marker="·",
                        color=cursor1_rgb,
                    )
                    plt_term.vline(c1_axis, color=cursor1_rgb)
                    plt_term.scatter(
                        [c1_axis], [v1], marker=marker_symbol, color=cursor1_rgb
                    )

                if cursor2_hz is not None:
                    v2 = float(np.interp(cursor2_hz, freqs, data))
                    c2_axis = cursor2_hz / multiplier
                    plt_term.plot(
                        freq_axis.tolist(),
                        [v2] * len(freq_axis),
                        marker="·",
                        color=cursor2_rgb,
                    )
                    plt_term.vline(c2_axis, color=cursor2_rgb)
                    plt_term.scatter(
                        [c2_axis], [v2], marker=marker_symbol, color=cursor2_rgb
                    )

                if (
                    active_tool == "distortion"
                    and cursor1_hz is not None
                    and cursor2_hz is not None
                ):
                    _dist = DistortionTool().compute(
                        freqs, sparams, trace, plot_type, cursor1_hz, cursor2_hz
                    )
                    if _dist.extra:
                        _ex = _dist.extra
                        _coeffs = _ex["coeffs"]
                        _x = np.array(_ex["x_norm"])
                        _f_band_axis = np.array(_ex["f_band_hz"]) / multiplier
                        _comp_enabled = self._get_distortion_comp_enabled()
                        _ov_rgb = plot_colors["distortion_overlays_rgb"]
                        for _n in range(6):
                            if not _comp_enabled[_n]:
                                continue
                            _cum = np.zeros(_n + 1)
                            _cum[:] = _coeffs[: _n + 1]
                            _cum_y = np.polynomial.legendre.legval(_x, _cum).tolist()
                            plt_term.plot(
                                _f_band_axis.tolist(),
                                _cum_y,
                                marker=".",
                                color=_ov_rgb[_n],
                            )

            plt_term.title(plot_title)
            plt_term.xlabel(f"Frequency ({freq_unit})")
            plt_term.ylabel(y_label)
            plt_term.theme("clear")
            pw.refresh()

        else:
            # Image backend — matplotlib
            plot_file = self.plot_temp_dir / "tools_plot.png"
            dpi = 150
            fixed_width_px = 1920
            fixed_height_px = 1080

            fig, ax = plt.subplots(
                figsize=(fixed_width_px / dpi, fixed_height_px / dpi), dpi=dpi
            )
            fg = plot_colors["fg"]
            fig.patch.set_alpha(0.0)
            ax.set_facecolor("none")

            ax.plot(freq_axis, data, label=trace, color=trace_color_hex, linewidth=1.5)
            ax.set_ylim(auto_y_min, auto_y_max)

            if active_tool in ("cursor", "distortion"):
                if cursor1_hz is not None:
                    v1 = float(np.interp(cursor1_hz, freqs, data))
                    c1_axis = cursor1_hz / multiplier
                    ax.axhline(
                        y=v1, color=cursor1_hex, linestyle=":", linewidth=1, alpha=0.6
                    )
                    ax.axvline(
                        x=c1_axis,
                        color=cursor1_hex,
                        linestyle="--",
                        linewidth=1,
                        alpha=0.8,
                    )
                    ax.plot(
                        [c1_axis],
                        [v1],
                        marker=mpl_marker,
                        color=cursor1_hex,
                        markersize=10,
                        linestyle="none",
                        zorder=5,
                    )

                if cursor2_hz is not None:
                    v2 = float(np.interp(cursor2_hz, freqs, data))
                    c2_axis = cursor2_hz / multiplier
                    ax.axhline(
                        y=v2, color=cursor2_hex, linestyle=":", linewidth=1, alpha=0.6
                    )
                    ax.axvline(
                        x=c2_axis,
                        color=cursor2_hex,
                        linestyle="--",
                        linewidth=1,
                        alpha=0.8,
                    )
                    ax.plot(
                        [c2_axis],
                        [v2],
                        marker=mpl_marker,
                        color=cursor2_hex,
                        markersize=10,
                        linestyle="none",
                        zorder=5,
                    )

                if (
                    active_tool == "distortion"
                    and cursor1_hz is not None
                    and cursor2_hz is not None
                ):
                    _dist = DistortionTool().compute(
                        freqs, sparams, trace, plot_type, cursor1_hz, cursor2_hz
                    )
                    if _dist.extra:
                        _ex = _dist.extra
                        _coeffs = _ex["coeffs"]
                        _x = np.array(_ex["x_norm"])
                        _f_band_axis = np.array(_ex["f_band_hz"]) / multiplier
                        _c0 = _coeffs[0]
                        _f_lo_axis = min(cursor1_hz, cursor2_hz) / multiplier
                        _f_hi_axis = max(cursor1_hz, cursor2_hz) / multiplier
                        # Shade the selected band
                        ax.axvspan(
                            _f_lo_axis,
                            _f_hi_axis,
                            alpha=0.08,
                            color=fg,
                            zorder=0,
                        )
                        _comp_enabled = self._get_distortion_comp_enabled()
                        _ov_hex = plot_colors["distortion_overlays"]
                        for _n in range(6):
                            if not _comp_enabled[_n]:
                                continue
                            _cum = np.zeros(_n + 1)
                            _cum[:] = _coeffs[: _n + 1]
                            _cum_y = np.polynomial.legendre.legval(_x, _cum)
                            ax.plot(
                                _f_band_axis,
                                _cum_y,
                                color=_ov_hex[_n],
                                linestyle=_DISTORTION_OVERLAY_STYLES[_n],
                                linewidth=1.5,
                                label=_DISTORTION_OVERLAY_LABELS[_n],
                                zorder=4,
                            )

            _font_family, _base_size = _get_terminal_font()
            _base_size = _base_size or 10.0
            ax.set_xlabel(f"Frequency ({freq_unit})", color=fg, fontsize=_base_size)
            ax.set_ylabel(y_label, color=fg, fontsize=_base_size)
            ax.set_title(plot_title, color=fg, fontsize=_base_size * 1.2, pad=15)
            ax.tick_params(colors=fg, labelsize=_base_size * 0.85)
            ax.grid(
                True, alpha=0.2, color=plot_colors["grid"], linestyle="-", linewidth=0.5
            )
            legend = ax.legend(
                edgecolor=plot_colors["grid"],
                labelcolor=fg,
                fontsize=_base_size * 0.9,
            )
            legend.get_frame().set_alpha(1.0)
            legend.get_frame().set_facecolor("none")
            for spine in ax.spines.values():
                spine.set_edgecolor(plot_colors["grid"])
                spine.set_linewidth(1)
            plt.tight_layout()
            plt.savefig(
                plot_file,
                dpi=dpi,
                facecolor="none",
                edgecolor="none",
                bbox_inches="tight",
            )
            plt.close(fig)

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
                    # Mount new widget first, then remove stale ones to avoid blank flash
                    await container.mount(img_widget)
                    for child in list(container.children[:-1]):
                        await child.remove()
                except Exception as e:
                    await container.remove_children()
                    await container.mount(
                        Static(f"[red]Image display error: {e}[/red]", markup=True)
                    )
            elif not TEXTUAL_IMAGE_AVAILABLE:
                await container.remove_children()
                await container.mount(
                    Static(
                        f"[dim]Plot saved to: {plot_file}[/dim]",
                        markup=True,
                    )
                )
            else:
                await container.remove_children()
                await container.mount(
                    Static("[red]Could not generate tools plot.[/red]", markup=True)
                )

    def _run_tools_computation(self) -> None:
        """Run the active tool and update the #tools_results_display."""
        active = self.settings.tools_active_tool
        try:
            display = self.query_one("#tools_results_display", Static)
        except Exception:
            return

        if active == "" or self.last_measurement is None:
            display.update("[dim]No tool active.[/dim]")
            return

        freqs = self.last_measurement["freqs"]
        sparams = self.last_measurement["sparams"]
        freq_unit = self.last_measurement.get("freq_unit", "MHz")
        unit_multipliers = {"Hz": 1, "kHz": 1e3, "MHz": 1e6, "GHz": 1e9}
        multiplier = unit_multipliers.get(freq_unit, 1e6)

        trace = self._get_tools_trace()
        try:
            plot_type = self.query_one("#select_tools_plot_type", Select).value
        except Exception:
            plot_type = "magnitude"

        if active == "cursor":
            result = MeasureTool().compute(
                freqs,
                sparams,
                trace,
                plot_type,
                self._tools_cursor1_hz,
                self._tools_cursor2_hz,
            )
            if result.cursor1_value is None and result.cursor2_value is None:
                display.update("[dim]Enter cursor frequencies above.[/dim]")
                return
            _pc = _get_plot_colors(self.get_css_variables())
            c1col = _pc["cursor1"]
            c2col = _pc["cursor2"]
            labelw, valw = 8, 9
            hdr = (
                f"[dim]{'':>{labelw}}  "
                f"{'Freq ('+freq_unit+')':>{valw}}  "
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

        elif active == "distortion":
            result = DistortionTool().compute(
                freqs,
                sparams,
                trace,
                plot_type,
                self._tools_cursor1_hz,
                self._tools_cursor2_hz,
            )
            if not result.extra:
                display.update("[dim]Enter both cursor frequencies above.[/dim]")
                return
            ex = result.extra
            coeffs = ex["coeffs"]
            delta_y = ex["delta_y"]
            unit = result.unit_label
            _ov_hex = _get_plot_colors(self.get_css_variables())["distortion_overlays"]
            _comp_enabled = self._get_distortion_comp_enabled()
            nw, namew, valw = 1, 10, 9
            hdr = (
                f"[dim]{'n':>{nw}}  {'Component':<{namew}}  "
                f"{'cₙ ('+unit+')':>{valw}}  {'Δyₙ ('+unit+')':>{valw}}[/dim]"
            )
            sep = f"[dim]{'─' * (nw + 2 + namew + 2 + valw + 2 + valw)}[/dim]"
            lines = [hdr, sep]
            for n, name in enumerate(_DISTORTION_COMPONENT_NAMES):
                c_raw = f"{coeffs[n]:.4f}"
                color = _ov_hex[n] if _comp_enabled[n] else None
                name_cell = (
                    f"[bold {color}]{name:<{namew}}[/]"
                    if color
                    else f"[dim]{name:<{namew}}[/dim]"
                )
                c_cell = (
                    f"[@click='app.copy_cell_value(\"{c_raw}\")']{c_raw:>{valw}}[/]"
                )
                if n == 0:
                    dy_cell = f"{'—':>{valw}}"
                else:
                    dy_raw = f"{delta_y[n]:.4f}"
                    dy_cell = f"[@click='app.copy_cell_value(\"{dy_raw}\")']{dy_raw:>{valw}}[/]"
                lines.append(
                    f"[dim]{str(n):>{nw}}[/dim]  {name_cell}  {c_cell}  {dy_cell}"
                )
            display.update("\n".join(lines))

    def _update_output_path_label(self) -> None:
        """Update the output path label with intelligent truncation based on available width."""
        if self.last_output_path is None:
            return

        try:
            output_file_label = self.query_one("#output_file_label", Static)
            container = self.query_one("#output_file_container")

            # Calculate actual button widths
            btn_show = self.query_one("#btn_open_output", Button)
            btn_png = self.query_one("#btn_export_png", Button)
            btn_svg = self.query_one("#btn_export_svg", Button)

            # Sum of button widths + margins (each button has margin-left: 1)
            buttons_width = (
                btn_show.size.width
                + btn_png.size.width
                + btn_svg.size.width
                + 6  # 3 buttons × 2 margin (left+right spacing)
            )

            # Available width for path = container width - buttons - buffer
            available_width = container.size.width - buttons_width - 4

            if available_width > 10:
                truncated_path = _truncate_path_intelligently(
                    str(self.last_output_path), available_width
                )
                output_file_label.update(f"📁 {truncated_path}")
        except Exception:
            # If query fails (widget not yet mounted), ignore
            pass

    @on(
        Checkbox.Changed,
        "#check_plot_s11, #check_plot_s21, #check_plot_s12, #check_plot_s22",
    )
    async def on_plot_param_change(self, event: Checkbox.Changed) -> None:
        """Handle S-parameter plot checkbox change."""
        if self.last_measurement is None:
            return

        # Redraw plot with selected parameters
        await self._update_results(
            self.last_measurement["freqs"],
            self.last_measurement["sparams"],
            self.last_measurement["output_path"],
        )

    @on(Select.Changed, "#select_plot_type")
    async def on_plot_type_change(self, event: Select.Changed) -> None:
        """Handle plot type selection change."""
        if self.last_measurement is None:
            return

        # Redraw plot with new plot type
        await self._update_results(
            self.last_measurement["freqs"],
            self.last_measurement["sparams"],
            self.last_measurement["output_path"],
        )

    @on(Button.Pressed, "#btn_apply_limits")
    async def handle_apply_limits(self) -> None:
        """Apply frequency and Y-axis limits and update plot."""
        if self.last_measurement is None:
            return

        # Redraw plot with new limits
        await self._update_results(
            self.last_measurement["freqs"],
            self.last_measurement["sparams"],
            self.last_measurement["output_path"],
        )

    # ------------------------------------------------------------------ #
    # Tools tab event handlers
    # ------------------------------------------------------------------ #

    @on(Button.Pressed, "#btn_tool_measure")
    def handle_tool_measure_pressed(self) -> None:
        """Toggle the Cursor tool."""
        self._set_active_tool("cursor")

    @on(Button.Pressed, "#btn_tool_distortion")
    def handle_tool_distortion_pressed(self) -> None:
        """Toggle the Distortion tool."""
        self._set_active_tool("distortion")

    @on(Input.Changed, "#input_tools_cursor1, #input_tools_cursor2")
    def handle_tools_cursor_change(self, event: Input.Changed) -> None:
        """Parse cursor frequency inputs, then debounce-refresh plot and results."""
        if self.last_measurement is None:
            return

        freq_unit = self.last_measurement.get("freq_unit", "MHz")
        unit_multipliers = {"Hz": 1, "kHz": 1e3, "MHz": 1e6, "GHz": 1e9}
        multiplier = unit_multipliers.get(freq_unit, 1e6)

        def _parse(widget_id: str) -> float | None:
            try:
                val = self.query_one(widget_id, Input).value.strip()
                return float(val) * multiplier if val else None
            except Exception:
                return None

        self._tools_cursor1_hz = _parse("#input_tools_cursor1")
        self._tools_cursor2_hz = _parse("#input_tools_cursor2")

        # Debounce: only redraw after 200 ms of no further input changes
        if self._tools_input_timer is not None:
            self._tools_input_timer.stop()
        self._tools_input_timer = self.set_timer(0.2, self._delayed_tools_refresh)

    @on(Checkbox.Changed, ".distortion-comp-check")
    def handle_distortion_comp_change(self, event: Checkbox.Changed) -> None:
        """Refresh tools plot when a distortion component overlay checkbox changes."""
        if self.last_measurement is None:
            return
        if self._tools_input_timer is not None:
            self._tools_input_timer.stop()
        self._tools_input_timer = self.set_timer(0.2, self._delayed_tools_refresh)

    @on(RadioSet.Changed, "#tools_trace_radioset")
    async def handle_tools_trace_changed(self, event: RadioSet.Changed) -> None:
        """Update tools plot and results when the trace selection changes."""
        if self.last_measurement is None:
            return
        await self._refresh_tools_plot()
        self._run_tools_computation()

    @on(Select.Changed, "#select_tools_plot_type")
    async def on_tools_plot_type_change(self, event: Select.Changed) -> None:
        """Redraw tools plot when the plot type is changed."""
        if self.last_measurement is None:
            return
        await self._refresh_tools_plot()
        self._run_tools_computation()

    # ------------------------------------------------------------------ #

    async def _update_results(self, freqs, sparams, output_path):
        """Update results tab with measurement data using native Textual widgets."""
        self.log_message(
            f"_update_results called with {len(freqs)} freqs, {len(sparams)} sparams",
            "debug",
        )

        # Get frequency unit from measurement data
        freq_unit = self.last_measurement.get("freq_unit", "MHz")
        unit_multipliers = {"Hz": 1, "kHz": 1e3, "MHz": 1e6, "GHz": 1e9}
        multiplier = unit_multipliers.get(freq_unit, 1e6)

        # Update input placeholders with original values and unit
        freq_min_orig = freqs[0] / multiplier
        freq_max_orig = freqs[-1] / multiplier
        self.query_one("#input_plot_freq_min", Input).placeholder = (
            f"Min: {freq_min_orig:.2f} {freq_unit}"
        )
        self.query_one("#input_plot_freq_max", Input).placeholder = (
            f"Max: {freq_max_orig:.2f} {freq_unit}"
        )

        # Apply frequency filtering based on user input
        freq_min_str = self.query_one("#input_plot_freq_min", Input).value.strip()
        freq_max_str = self.query_one("#input_plot_freq_max", Input).value.strip()

        # Filter frequencies if limits are specified
        if freq_min_str or freq_max_str:
            try:
                # Convert from current unit to Hz
                freq_min_hz = (
                    float(freq_min_str) * multiplier if freq_min_str else freqs[0]
                )
                freq_max_hz = (
                    float(freq_max_str) * multiplier if freq_max_str else freqs[-1]
                )

                # Find indices within range
                mask = (freqs >= freq_min_hz) & (freqs <= freq_max_hz)
                if not mask.any():
                    # No points in range, use full range
                    filtered_freqs = freqs
                    filtered_sparams = sparams
                else:
                    filtered_freqs = freqs[mask]
                    # Filter all S-parameters
                    filtered_sparams = {}
                    for param, (mag, phase) in sparams.items():
                        filtered_sparams[param] = (mag[mask], phase[mask])
            except (ValueError, IndexError):
                # Invalid input, use full range
                filtered_freqs = freqs
                filtered_sparams = sparams
        else:
            # No filtering
            filtered_freqs = freqs
            filtered_sparams = sparams

        freq_range = (
            f"{filtered_freqs[0] / 1e6:.1f} - {filtered_freqs[-1] / 1e6:.1f} MHz"
        )

        # Calculate min, max, avg for all S-parameters (using filtered data)
        stats = {}
        for param in ["S11", "S21", "S12", "S22"]:
            if param in filtered_sparams:
                mag = filtered_sparams[param][0]
                stats[param] = {"min": mag.min(), "max": mag.max(), "avg": mag.mean()}

        # Get selected parameters for plot from checkboxes
        plot_params = []
        if (
            self.query_one("#check_plot_s11", Checkbox).value
            and "S11" in filtered_sparams
        ):
            plot_params.append("S11")
        if (
            self.query_one("#check_plot_s21", Checkbox).value
            and "S21" in filtered_sparams
        ):
            plot_params.append("S21")
        if (
            self.query_one("#check_plot_s12", Checkbox).value
            and "S12" in filtered_sparams
        ):
            plot_params.append("S12")
        if (
            self.query_one("#check_plot_s22", Checkbox).value
            and "S22" in filtered_sparams
        ):
            plot_params.append("S22")

        # Clear and rebuild results container
        results_container = self.query_one("#results_container", Container)
        await results_container.remove_children()

        # Update Results panel title with measurement info
        # Show filtered point count and original count if different
        if len(filtered_freqs) != len(freqs):
            point_info = f"{len(filtered_freqs)}/{len(freqs)} pts"
        else:
            point_info = f"{len(freqs)} pts"

        results_container.border_title = f"Results [{freq_range} | {point_info}]"

        # Plot S-parameters
        if plot_params:
            # Get plot settings from UI
            plot_type = self.query_one("#select_plot_type", Select).value
            plot_backend = self.settings.plot_backend

            # Determine plot title
            if plot_type == "magnitude":
                plot_title = "S-Parameter Magnitude"
                y_label = "Magnitude (dB)"
            elif plot_type == "phase":
                plot_title = "S-Parameter Phase (Unwrapped)"
                y_label = "Phase (degrees)"
            elif plot_type == "phase_raw":
                plot_title = "S-Parameter Phase (Raw)"
                y_label = "Phase (degrees)"
            elif plot_type == "smith":
                plot_title = "Smith Chart"
                y_label = ""
            else:
                plot_title = "S-Parameter"
                y_label = ""

            # Calculate Y-axis limits (used by both backends)
            y_min_str = self.query_one("#input_plot_y_min", Input).value.strip()
            y_max_str = self.query_one("#input_plot_y_max", Input).value.strip()
            user_y_min = None
            user_y_max = None

            if y_min_str:
                try:
                    user_y_min = float(y_min_str)
                except ValueError:
                    pass
            if y_max_str:
                try:
                    user_y_max = float(y_max_str)
                except ValueError:
                    pass

            # Calculate auto Y-axis limits for placeholders
            # Collect all data based on plot type (use filtered data)
            all_y_data = []
            for param in plot_params:
                if plot_type == "magnitude":
                    param_data = filtered_sparams[param][0]
                elif plot_type == "phase":
                    param_data = _unwrap_phase(filtered_sparams[param][1])
                else:  # phase_raw
                    param_data = filtered_sparams[param][1]
                all_y_data.append(param_data)

            # Calculate auto limits
            if all_y_data and plot_type != "smith":
                combined_data = np.concatenate(all_y_data)
                auto_y_min, auto_y_max = _calculate_plot_range_with_outlier_filtering(
                    combined_data, outlier_percentile=1.0, safety_margin=0.05
                )

                # Update input placeholders with auto-detected values
                if user_y_min is None:
                    self.query_one("#input_plot_y_min", Input).placeholder = (
                        f"Min: {auto_y_min:.1f} dB"
                        if plot_type == "magnitude"
                        else f"Min: {auto_y_min:.1f}°"
                    )
                if user_y_max is None:
                    self.query_one("#input_plot_y_max", Input).placeholder = (
                        f"Max: {auto_y_max:.1f} dB"
                        if plot_type == "magnitude"
                        else f"Max: {auto_y_max:.1f}°"
                    )
            else:
                # Smith chart or no data - set generic placeholders
                self.query_one("#input_plot_y_min", Input).placeholder = (
                    "Min (N/A for Smith)"
                )
                self.query_one("#input_plot_y_max", Input).placeholder = (
                    "Max (N/A for Smith)"
                )

            # Check if smith chart is selected
            if plot_type == "smith" and plot_backend == "terminal":
                # Smith chart not supported in terminal mode
                await results_container.mount(
                    Static(
                        "\n[bold yellow]Smith Chart not available in terminal mode[/bold yellow]\n"
                        "[dim]Please switch to Image backend to view Smith charts.[/dim]",
                        markup=True,
                    )
                )
            elif plot_backend == "terminal":
                # Use plotext for terminal-based plotting
                from textual_plotext import PlotextPlot

                plot_widget = PlotextPlot()
                await results_container.mount(plot_widget)

                # Configure the plot using the plt property
                plt_term = plot_widget.plt
                plt_term.clf()

                # Plot data as line with braille markers (use filtered data)
                freq_mhz = filtered_freqs / 1e6
                plot_colors = _get_plot_colors(self.get_css_variables())

                # Calculate Y limits first (before plotting)
                if all_y_data:
                    y_min = user_y_min if user_y_min is not None else auto_y_min
                    y_max = user_y_max if user_y_max is not None else auto_y_max
                else:
                    y_min = None
                    y_max = None

                # Plot each parameter, filtering out traces with no visible data
                for param in plot_params:
                    # Select data based on plot type (use filtered data)
                    if plot_type == "magnitude":
                        param_data = filtered_sparams[param][0]
                    elif plot_type == "phase":
                        param_data = _unwrap_phase(filtered_sparams[param][1])
                    else:  # phase_raw
                        param_data = filtered_sparams[param][1]

                    # Skip empty traces (can happen if all data filtered out)
                    if len(param_data) == 0:
                        continue

                    # If Y limits are set, check if trace has any visible data
                    # This prevents plotext from crashing when rendering legend
                    # for traces that are completely outside the plot range
                    if y_min is not None and y_max is not None:
                        # Check if any data points fall within Y range
                        if not np.any((param_data >= y_min) & (param_data <= y_max)):
                            # Skip this trace - it's completely outside Y range
                            continue

                    plt_term.plot(
                        freq_mhz.tolist(),
                        param_data.tolist(),
                        label=param,
                        marker="braille",
                        color=plot_colors["traces_rgb"].get(param, (255, 255, 255)),
                    )

                # Apply Y-axis limits after plotting
                if y_min is not None and y_max is not None:
                    plt_term.ylim(y_min, y_max)

                # Labels and formatting
                plt_term.title(plot_title)
                plt_term.xlabel("Frequency (MHz)")
                plt_term.ylabel(y_label)
                plt_term.theme("clear")

                # Refresh the plot widget to display
                plot_widget.refresh()

            else:  # image backend
                # Generate matplotlib plot at fixed high resolution
                # This avoids regenerating on resize and ensures quality
                plot_file = self.plot_temp_dir / "current_plot.png"

                # Log for debugging
                self.log_message(f"Generating plot at: {plot_file}", "debug")

                # Fixed high-resolution dimensions for quality
                # Target: 1080p (1920x1080) at high DPI
                # This gives good quality without excessive memory usage
                render_scale = 1
                dpi = 150 * render_scale  # 150 DPI

                # For Smith charts, use square dimensions
                if plot_type == "smith":
                    # Use 1920x1920 for high quality square Smith chart
                    fixed_width_px = 1920
                    fixed_height_px = 1920
                else:
                    # For other plots, use 16:9 aspect ratio
                    fixed_width_px = 1920  # Full HD width
                    fixed_height_px = 1080  # Full HD height (16:9 aspect)

                px_w = fixed_width_px
                px_h = fixed_height_px

                plot_colors = _get_plot_colors(self.get_css_variables())

                # Use Smith chart plotter if smith type selected (use filtered data)
                if plot_type == "smith":
                    _create_smith_chart(
                        filtered_freqs,
                        filtered_sparams,
                        plot_params,
                        plot_file,
                        dpi=dpi,
                        pixel_width=px_w,
                        pixel_height=px_h,
                        transparent=True,
                        render_scale=render_scale,
                        colors=plot_colors,
                    )
                else:
                    _create_matplotlib_plot(
                        filtered_freqs,
                        filtered_sparams,
                        plot_params,
                        plot_type,
                        plot_file,
                        dpi=dpi,
                        pixel_width=px_w,
                        pixel_height=px_h,
                        transparent=True,
                        render_scale=render_scale,
                        colors=plot_colors,
                        y_min=user_y_min,
                        y_max=user_y_max,
                    )

                # Store plot path for export
                self.last_plot_path = plot_file

                # Verify file was created
                if not plot_file.exists():
                    self.log_message(
                        f"Error: Plot file not created at {plot_file}", "error"
                    )
                    await results_container.mount(
                        Static(
                            "[red]Failed to generate plot image[/red]",
                            markup=True,
                        )
                    )
                else:
                    self.log_message(
                        f"Plot file created: {plot_file.stat().st_size} bytes", "debug"
                    )

                    # Display image using textual-image widget
                    # Auto-detects Kitty/iTerm2/Sixel and falls back to Unicode
                    try:
                        if not TEXTUAL_IMAGE_AVAILABLE:
                            raise ImportError("textual-image not available")

                        # Force terminal graphics protocol detection
                        terminal = os.environ.get("TERM", "")
                        term_program = os.environ.get("TERM_PROGRAM", "")
                        kitty_window_id = os.environ.get("KITTY_WINDOW_ID", "")

                        self.log_message(
                            f"Terminal detection: TERM='{terminal}', TERM_PROGRAM='{term_program}', KITTY_WINDOW_ID='{kitty_window_id}'",
                            "debug",
                        )

                        # Set environment hints for better graphics detection
                        if (
                            "ghostty" in term_program.lower()
                            or "kitty" in terminal.lower()
                        ):
                            # Force Kitty graphics protocol detection
                            os.environ.setdefault("KITTY_GRAPHICS_PROTOCOL", "1")
                            self.log_message("Forcing Kitty graphics protocol", "debug")

                        # Create image widget - accepts Path or str
                        self.log_message(
                            f"Creating image widget for: {plot_file}", "debug"
                        )

                        img_widget = ImageWidget(str(plot_file))

                        # Debug protocol detection
                        if hasattr(img_widget, "_protocol"):
                            self.log_message(
                                f"Image widget using protocol: {img_widget._protocol}",
                                "debug",
                            )

                        # Try to detect available protocols
                        try:
                            import textual_image.widget as tiw

                            if hasattr(tiw, "_detect_image_support"):
                                protocols = tiw._detect_image_support()
                                self.log_message(
                                    f"Available image protocols: {protocols}", "debug"
                                )
                        except (ImportError, AttributeError) as e:
                            self.log_message(
                                f"Could not detect available image protocols: {e}",
                                "debug",
                            )

                        # Calculate display size based on available container width
                        # and preserve the actual aspect ratio of the generated plot
                        container_w = results_container.content_size.width

                        # Debug the values
                        self.log_message(
                            f"Container width: {container_w}, px_w: {px_w}, px_h: {px_h}",
                            "debug",
                        )

                        if container_w and container_w > 10 and px_w and px_h:
                            # Use most of the width with small padding
                            display_w = max(40, container_w - 4)

                            # Calculate aspect ratio from pixel dimensions
                            # Terminal cells: ~8px wide, ~16px tall (2:1 ratio)
                            # For a square image (1920x1920), this gives aspect_ratio = 2.0
                            # which correctly displays as square in terminal (100w x 50h cells)
                            img_w_cells = px_w / 8
                            img_h_cells = px_h / 16
                            aspect_ratio = img_w_cells / img_h_cells

                            # Derive height from width to preserve aspect ratio
                            display_h = int(display_w / aspect_ratio)

                            img_widget.styles.width = display_w
                            img_widget.styles.height = display_h

                            self.log_message(
                                f"Using proper sizing: {display_w}x{display_h}", "debug"
                            )
                        else:
                            # Fallback if container size unknown - use better fallback
                            fallback_w = 120
                            fallback_h = 60
                            img_widget.styles.width = fallback_w
                            img_widget.styles.height = fallback_h

                            self.log_message(
                                f"Using fallback sizing: {fallback_w}x{fallback_h} (container_w={container_w}, px_w={px_w}, px_h={px_h})",
                                "debug",
                            )

                        self.log_message(
                            "Mounting image widget...",
                            "debug",
                        )
                        await results_container.mount(img_widget)
                        self.log_message("Image widget mounted successfully", "debug")
                    except Exception as e:
                        self.log_message(f"Failed to display image: {e}", "error")
                        # Fallback: show file location
                        await results_container.mount(
                            Static(
                                f"[yellow]Plot generated but display failed[/yellow]\n"
                                f"[cyan]File: {plot_file}[/cyan]\n"
                                f"[dim]Error: {e}[/dim]",
                                markup=True,
                            )
                        )
        else:
            await results_container.mount(
                Static(
                    "\n[bold yellow]No parameters selected for plotting[/bold yellow]",
                    markup=True,
                )
            )

        # S-Parameters statistics using DataTable (after plot)
        # Disabled for now - feels redundant with plot data
        # table = DataTable(zebra_stripes=True, show_header=True, show_cursor=False)
        # table.add_column("Param")
        # table.add_column("Min (dB)")
        # table.add_column("Max (dB)")
        # table.add_column("Avg (dB)")

        # for param in ["S11", "S21", "S12", "S22"]:
        #     if param in stats:
        #         table.add_row(
        #             param,
        #             f"{stats[param]['min']:.2f}",
        #             f"{stats[param]['max']:.2f}",
        #             f"{stats[param]['avg']:.2f}",
        #         )

        # table.styles.height = len(stats) + 1  # Rows + header only
        # table.styles.margin = (0, 0)
        # await results_container.mount(table)

        # Update output file panel with intelligent truncation
        self.last_output_path = output_path
        self._update_output_path_label()

        # Enable export buttons
        self.query_one("#btn_open_output", Button).disabled = False
        self.query_one("#btn_export_png", Button).disabled = False
        self.query_one("#btn_export_svg", Button).disabled = False


def run_gui(test_updates: bool = False):
    """Run GUI mode with proper imports."""
    app = VNAApp(test_updates=test_updates)
    app.run()


def main():
    """Main entry point."""
    from .cli import create_cli_parser, run_cli_measurement

    parser = create_cli_parser()
    args = parser.parse_args()

    if args.now:
        # CLI mode - quick measurement
        return run_cli_measurement(args)
    else:
        # GUI mode
        run_gui(test_updates=args.test_updates)
        return 0


if __name__ == "__main__":
    sys.exit(main())