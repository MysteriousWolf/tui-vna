"""Custom TINA application theme."""

from textual.theme import Theme

TINA_THEME = Theme(
    name="tina",
    dark=True,
    # --- Primary palette ---
    # Instrument blue: buttons, tab highlights, S21 traces
    primary="#4a9eda",
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
        # Block cursor: use primary blue on dark background, no text decoration
        "block-cursor-background": "#4a9eda",
        "block-cursor-foreground": "#121212",
        "block-cursor-text-style": "none",
        # Footer key hints match primary
        "footer-key-foreground": "#4a9eda",
        # Text selection: semi-transparent primary
        "input-selection-background": "#4a9eda 35%",
        # Button labels on primary-colored buttons read dark
        "button-color-foreground": "#121212",
        # No extra text style on focused buttons (underline looks noisy)
        "button-focus-text-style": "none",
    },
)
