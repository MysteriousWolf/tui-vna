"""
Abstract base class for VNA drivers with dynamic driver discovery.

This module provides a plugin-style architecture where new VNA drivers
can be added by simply creating a new file in the drivers/ directory.
Each driver registers itself by implementing VNABase and providing
an IDN pattern matcher.
"""

import importlib
import inspect
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import numpy as np


@dataclass
class VNAConfig:
    """VNA configuration parameters."""

    host: str = ""
    port: str = "inst0"
    protocol: str = "TCPIP0"
    suffix: str = "INSTR"
    timeout_ms: int = 60000

    # Measurement settings
    start_freq_hz: float = 1e6
    stop_freq_hz: float = 1100e6
    sweep_points: int = 601

    # Feature flags
    set_freq_range: bool = False
    set_sweep_points: bool = True
    enable_averaging: bool = False
    averaging_count: int = 16
    set_averaging_count: bool = False

    def build_address(self) -> str:
        """Build VISA resource address string."""
        if not self.host:
            raise ValueError("Host IP address must be configured before connecting")
        return f"{self.protocol}::{self.host}::{self.port}::{self.suffix}"


class VNABase(ABC):
    """Abstract base class for VNA controllers."""

    # Class attribute for driver registration
    # Subclasses should override this with their IDN detection function
    idn_matcher: Callable[[str], bool] | None = None
    driver_name: str = "Unknown"

    def __init__(self, config: VNAConfig | None = None):
        """
        Initialize VNA controller.

        Args:
            config: VNA configuration (uses defaults if None)
        """
        self.config = config or VNAConfig()
        self._connected = False
        self._idn: str = ""

    @abstractmethod
    def connect(self, progress_callback=None) -> bool:
        """
        Connect to VNA.

        Args:
            progress_callback: Optional callback(message, progress_pct) for status updates

        Returns:
            True if connection successful

        Raises:
            ConnectionError: If host is not reachable
            ValueError: If host is not configured
        """
        pass

    @abstractmethod
    def disconnect(self) -> None:
        """Disconnect from VNA."""
        pass

    @property
    def idn(self) -> str:
        """Return instrument identification string."""
        return self._idn

    def is_connected(self) -> bool:
        """Check if connected to VNA."""
        return self._connected

    @abstractmethod
    def configure_frequency(self) -> None:
        """Configure frequency range from config."""
        pass

    @abstractmethod
    def configure_measurements(self) -> None:
        """Configure measurement settings."""
        pass

    @abstractmethod
    def setup_s_parameters(self) -> None:
        """Setup S-parameter measurements."""
        pass

    @abstractmethod
    def trigger_sweep(self) -> None:
        """Trigger a sweep and wait for completion."""
        pass

    @abstractmethod
    def get_frequency_axis(self) -> np.ndarray:
        """
        Get frequency axis points.

        Returns:
            Numpy array of frequencies in Hz
        """
        pass

    @abstractmethod
    def get_sparam_data(self, param_num: int) -> tuple[np.ndarray, np.ndarray]:
        """
        Get S-parameter data for a specific parameter.

        Args:
            param_num: Parameter number (model-specific)

        Returns:
            Tuple of (magnitude_db, phase_deg) numpy arrays
        """
        pass

    @abstractmethod
    def get_all_sparameters(self) -> dict[str, tuple[np.ndarray, np.ndarray]]:
        """
        Get all S-parameter data.

        Returns:
            Dictionary with S-parameter names as keys
            and (magnitude_db, phase_deg) tuples as values
        """
        pass

    def perform_measurement(
        self,
    ) -> tuple[np.ndarray, dict[str, tuple[np.ndarray, np.ndarray]]]:
        """
        Perform complete measurement cycle.

        Returns:
            Tuple of (frequencies, s_parameters_dict)
        """
        self.configure_frequency()
        self.configure_measurements()
        self.setup_s_parameters()
        self.trigger_sweep()

        freqs = self.get_frequency_axis()
        sparams = self.get_all_sparameters()

        return freqs, sparams

    def __enter__(self):
        """Context manager entry."""
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.disconnect()


# Driver registry - populated automatically by scanning drivers/ directory
_DRIVER_REGISTRY: dict[str, type[VNABase]] = {}


def discover_drivers() -> dict[str, type[VNABase]]:
    """
    Automatically discover and load all VNA drivers from the drivers/ directory.

    Scans all Python files in drivers/, imports them, and finds all VNABase
    subclasses that have an idn_matcher function defined.

    Returns:
        Dictionary mapping driver names to driver classes
    """
    global _DRIVER_REGISTRY

    if _DRIVER_REGISTRY:
        # Already discovered
        return _DRIVER_REGISTRY

    drivers_dir = Path(__file__).parent

    # Find all Python files except base.py and __init__.py
    driver_files = [
        f
        for f in drivers_dir.glob("*.py")
        if f.stem not in ("base", "__init__", "scpi_commands")
    ]

    for driver_file in driver_files:
        module_name = f".{driver_file.stem}"
        try:
            # Import the driver module
            module = importlib.import_module(module_name, package="tina.drivers")

            # Find all VNABase subclasses in the module
            for name, obj in inspect.getmembers(module, inspect.isclass):
                if (
                    issubclass(obj, VNABase)
                    and obj is not VNABase
                    and hasattr(obj, "idn_matcher")
                    and obj.idn_matcher is not None
                ):
                    driver_name = getattr(obj, "driver_name", name)
                    _DRIVER_REGISTRY[driver_name] = obj

        except Exception:
            # Silently skip drivers that fail to load
            # You could add logging here if needed
            pass

    return _DRIVER_REGISTRY


def detect_vna_driver(idn_string: str) -> type[VNABase] | None:
    """
    Detect the appropriate VNA driver from an IDN string.

    Automatically discovers all drivers in the drivers/ folder and tests
    each one's idn_matcher function to find a match.

    Args:
        idn_string: Response from *IDN? query

    Returns:
        VNA driver class that matches, or None if not recognized

    Example:
        >>> driver_class = detect_vna_driver("HEWLETT-PACKARD,E5071B,...")
        >>> if driver_class:
        >>>     vna = driver_class(config)
        >>>     vna.connect()
    """
    drivers = discover_drivers()

    for driver_name, driver_class in drivers.items():
        try:
            if driver_class.idn_matcher and driver_class.idn_matcher(idn_string):
                return driver_class
        except Exception:
            # Skip drivers with broken matchers
            continue

    return None


def list_available_drivers() -> list[str]:
    """
    Get a list of all available VNA drivers.

    Returns:
        List of driver names
    """
    drivers = discover_drivers()
    return list(drivers.keys())
