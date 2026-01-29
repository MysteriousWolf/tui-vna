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

# S-parameter theme color mapping
# Maps S-parameters to Textual CSS theme variable names
SPARAM_THEME_KEYS = {
    "S11": "error",
    "S21": "primary",
    "S12": "accent",
    "S22": "success",
}

# Fallback colors for S-parameters (hex strings)
SPARAM_FALLBACK_COLORS = {
    "S11": "#ff6b6b",
    "S21": "#4ecdc4",
    "S12": "#ffe66d",
    "S22": "#c77dff",
}

# Default trace color
TRACE_COLOR_DEFAULT = "#ffffff"

# Default theme colors
DEFAULT_FOREGROUND_COLOR = "#e6e1dc"
DEFAULT_BACKGROUND_COLOR = "#0e1419"
DEFAULT_GRID_COLOR = "#2d3640"

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
