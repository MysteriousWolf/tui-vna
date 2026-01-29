"""
Color utilities for terminal UI and plotting.

Provides color conversion and theme management functions.
"""

from ..config.constants import (
    DEFAULT_BACKGROUND_COLOR,
    DEFAULT_FOREGROUND_COLOR,
    DEFAULT_GRID_COLOR,
    SPARAM_FALLBACK_COLORS,
    SPARAM_THEME_KEYS,
    TRACE_COLOR_DEFAULT,
)


def hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    """
    Convert a hex color string to an (R, G, B) tuple.

    Args:
        hex_color: Hex color string (e.g., "#ff6b6b" or "abc")

    Returns:
        RGB tuple with values 0-255
    """
    h = hex_color.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def get_plot_colors(theme_vars: dict[str, str] | None = None) -> dict:
    """
    Build plot color scheme from Textual theme variables.

    Args:
        theme_vars: Dictionary of Textual theme variable names to hex colors

    Returns:
        Dictionary with keys:
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
        fg = theme_vars.get(
            "foreground", theme_vars.get("text", DEFAULT_FOREGROUND_COLOR)
        )
        bg = theme_vars.get("background", DEFAULT_BACKGROUND_COLOR)
        surface = theme_vars.get("surface", bg)
        grid = theme_vars.get(
            "panel", theme_vars.get("surface-darken-1", DEFAULT_GRID_COLOR)
        )
    else:
        traces = dict(SPARAM_FALLBACK_COLORS)
        fg = DEFAULT_FOREGROUND_COLOR
        bg = DEFAULT_BACKGROUND_COLOR
        surface = bg
        grid = DEFAULT_GRID_COLOR

    # Build RGB tuples for plotext (which doesn't support hex strings)
    traces_rgb = {}
    for param, hex_val in traces.items():
        try:
            traces_rgb[param] = hex_to_rgb(hex_val)
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
