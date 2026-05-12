"""Custom TINA application theme."""

from textual.theme import Theme

from tina.config.constants import (
    THEME_ACCENT,
    THEME_BACKGROUND,
    THEME_BOOST,
    THEME_ERROR,
    THEME_FOREGROUND,
    THEME_PANEL,
    THEME_PRIMARY,
    THEME_SECONDARY,
    THEME_SUCCESS,
    THEME_SURFACE,
    THEME_WARNING,
)

TINA_THEME = Theme(
    name="tina",
    dark=True,
    # --- Primary palette ---
    # Instrument blue: buttons, tab highlights, S21 traces
    primary=THEME_PRIMARY,
    # Deeper blue for secondary chrome
    secondary=THEME_SECONDARY,
    # Teal: distinct from blue, used for S12 traces and accent highlights
    accent=THEME_ACCENT,
    # --- Backgrounds (darkest → lightest: bg → surface → panel → boost) ---
    # Pure neutral grays — no color cast
    background=THEME_BACKGROUND,
    surface=THEME_SURFACE,
    panel=THEME_PANEL,
    boost=THEME_BOOST,
    # --- Text ---
    foreground=THEME_FOREGROUND,
    # --- Status / S-param trace colors ---
    # S11 traces and error states
    error=THEME_ERROR,
    # Cursors and warnings
    warning=THEME_WARNING,
    # S22 traces and success states
    success=THEME_SUCCESS,
    # --- Shade spread: default 0.15, keep it to preserve legibility ---
    luminosity_spread=0.15,
    # --- Fine-grained widget overrides ---
    variables={
        # Input cursor: use primary blue on dark background, no text decoration
        "input-cursor-background": THEME_PRIMARY,
        "input-cursor-foreground": THEME_BACKGROUND,
        "input-cursor-text-style": "none",
        # Footer key hints match primary
        "footer-key-foreground": THEME_PRIMARY,
        # Text selection: semi-transparent primary (35% opacity = 0x59 alpha)
        "input-selection-background": f"{THEME_PRIMARY}59",
        # Button labels on primary-colored buttons read dark
        "button-foreground": THEME_BACKGROUND,
    },
)
