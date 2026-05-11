"""Pure matplotlib rendering helpers and color utilities, with no GUI dependencies.

Provides :func:`create_matplotlib_plot`, :func:`get_terminal_font`, and
:func:`get_plot_colors` for use by both the CLI and the GUI layers without
introducing an upward dependency on the ``tina.gui`` package.
"""

from __future__ import annotations

import logging
import os
import platform
import re
import subprocess
from pathlib import Path

import matplotlib.font_manager as fm
import matplotlib.pyplot as plt
import numpy as np
from matplotlib import rc_context

from tina.utils.signal import calculate_plot_range_with_outlier_filtering, unwrap_phase

_log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Color constants
# ---------------------------------------------------------------------------

SPARAM_THEME_KEYS = {
    "S11": "error",
    "S21": "primary",
    "S12": "accent",
    "S22": "success",
}

SPARAM_FALLBACK_COLORS = {
    "S11": "#ff6b6b",
    "S21": "#4ecdc4",
    "S12": "#ffe66d",
    "S22": "#c77dff",
}

TRACE_COLOR_DEFAULT = "#ffffff"

DISTORTION_OVERLAY_COLORS: list[str] = [
    "#888888",  # n=0 constant  (~0° sat, neutral gray)
    "#cc8800",  # n=1 linear    (~45°,  amber)
    "#22aa44",  # n=2 parabolic (~135°, green)
    "#cc2233",  # n=3 cubic     (~350°, red)
    "#00aacc",  # n=4 quartic   (~190°, cyan)
    "#7733cc",  # n=5 quintic   (~275°, violet)
]
DISTORTION_OVERLAY_STYLES: list = [
    "-",
    "--",
    "-.",
    ":",
    (0, (5, 2)),
    (0, (3, 1, 1, 1)),
]
DISTORTION_OVERLAY_LABELS: list[str] = [
    "constant",
    "linear",
    "parabolic",
    "cubic",
    "quartic",
    "quintic",
]

# ---------------------------------------------------------------------------
# Color helpers
# ---------------------------------------------------------------------------


def hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    """
    Convert a hex color string into an (R, G, B) tuple of integers.

    Accepts strings in the forms "#RRGGBB", "RRGGBB", "#RGB", or "RGB".
    A leading "#" is optional; 3-digit shorthand is expanded to 6-digit form.

    Parameters:
        hex_color: Hex color string to convert.

    Returns:
        RGB components as integers (red, green, blue).
    """
    h = hex_color.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    if len(h) != 6:
        raise ValueError(
            f"Invalid hex color {hex_color!r}: expected 3 or 6 hex digits, got {len(hex_color.lstrip('#'))}"
        )
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def get_plot_colors(theme_vars: dict[str, str] | None = None) -> dict:
    """
    Construct a plotting color scheme from Textual theme variables.

    Parameters:
        theme_vars: Mapping of Textual theme variable names to hex color strings.
            When None, a set of sensible fallback colors is used.

    Returns:
        A dictionary containing plotting colors and RGB tuples.
    """
    if theme_vars is not None:
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

    traces_rgb = {}
    for param, hex_val in traces.items():
        try:
            traces_rgb[param] = hex_to_rgb(hex_val)
        except (ValueError, IndexError):
            traces_rgb[param] = (255, 255, 255)

    def _resolve_color(
        theme_color: str | None, fallback: str
    ) -> tuple[str, tuple[int, int, int]]:
        """
        Resolve a theme hex color string and return the chosen hex value and RGB tuple.
        """
        if theme_color:
            try:
                return theme_color, hex_to_rgb(theme_color)
            except (ValueError, IndexError):
                pass
        return fallback, hex_to_rgb(fallback)

    distortion_overlays = list(DISTORTION_OVERLAY_COLORS)
    distortion_overlays_rgb = [hex_to_rgb(h) for h in DISTORTION_OVERLAY_COLORS]

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


# ---------------------------------------------------------------------------
# Terminal font detection
# ---------------------------------------------------------------------------


