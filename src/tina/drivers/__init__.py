"""
VNA drivers package with automatic driver discovery.

New drivers are automatically discovered - just create a new file
in this directory that defines a VNABase subclass with an idn_matcher.
"""

from .base import (
    IDNInfo,
    StatusCapableDriver,
    TriggerStateDriver,
    VNABase,
    VNAConfig,
    detect_vna_driver,
    discover_drivers,
    list_available_drivers,
)

# Import specific drivers for direct access if needed
from .hp_e5071b import HPE5071B
from .keysight_p5007a import KeysightP5007A

__all__ = [
    "IDNInfo",
    "VNABase",
    "VNAConfig",
    "StatusCapableDriver",
    "HPE5071B",
    "KeysightP5007A",
    "detect_vna_driver",
    "discover_drivers",
    "list_available_drivers",
    "TriggerStateDriver",
]
