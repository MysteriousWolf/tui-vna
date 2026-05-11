"""Custom TINA application theme."""

from textual.theme import Theme

_PRIMARY = "#4a9eda"

TINA_THEME = Theme(
    name="tina",
    dark=True,
    # --- Primary palette ---
    # Instrument blue: buttons, tab highlights, S21 traces
    primary=_PRIMARY,
    # Deeper blue for secondary chrome
    secondary="#3278b5",
    # Teal: distinct from blue, used for S12 traces and accent highlights
    accent="#00c8b8",
    # --- Backgrounds (darkest → lightest: bg → surface → panel → boost) ---
    # Pure neutral grays — no color cast
    background="#121212",
    surface="#1b1b1b",
    panel="#252525",
    boost="#2f2f2f",
    # --- Text ---
    foreground="#c8d3e0",
    # --- Status / S-param trace colors ---
    # S11 traces and error states
    error="#e05555",
    # Cursors and warnings
    warning="#d4923a",
    # S22 traces and success states
    success="#4ac48a",
    # --- Shade spread: default 0.15, keep it to preserve legibility ---
    luminosity_spread=0.15,
    # --- Fine-grained widget overrides ---
    variables={
        # Input cursor: use primary blue on dark background, no text decoration
        "input-cursor-background": _PRIMARY,
        "input-cursor-foreground": "#121212",
        "input-cursor-text-style": "none",
        # Footer key hints match primary
        "footer-key-foreground": _PRIMARY,
        # Text selection: semi-transparent primary
        "input-selection-background": f"color-mix(in srgb, {_PRIMARY} 35%, transparent)",
        # Button labels on primary-colored buttons read dark
        "button-foreground": "#121212",
    },
)