def get_terminal_font() -> tuple[str, float | None]:
    """Detect the terminal's font family and size by parsing its config file.

    Uses TERM_PROGRAM to identify the terminal emulator, then reads its
    configuration file to extract the font family and size.
    Falls back to ('monospace', None).

    Supported terminals: Ghostty, Kitty, Alacritty, WezTerm, iTerm2,
    Windows Terminal.
    """
    import json

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
            for line in cfg.read_text(encoding="utf-8").splitlines():
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
            if not font_size:
                font_size = 13.0

    try:
        if "ghostty" in term:
            _parse_ghostty_config()

        elif "kitty" in term:
            cfg = home / ".config" / "kitty" / "kitty.conf"
            if cfg.exists():
                for line in cfg.read_text(encoding="utf-8").splitlines():
                    line = line.strip()
                    if line.startswith("font_family") and not font_name:
                        font_name = line.split(None, 1)[1].strip().strip("\"'")
                    elif line.startswith("font_size") and not font_size:
                        try:
                            font_size = float(line.split(None, 1)[1].strip())
                        except (ValueError, IndexError):
                            pass

        elif "alacritty" in term:
            for name in ("alacritty.toml", "alacritty.yml"):
                cfg = home / ".config" / "alacritty" / name
                if cfg.exists():
                    text = cfg.read_text(encoding="utf-8")
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
            for cfg in (
                home / ".config" / "wezterm" / "wezterm.lua",
                home / ".wezterm.lua",
            ):
                if cfg.exists():
                    text = cfg.read_text(encoding="utf-8")
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
            if platform.system() == "Darwin":
                result = subprocess.run(
                    ["defaults", "read", "com.googlecode.iterm2", "Normal Font"],
                    capture_output=True,
                    text=True,
                    timeout=2,
                )
                if result.returncode == 0:
                    raw = result.stdout.strip()
                    parts = raw.rsplit(" ", 1)
                    font_name = parts[0].replace("-Regular", "")
                    if len(parts) == 2:
                        try:
                            font_size = float(parts[1])
                        except ValueError:
                            pass

        elif platform.system() == "Windows":
            local_app = os.environ.get("LOCALAPPDATA", "")
            if local_app:
                wt_dir = Path(local_app) / "Packages"
                if wt_dir.exists():
                    for pkg in wt_dir.iterdir():
                        if "WindowsTerminal" in pkg.name:
                            settings = pkg / "LocalState" / "settings.json"
                            if settings.exists():
                                data = json.loads(settings.read_text(encoding="utf-8"))
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

        if not font_name and "ghostty" in term:
            _parse_ghostty_config()

    except Exception as exc:
        _log.debug("Terminal font detection failed: %s", exc, exc_info=True)

    resolved_name = "monospace"
    if font_name:
        if font_name in available_fonts:
            resolved_name = font_name
        else:
            lower_name = font_name.lower()
            for available_font in available_fonts:
                if available_font.lower() == lower_name:
                    resolved_name = available_font
                    break
            else:
                candidates = [
                    available_font
                    for available_font in available_fonts
                    if lower_name in available_font.lower()
                    or available_font.lower() in lower_name
                ]
                if candidates:
                    resolved_name = min(candidates, key=len)

    return resolved_name, font_size


# ---------------------------------------------------------------------------
# Matplotlib plot creation
# ---------------------------------------------------------------------------


def create_matplotlib_plot(
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
    font_family: str | None = None,
    font_size: float | None = None,
) -> None:
    """Create a plot using matplotlib with dark theme matching terminal UI."""
    if font_family is None or font_size is None:
        detected_family, detected_size = get_terminal_font()
        font_family = font_family or detected_family
        font_size = font_size or detected_size

    if colors is None:
        colors = get_plot_colors()
    fg_color = colors["fg"]
    grid_color = colors["grid"]

    if pixel_width and pixel_height:
        fig_width = pixel_width / dpi
        fig_height = pixel_height / dpi
    else:
        fig_width = 10
        fig_height = 5

    with rc_context({"font.family": font_family}):
        base_size = (font_size if font_size else 10.0) / render_scale

        fig, ax = plt.subplots(figsize=(fig_width, fig_height))
        fig.patch.set_alpha(0.0 if transparent else 1.0)
        if not transparent:
            fig.patch.set_facecolor(colors["bg"])
        ax.set_facecolor("none" if transparent else colors["bg"])

        freq_mhz = freqs / 1e6

        if plot_type == "magnitude":
            ylabel = "Magnitude (dB)"
            title = "S-Parameter Magnitude"
        elif plot_type == "phase":
            ylabel = "Phase (degrees)"
            title = "S-Parameter Phase (Unwrapped)"
        else:
            ylabel = "Phase (degrees)"
            title = "S-Parameter Phase (Raw)"

        all_y_data = []
        for param in plot_params:
            if plot_type == "magnitude":
                data = sparams[param][0]
            elif plot_type == "phase":
                data = unwrap_phase(sparams[param][1])
            else:
                data = sparams[param][1]

            all_y_data.append(data)
            ax.plot(
                freq_mhz,
                data,
                label=param,
                color=colors["traces"].get(param, colors["default_trace"]),
                linewidth=1.5,
            )

        if all_y_data:
            combined_data = np.concatenate(all_y_data)
            if y_min is None or y_max is None:
                auto_y_min, auto_y_max = calculate_plot_range_with_outlier_filtering(
                    combined_data, outlier_percentile=1.0, safety_margin=0.05
                )
                final_y_min = y_min if y_min is not None else auto_y_min
                final_y_max = y_max if y_max is not None else auto_y_max
            else:
                final_y_min = y_min
                final_y_max = y_max
            ax.set_ylim(final_y_min, final_y_max)

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

        for spine in ax.spines.values():
            spine.set_edgecolor(grid_color)
            spine.set_linewidth(1)

        plt.tight_layout()
        plt.savefig(
            output_path,
            dpi=dpi,
            facecolor=fig.get_facecolor(),
            edgecolor="none",
            bbox_inches="tight",
            transparent=transparent,
        )
        plt.close(fig)
