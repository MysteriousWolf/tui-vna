"""
tina - Terminal UI Network Analyzer
"""

import argparse
import asyncio
import os
import platform
import queue
import subprocess
import sys
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import filedialog

import matplotlib
import matplotlib.pyplot as plt
import numpy as np
import skrf as rf
from textual import on
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical, VerticalScroll
from textual.widgets import (
    Button,
    Checkbox,
    Footer,
    Header,
    Input,
    Label,
    ProgressBar,
    Select,
    Static,
    TabbedContent,
    TabPane,
    TextArea,
)

# Set matplotlib to non-interactive backend
matplotlib.use("Agg")

from .config.settings import AppSettings, SettingsManager
from .drivers import HPE5071B as VNA
from .drivers import VNAConfig
from .utils import TouchstoneExporter
from .worker import (
    LogMessage,
    MeasurementResult,
    MeasurementWorker,
    MessageType,
    ParamsResult,
    ProgressUpdate,
)

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

    return {
        "traces": traces,
        "traces_rgb": traces_rgb,
        "fg": fg,
        "bg": bg,
        "surface": surface,
        "grid": grid,
        "default_trace": TRACE_COLOR_DEFAULT,
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


class VNAApp(App):
    """tina - Terminal uI Network Analyzer"""

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
        margin: 0 1 1 1;
        padding: 0 1;
        border: solid $primary;
        border-title-color: $accent;
        border-title-style: bold;
    }

    #action_bar {
        width: 100%;
        height: auto;
        align: right middle;
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
    }

    .spacer {
        width: 1fr;
    }

    #log_content {
        height: 1fr;
        border: solid $primary;
        border-title-color: $accent;
        border-title-style: bold;
        margin: 1 0;
    }

    #results_text {
        height: 100%;
        padding: 1;
    }

    TabbedContent {
        height: 100%;
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
    """

    BINDINGS = [
        Binding("q", "quit", "Quit"),
    ]

    TITLE = "tina - Terminal UI Network Analyzer"

    def __init__(self):
        super().__init__()

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
            with TabPane("Measurement", id="tab_measure"):
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
                        yield Checkbox("• Debug", id="check_log_debug", value=False)
                log_area = TextArea(
                    id="log_content", read_only=True, show_line_numbers=False
                )
                log_area.border_title = "Log"
                yield log_area

            # Results Tab
            with TabPane("Results", id="tab_results"):
                with VerticalScroll():
                    # Plot parameter selection
                    with Container(classes="panel") as panel:
                        panel.border_title = "Plot"
                        with Horizontal(classes="plot-controls"):
                            yield Label("Backend:")
                            yield Select(
                                options=[
                                    ("Terminal", "terminal"),
                                    ("Image", "image"),
                                ],
                                value=(
                                    self.settings.plot_backend
                                    if self.settings.plot_backend
                                    in ["terminal", "image"]
                                    else "terminal"
                                ),
                                id="select_plot_backend",
                            )
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
                    # Results container
                    with Container(id="results_container", classes="panel") as panel:
                        panel.border_title = "Results"
                        yield Static("No measurements yet.", markup=True)
                    # Output File panel
                    with Container(
                        id="output_file_container", classes="panel"
                    ) as panel:
                        panel.border_title = "Output File"
                        with Horizontal(classes="plot-controls"):
                            yield Static(
                                "No file loaded", id="output_file_label", markup=True
                            )
                            yield Static(classes="spacer")
                            yield Button(
                                "📂 Show",
                                id="btn_open_output",
                                variant="primary",
                                disabled=True,
                            )
                            yield Button(
                                "◐ PNG",
                                id="btn_export_png",
                                variant="success",
                                disabled=True,
                            )
                            yield Button(
                                "◇ SVG",
                                id="btn_export_svg",
                                variant="success",
                                disabled=True,
                            )

        # Controls panel with progress bar (left) and buttons (right)
        with Container(id="controls_panel") as controls:
            controls.border_title = "Controls"
            with Horizontal(id="action_bar"):
                with Vertical(id="progress_container"):
                    yield Label("Disconnected", id="progress_label")
                    yield ProgressBar(id="progress_bar")
                yield Button("📡 Connect", id="btn_connect", variant="primary")
                yield Button(
                    "🔍 Read Parameters",
                    id="btn_read_params",
                    variant="default",
                    disabled=True,
                )
                yield Button(
                    "📊 Measure", id="btn_measure", variant="success", disabled=True
                )
                yield Button(
                    "📁 Import File",
                    id="btn_import_results",
                    variant="warning",
                )

        yield Footer()

    def on_mount(self) -> None:
        """Called when app starts."""
        self.call_after_refresh(self._log_startup)
        # Initialize progress bar to 0 (not indeterminate)
        self.query_one("#progress_bar", ProgressBar).update(total=100, progress=0)
        # Initialize plot type dropdown based on backend
        self._update_plot_type_options()
        # Start worker thread
        self.worker.start()
        # Start message polling
        self._start_message_polling()

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

    def _update_plot_type_options(self) -> None:
        """Update plot type dropdown options based on selected backend."""
        plot_backend = self.query_one("#select_plot_backend", Select).value
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
            self.settings.plot_backend = self.query_one(
                "#select_plot_backend", Select
            ).value

            # Save to disk
            self.settings_manager.save(self.settings)
        except Exception:
            # Silently fail during shutdown to avoid errors
            pass

    def _start_message_polling(self):
        """Start polling worker thread for messages."""
        self._message_check_timer = self.set_interval(0.05, self._check_worker_messages)

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
            idn = msg.data
            self.sub_title = idn
            self.connected = True
            self.log_message(f"Connected: {idn}", "success")
            self.update_connect_button()
            self.enable_buttons_for_state()
            self.reset_progress()

        elif msg.type == MessageType.DISCONNECTED:
            self.connected = False
            self.sub_title = ""
            self.log_message("Disconnected from VNA", "success")
            self.update_connect_button()
            self.enable_buttons_for_state()
            self.reset_progress()

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

        elif msg.type == MessageType.ERROR:
            self.log_message(msg.error, "error")
            if "Connection failed" in msg.error or "Disconnect failed" in msg.error:
                self.connected = False
                self.sub_title = ""
                self.update_connect_button()
            self.enable_buttons_for_state()
            self.reset_progress()
            self.measuring = False

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
            log_content = self.query_one("#log_content", TextArea)
            log_content.scroll_end(animate=False)
        elif event.pane.id == "tab_results":
            # Redraw plot with correct sizing when switching to results tab
            if self.last_measurement is not None:
                self.set_timer(0.3, self._delayed_redraw_plot)

    @on(
        Checkbox.Changed,
        "#check_log_tx, #check_log_rx, #check_log_info, #check_log_progress, #check_log_success, #check_log_error, #check_log_debug",
    )
    def on_log_filter_change(self, event: Checkbox.Changed) -> None:
        """Handle log filter checkbox changes."""
        self._refresh_log_display()

    def log_message(self, message: str, level: str = "info"):
        """Add message to log with plain text formatting for TextArea."""
        timestamp = datetime.now().strftime("%H:%M:%S")

        # Clear, distinct icons for different message types
        icons = {
            "info": "i",  # Simple letter, cross-platform compatible
            "success": "✓",  # Checkmark
            "error": "✗",  # X mark
            "progress": "⋯",  # Horizontal ellipsis for progress
            "tx": "↑",  # Up arrow for sent SCPI commands
            "rx": "↓",  # Down arrow for received SCPI responses
            "debug": "•",  # Bullet for debug messages
        }
        icon = icons.get(level, "•")

        # Remove "TX: " or "RX: " prefix if present (we use arrows instead)
        display_message = message
        if level in ("tx", "rx"):
            if message.startswith("TX: "):
                display_message = message[4:]
            elif message.startswith("RX: "):
                display_message = message[4:]

        # Plain text format for TextArea (no Rich markup)
        formatted_message = f"{timestamp} {icon} {display_message}"

        # Store message with metadata
        log_entry = {
            "timestamp": timestamp,
            "level": level,
            "message": message,
            "icon": icon,
            "formatted": formatted_message,
        }
        self.log_messages.append(log_entry)

        # Check if this message should be displayed based on filters
        if self._should_show_log(level):
            log_content = self.query_one("#log_content", TextArea)
            # Append to TextArea
            current_text = log_content.text
            if current_text:
                log_content.text = current_text + "\n" + log_entry["formatted"]
            else:
                log_content.text = log_entry["formatted"]
            # Scroll to bottom
            log_content.scroll_end(animate=False)

    def _should_show_log(self, level: str) -> bool:
        """Check if a log message should be displayed based on filter settings."""
        try:
            filter_map = {
                "tx": "#check_log_tx",
                "rx": "#check_log_rx",
                "info": "#check_log_info",
                "progress": "#check_log_progress",
                "success": "#check_log_success",
                "error": "#check_log_error",
                "debug": "#check_log_debug",
            }

            checkbox_id = filter_map.get(level)
            if checkbox_id:
                return self.query_one(checkbox_id, Checkbox).value
            return True  # Show by default if unknown level
        except Exception:
            # During initialization, show everything
            return True

    def _refresh_log_display(self):
        """Refresh log display based on current filter settings."""
        log_content = self.query_one("#log_content", TextArea)

        # Rebuild text from filtered messages
        filtered_lines = [
            entry["formatted"]
            for entry in self.log_messages
            if self._should_show_log(entry["level"])
        ]
        log_content.text = "\n".join(filtered_lines)
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
            btn.label = "🔌 Disconnect"
            btn.variant = "error"
        else:
            btn.label = "📡 Connect"
            btn.variant = "primary"

    @on(Button.Pressed, "#btn_connect")
    def handle_connect(self) -> None:
        """Connect or disconnect from VNA."""
        self.disable_all_buttons()

        if self.connected:
            # Disconnect
            self.set_progress("Disconnecting...", 50)
            self.log_message("Disconnecting from VNA...", "progress")
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

    @on(Select.Changed, "#select_plot_backend")
    async def on_plot_backend_change(self, event: Select.Changed) -> None:
        """Handle plot backend selection change."""
        # Update plot type options based on backend
        self._update_plot_type_options()

        # Redraw plot if measurement exists
        if self.last_measurement is None:
            return

        # Redraw plot with new backend
        await self._update_results(
            self.last_measurement["freqs"],
            self.last_measurement["sparams"],
            self.last_measurement["output_path"],
        )

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
            plot_backend = self.query_one("#select_plot_backend", Select).value

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
                render_scale = 2
                dpi = 150 * render_scale  # 300 DPI

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


def create_cli_parser() -> argparse.ArgumentParser:
    """Create command line argument parser."""
    parser = argparse.ArgumentParser(
        description="tina - Terminal UI Network Analyzer",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Quick measurement with last settings
  tina --now

  # Quick measurement with custom output
  tina -n --output-folder ./data --filename-prefix test_run

  # Custom measurement parameters
  tina --host 192.168.1.100 --start-freq 10 --stop-freq 1000 --points 201

  # GUI mode (default)
  tina
        """,
    )

    # Quick measurement option
    parser.add_argument(
        "--now",
        "-n",
        action="store_true",
        help="Quick measurement: use last settings to connect, measure, and save to s2p + png files",
    )

    # Connection parameters
    conn_group = parser.add_argument_group("connection settings")
    conn_group.add_argument("--host", help="VNA IP address (e.g., 192.168.1.100)")
    conn_group.add_argument(
        "--port", default="inst0", help="VISA port (default: inst0)"
    )
    conn_group.add_argument(
        "--timeout",
        type=int,
        help="Connection timeout in milliseconds (default: 60000)",
    )

    # Frequency parameters
    freq_group = parser.add_argument_group("frequency settings")
    freq_group.add_argument(
        "--start-freq", type=float, help="Start frequency in MHz (default: 1.0)"
    )
    freq_group.add_argument(
        "--stop-freq", type=float, help="Stop frequency in MHz (default: 1100.0)"
    )
    freq_group.add_argument(
        "--freq-unit",
        choices=["Hz", "kHz", "MHz", "GHz"],
        help="Frequency unit for output files (default: MHz)",
    )

    # Measurement parameters
    meas_group = parser.add_argument_group("measurement settings")
    meas_group.add_argument(
        "--points", type=int, help="Number of sweep points (default: 601)"
    )
    meas_group.add_argument("--averaging", action="store_true", help="Enable averaging")
    meas_group.add_argument(
        "--avg-count", type=int, help="Averaging count (default: 16)"
    )

    # Override flags
    override_group = parser.add_argument_group("override settings")
    override_group.add_argument(
        "--set-freq-range", action="store_true", help="Override VNA frequency range"
    )
    override_group.add_argument(
        "--set-sweep-points",
        action="store_true",
        help="Override VNA sweep points (default: true)",
    )
    override_group.add_argument(
        "--set-avg-count", action="store_true", help="Override VNA averaging count"
    )

    # Output parameters
    output_group = parser.add_argument_group("output settings")
    output_group.add_argument(
        "--output-folder", help="Output folder path (default: measurement)"
    )
    output_group.add_argument(
        "--filename-prefix", help="Filename prefix (default: measurement)"
    )
    output_group.add_argument(
        "--custom-filename", help="Use custom filename instead of auto-generated"
    )

    # S-parameter selection
    sparam_group = parser.add_argument_group("S-parameter selection")
    sparam_group.add_argument("--s11", action="store_true", help="Export S11 parameter")
    sparam_group.add_argument("--s21", action="store_true", help="Export S21 parameter")
    sparam_group.add_argument("--s12", action="store_true", help="Export S12 parameter")
    sparam_group.add_argument("--s22", action="store_true", help="Export S22 parameter")
    sparam_group.add_argument(
        "--all-sparams",
        action="store_true",
        help="Export all S-parameters (S11, S21, S12, S22)",
    )

    # Plot parameters
    plot_group = parser.add_argument_group("plot settings")
    plot_group.add_argument(
        "--plot-s11", action="store_true", help="Include S11 in plots"
    )
    plot_group.add_argument(
        "--plot-s21", action="store_true", help="Include S21 in plots"
    )
    plot_group.add_argument(
        "--plot-s12", action="store_true", help="Include S12 in plots"
    )
    plot_group.add_argument(
        "--plot-s22", action="store_true", help="Include S22 in plots"
    )
    plot_group.add_argument(
        "--plot-all", action="store_true", help="Include all S-parameters in plots"
    )
    plot_group.add_argument(
        "--no-plots", action="store_true", help="Skip plot generation"
    )

    return parser


