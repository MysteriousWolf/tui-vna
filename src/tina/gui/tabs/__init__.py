"""Tab composition helpers for the TINA GUI."""

from .log import compose_log_tab
from .measurement import compose_measurement_tab
from .setup import compose_setup_tab
from .tools import compose_tools_tab

__all__ = [
    "compose_log_tab",
    "compose_measurement_tab",
    "compose_setup_tab",
    "compose_tools_tab",
]
