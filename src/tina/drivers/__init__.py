"""
VNA drivers package with automatic driver discovery.

New drivers are automatically discovered - just create a new file
in this directory that defines a VNABase subclass with an idn_matcher.
"""

from .base import (
    VNABase,
    VNAConfig,
    detect_vna_driver,
    discover_drivers,
    list_available_drivers,
)

# Import specific drivers for direct access if needed
from .hp_e5071b import HPE5071B

__all__ = [
    "VNABase",
    "VNAConfig",
    "HPE5071B",
    "detect_vna_driver",
    "discover_drivers",
    "list_available_drivers",
]