def apply_cli_settings(args: argparse.Namespace, settings: AppSettings) -> AppSettings:
    """Apply CLI arguments to settings object."""
    # Connection settings
    if args.host:
        settings.last_host = args.host
    if args.port:
        settings.last_port = args.port
    if args.timeout:
        # Convert to VNA config format if needed
        pass

    # Frequency settings
    if args.start_freq is not None:
        settings.start_freq_mhz = args.start_freq
    if args.stop_freq is not None:
        settings.stop_freq_mhz = args.stop_freq
    if args.freq_unit:
        settings.freq_unit = args.freq_unit

    # Measurement settings
    if args.points is not None:
        settings.sweep_points = args.points
    if args.averaging:
        settings.enable_averaging = True
    if args.avg_count is not None:
        settings.averaging_count = args.avg_count

    # Override flags
    if args.set_freq_range:
        settings.set_freq_range = True
    if args.set_sweep_points:
        settings.set_sweep_points = True
    if args.set_avg_count:
        settings.set_averaging_count = True

    # Output settings
    if args.output_folder:
        settings.output_folder = args.output_folder
    if args.filename_prefix:
        settings.filename_prefix = args.filename_prefix
    if args.custom_filename:
        settings.custom_filename = args.custom_filename
        settings.use_custom_filename = True

    # S-parameter selection
    if args.all_sparams:
        settings.export_s11 = True
        settings.export_s21 = True
        settings.export_s12 = True
        settings.export_s22 = True
    else:
        if args.s11:
            settings.export_s11 = True
        if args.s21:
            settings.export_s21 = True
        if args.s12:
            settings.export_s12 = True
        if args.s22:
            settings.export_s22 = True

    # Plot settings
    if args.plot_all:
        settings.plot_s11 = True
        settings.plot_s21 = True
        settings.plot_s12 = True
        settings.plot_s22 = True
    else:
        if args.plot_s11:
            settings.plot_s11 = True
        if args.plot_s21:
            settings.plot_s21 = True
        if args.plot_s12:
            settings.plot_s12 = True
        if args.plot_s22:
            settings.plot_s22 = True

    return settings


