"""Plot color helpers for the TINA GUI."""

from __future__ import annotations

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

# Fixed hue-wheel palette for distortion overlays — guaranteed distinct
# regardless of theme.
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
