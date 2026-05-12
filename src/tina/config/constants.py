"""
Configuration constants for the VNA control application.

This module centralizes all hardcoded values to make the application
easier to maintain and configure.
"""

# Frequency defaults (in Hz)
DEFAULT_START_FREQ_HZ = 1e6  # 1 MHz
DEFAULT_STOP_FREQ_HZ = 1100e6  # 1100 MHz

# Sweep parameters
DEFAULT_SWEEP_POINTS = 601
DEFAULT_AVERAGING_COUNT = 16

# Timeout values (in milliseconds)
DEFAULT_VISA_TIMEOUT_MS = 60000
COMMAND_TIMEOUT_MS = 5000
SOCKET_TIMEOUT_SEC = 0.5
OPERATION_TIMEOUT_SEC = 60.0
SWEEP_TIMEOUT_SEC = 60.0
PARAM_SETUP_TIMEOUT_SEC = 30.0

# Reference impedance (Ohms)
DEFAULT_REFERENCE_IMPEDANCE = 50.0

# Math constants
LOG_EPSILON = 1e-15  # Epsilon to avoid log(0)

# Plot settings
DEFAULT_PLOT_DPI = 150
DEFAULT_PLOT_RENDER_SCALE = 1
DEFAULT_OUTLIER_PERCENTILE = 1.0  # Percentage of outliers to filter on each end
DEFAULT_SAFETY_MARGIN = 0.05  # Safety margin beyond filtered range
DEFAULT_TERMINAL_PLOT_HEIGHT = 25  # Lines

# ---------------------------------------------------------------------------
# TINA theme palette — single source of truth for all color hex values.
# theme.py and every fallback path must import from here, never re-define.
# ---------------------------------------------------------------------------
THEME_PRIMARY = "#4a9eda"
THEME_SECONDARY = "#3278b5"
THEME_ACCENT = "#00c8b8"
THEME_BACKGROUND = "#121212"
THEME_SURFACE = "#1b1b1b"
THEME_PANEL = "#252525"
THEME_BOOST = "#2f2f2f"
THEME_FOREGROUND = "#c8d3e0"
THEME_ERROR = "#e05555"
THEME_WARNING = "#d4923a"
THEME_SUCCESS = "#4ac48a"

# Distortion overlay colors — cycling palette for polynomial components (n=0…5).
DISTORTION_OVERLAY_COLORS: list[str] = [
    "#888888",  # n=0 constant  (~0° sat, neutral gray)
    "#cc8800",  # n=1 linear    (~45°,  amber)
    "#22aa44",  # n=2 parabolic (~135°, green)
    "#cc2233",  # n=3 cubic     (~350°, red)
    "#00aacc",  # n=4 quartic   (~190°, cyan)
    "#7733cc",  # n=5 quintic   (~275°, violet)
]

# S-parameter theme color mapping
# Maps S-parameters to Textual CSS theme variable names
SPARAM_THEME_KEYS = {
    "S11": "error",
    "S21": "primary",
    "S12": "accent",
    "S22": "success",
}

# Fallback colors for S-parameters — must match the theme palette above.
SPARAM_FALLBACK_COLORS = {
    "S11": THEME_ERROR,
    "S21": THEME_PRIMARY,
    "S12": THEME_ACCENT,
    "S22": THEME_SUCCESS,
}

# Default trace color (white = unknown/unthemed trace)
TRACE_COLOR_DEFAULT = "#ffffff"

# Default theme colors used when no live theme variables are available.
DEFAULT_FOREGROUND_COLOR = THEME_FOREGROUND
DEFAULT_BACKGROUND_COLOR = THEME_BACKGROUND
DEFAULT_GRID_COLOR = THEME_PANEL

# SCPI response truncation
SCPI_RESPONSE_TRUNCATE_LENGTH = 200

# Message poll interval (seconds)
MESSAGE_POLL_INTERVAL_SEC = 0.05

# Worker thread shutdown timeout (seconds)
WORKER_SHUTDOWN_TIMEOUT_SEC = 5.0

# Temporary directory name for plots
PLOT_TEMP_DIR_NAME = "tui-vna-plots"

# Default VISA ports (in order of preference)
DEFAULT_VISA_PORTS = [
    "inst0",
    "inst1",
    "inst2",
    "inst3",
    "hislip0",
    "gpib0,16",
]

# History limits
MAX_HOST_HISTORY = 10
MAX_PORT_HISTORY = 10

# Frequency unit conversion factors
FREQ_UNIT_CONVERSIONS = {
    "Hz": 1.0,
    "kHz": 1e3,
    "MHz": 1e6,
    "GHz": 1e9,
}

# VISA connection parameters
DEFAULT_VISA_PROTOCOL = "TCPIP0"
DEFAULT_VISA_SUFFIX = "INSTR"
DEFAULT_VISA_PORT = "inst0"

# Port check ports (for connection testing)
VXI11_PORTMAPPER_PORT = 111
SCPI_RAW_PORT = 5025