def create_vna_config(settings: AppSettings) -> VNAConfig:
    """Create VNA config from settings."""
    return VNAConfig(
        host=settings.last_host,
        port=settings.last_port,
        start_freq_hz=settings.start_freq_mhz * 1e6,
        stop_freq_hz=settings.stop_freq_mhz * 1e6,
        sweep_points=settings.sweep_points,
        set_freq_range=settings.set_freq_range,
        set_sweep_points=settings.set_sweep_points,
        enable_averaging=settings.enable_averaging,
        averaging_count=settings.averaging_count,
        set_averaging_count=settings.set_averaging_count,
    )


def export_plots_cli(
    frequencies: np.ndarray,
    s_parameters: dict[str, tuple[np.ndarray, np.ndarray]],
    settings: AppSettings,
    output_path: str,
    base_filename: str,
) -> None:
    """Generate and export plots in CLI mode using same scaling as GUI."""
    # Create plots for magnitude and phase
    plot_params = []
    if settings.plot_s11 and "S11" in s_parameters:
        plot_params.append("S11")
    if settings.plot_s21 and "S21" in s_parameters:
        plot_params.append("S21")
    if settings.plot_s12 and "S12" in s_parameters:
        plot_params.append("S12")
    if settings.plot_s22 and "S22" in s_parameters:
        plot_params.append("S22")

    if not plot_params:
        print("No S-parameters selected for plotting")
        return

    # Use the same plot settings as GUI for consistency
    # Match the GUI's high-quality rendering parameters
    render_scale = 2
    dpi = 150 * render_scale  # 300 DPI for high quality

    # Get proper themed colors (use fallback colors which are already well-themed)
    plot_colors = _get_plot_colors(None)  # This will use the nice fallback colors

    # Create magnitude plot using the same method as GUI
    plot_filename = f"{base_filename}_magnitude.png"
    plot_path = os.path.join(output_path, plot_filename)

    # Use the same matplotlib plotting function as the GUI
    _create_matplotlib_plot(
        frequencies,
        s_parameters,
        plot_params,
        plot_type="magnitude",
        output_path=Path(plot_path),
        dpi=dpi,
        pixel_width=1920,
        pixel_height=1080,
        transparent=False,
        render_scale=render_scale,
        colors=plot_colors,
        y_min=None,  # Auto-detect with outlier filtering
        y_max=None,  # Auto-detect with outlier filtering
    )
    print(f"Magnitude plot saved: {plot_path}")

    # Create phase plot using the same method as GUI
    phase_plot_filename = f"{base_filename}_phase.png"
    phase_plot_path = os.path.join(output_path, phase_plot_filename)

    _create_matplotlib_plot(
        frequencies,
        s_parameters,
        plot_params,
        plot_type="phase",  # Unwrapped phase
        output_path=Path(phase_plot_path),
        dpi=dpi,
        pixel_width=1920,
        pixel_height=1080,
        transparent=False,
        render_scale=render_scale,
        colors=plot_colors,
        y_min=None,  # Auto-detect with outlier filtering
        y_max=None,  # Auto-detect with outlier filtering
    )
    print(f"Phase plot saved: {phase_plot_path}")


def run_cli_measurement(args: argparse.Namespace) -> int:
    """Run measurement in CLI mode."""
    try:
        # Load settings
        settings_mgr = SettingsManager()
        settings = settings_mgr.load()

        # Apply CLI overrides
        settings = apply_cli_settings(args, settings)

        # Validate required settings
        if not settings.last_host:
            print("Error: No host IP configured. Use --host option or run GUI first.")
            return 1

        print(f"Connecting to VNA at {settings.last_host}...")

        # Create VNA config and connect
        vna_config = create_vna_config(settings)
        vna = VNA(vna_config)

        def progress_callback(message: str, progress: float):
            print(f"  {message} ({progress:.0f}%)")

        vna.connect(progress_callback)
        print(f"Connected: {vna.idn}")

        # Perform measurement
        print("Starting measurement...")
        frequencies, s_parameters = vna.perform_measurement()
        print(f"Measurement complete: {len(frequencies)} points")

        # Disconnect
        vna.disconnect()

        # Prepare export parameters
        export_params = {}
        if settings.export_s11 and "S11" in s_parameters:
            export_params["S11"] = s_parameters["S11"]
        if settings.export_s21 and "S21" in s_parameters:
            export_params["S21"] = s_parameters["S21"]
        if settings.export_s12 and "S12" in s_parameters:
            export_params["S12"] = s_parameters["S12"]
        if settings.export_s22 and "S22" in s_parameters:
            export_params["S22"] = s_parameters["S22"]

        if not export_params:
            print("Warning: No S-parameters selected for export, exporting all")
            export_params = s_parameters

        # Export touchstone file
        exporter = TouchstoneExporter(
            freq_unit=settings.freq_unit, reference_impedance=50.0
        )

        filename = None
        if settings.use_custom_filename and settings.custom_filename:
            filename = settings.custom_filename

        s2p_path = exporter.export(
            frequencies,
            export_params,
            settings.output_folder,
            filename=filename,
            prefix=settings.filename_prefix,
        )
        print(f"S2P file saved: {s2p_path}")

        # Generate plots unless disabled
        if not args.no_plots:
            base_filename = os.path.splitext(os.path.basename(s2p_path))[0]
            export_plots_cli(
                frequencies,
                s_parameters,
                settings,
                settings.output_folder,
                base_filename,
            )

        print("Measurement complete!")
        return 0

    except Exception as e:
        print(f"Error: {e}")
        return 1


def run_gui():
    """Run GUI mode with proper imports."""
    app = VNAApp()
    app.run()


def main():
    """Main entry point."""
    parser = create_cli_parser()
    args = parser.parse_args()

    if args.now:
        # CLI mode - quick measurement
        return run_cli_measurement(args)
    else:
        # GUI mode
        run_gui()
        return 0


if __name__ == "__main__":
    sys.exit(main())
