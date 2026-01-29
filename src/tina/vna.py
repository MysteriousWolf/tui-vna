"""
HP E5071B Vector Network Analyzer control module.

Provides clean interface for controlling the VNA, performing measurements,
and retrieving S-parameter data.
"""

import socket
import time
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import numpy as np
import pyvisa


@dataclass
class VNAConfig:
    """VNA configuration parameters."""

    host: str = ""  # No default IP to avoid exposing network configs in git
    port: str = "inst0"
    protocol: str = "TCPIP0"
    suffix: str = "INSTR"
    timeout_ms: int = 60000

    # Measurement settings
    start_freq_hz: float = 1e6  # 1 MHz
    stop_freq_hz: float = 1100e6  # 1100 MHz
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


class VNA:
    """HP E5071B VNA controller."""

    def __init__(self, config: Optional[VNAConfig] = None):
        """
        Initialize VNA controller.

        Args:
            config: VNA configuration (uses defaults if None)
        """
        self.config = config or VNAConfig()
        self.inst: Optional[pyvisa.resources.Resource] = None
        self._connected = False
        self._idn: str = ""

    def _check_host_reachable(self, host: str, timeout: float = 0.5) -> bool:
        """Quick check if host is reachable via TCP (VXI-11 portmapper on 111 or SCPI on 5025)."""
        for port in [111, 5025]:
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                    sock.settimeout(timeout)
                    result = sock.connect_ex((host, port))
                    if result == 0:
                        return True
            except (socket.error, OSError):
                continue
        return False

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

        def report(msg: str, pct: float) -> None:
            if progress_callback:
                progress_callback(msg, pct)

        address = self.config.build_address()

        # Quick reachability check first (0.5s timeout per port)
        report("Checking host...", 10)
        if not self._check_host_reachable(self.config.host):
            self._connected = False
            raise ConnectionError(f"Host {self.config.host} not reachable")

        # Use pyvisa-py backend only (faster, no NI-VISA dependency)
        report("Initializing VISA...", 25)
        try:
            rm = pyvisa.ResourceManager("@py")
        except Exception:
            rm = pyvisa.ResourceManager()

        report("Opening connection...", 50)
        try:
            self.inst = rm.open_resource(address)
            self.inst.timeout = 5000  # 5s timeout for commands

            report("Verifying connection...", 80)
            self._idn = self.inst.query("*IDN?").strip()

            report("Connected", 100)
            self._connected = True
            return True

        except Exception as e:
            self._cleanup_failed_connection()
            raise e

    def _cleanup_failed_connection(self) -> None:
        """Clean up resources after failed connection attempt."""
        if self.inst:
            try:
                self.inst.close()
            except Exception:
                pass
            self.inst = None
        self._connected = False

    def disconnect(self) -> None:
        """Disconnect from VNA."""
        if self.inst:
            try:
                self.inst.close()
            except Exception:
                pass
            self.inst = None
        self._connected = False
        self._idn = ""

    @property
    def idn(self) -> str:
        """Return instrument identification string."""
        return self._idn

    def is_connected(self) -> bool:
        """Check if connected to VNA."""
        return self._connected

    def _ensure_connected(self) -> None:
        """Ensure VNA is connected, raise error if not."""
        if not self._connected or self.inst is None:
            raise RuntimeError("Not connected to VNA")

    def _send_command(self, command: str) -> None:
        """Send SCPI command."""
        self._ensure_connected()
        self.inst.write(command)

    def _query(self, command: str) -> str:
        """Send SCPI query and return response."""
        self._ensure_connected()
        return self.inst.query(command)

    def _query_ascii_values(self, command: str) -> List[float]:
        """Query ASCII values."""
        self._ensure_connected()
        return self.inst.query_ascii_values(command)

    def configure_frequency(self) -> None:
        """Configure frequency range from config."""
        if self.config.set_freq_range:
            self._send_command(f"SENS1:FREQ:STAR {self.config.start_freq_hz}")
            self._send_command(f"SENS1:FREQ:STOP {self.config.stop_freq_hz}")
            time.sleep(0.5)

    def configure_measurements(self) -> None:
        """Configure measurement settings."""
        # ASCII data format
        self._send_command("FORM:DATA ASCII")

        # Continuous mode OFF for single sweep control
        self._send_command("INIT1:CONT OFF")

        # Linear sweep
        self._send_command("SENS1:SWE:TYPE LIN")

        # Sweep points
        if self.config.set_sweep_points:
            self._send_command(f"SENS1:SWE:POIN {self.config.sweep_points}")

        # Averaging
        avg_state = "ON" if self.config.enable_averaging else "OFF"
        self._send_command(f"SENS1:AVER:STAT {avg_state}")

        # Averaging count (only if override enabled)
        if self.config.set_averaging_count:
            self._send_command(f"SENS1:AVER:COUN {self.config.averaging_count}")

        time.sleep(0.5)

    def setup_s_parameters(self) -> None:
        """Setup S-parameter measurements (S11, S21, S12, S22)."""
        # Set parameter count to 4
        self._send_command("CALC1:PAR:COUN 4")
        time.sleep(0.3)

        # Define each S-parameter
        sparams = ["S11", "S21", "S12", "S22"]
        for idx, param in enumerate(sparams, start=1):
            self._send_command(f"CALC1:PAR{idx}:DEF {param}")
            time.sleep(0.2)
            self._send_command(f"CALC1:PAR{idx}:SEL")
            time.sleep(0.1)

        # Select first parameter as active
        self._send_command("CALC1:PAR1:SEL")
        time.sleep(0.1)

        # Flush measurement to apply settings
        self._send_command("ABOR")
        time.sleep(0.2)
        self._send_command("INIT1")

        # Wait for completion
        self._wait_for_operation_complete(timeout_seconds=30)

    def _wait_for_operation_complete(self, timeout_seconds: float = 60.0) -> None:
        """
        Wait for VNA operation to complete using *OPC? query.

        Args:
            timeout_seconds: Maximum time to wait for completion

        Raises:
            TimeoutError: If operation doesn't complete within timeout
        """
        timeout = time.time() + timeout_seconds
        while time.time() < timeout:
            resp = self._query("*OPC?")
            if resp.strip() in ("1", "+1"):
                return
            time.sleep(0.1)

        raise TimeoutError(
            f"Operation did not complete within {timeout_seconds} seconds"
        )

    def trigger_sweep(self) -> None:
        """Trigger a sweep and wait for completion."""
        self._send_command("ABOR")
        time.sleep(0.2)
        self._send_command("INIT1")
        self._wait_for_operation_complete(timeout_seconds=60.0)

    def get_frequency_axis(self) -> np.ndarray:
        """
        Get frequency axis points.

        Returns:
            Numpy array of frequencies in Hz
        """
        freqs = self._query_ascii_values("SENS1:FREQ:DATA?")
        return np.array(freqs, dtype=float)

    def get_sparam_data(self, param_num: int) -> Tuple[np.ndarray, np.ndarray]:
        """
        Get S-parameter data for a specific parameter.

        Args:
            param_num: Parameter number (1-4 for S11, S21, S12, S22)

        Returns:
            Tuple of (magnitude_db, phase_deg) numpy arrays
        """
        self._send_command(f"CALC1:PAR{param_num}:SEL")
        time.sleep(0.1)

        # Query complex data (real/imag pairs)
        data = self._query_ascii_values("CALC1:DATA:SDAT?")

        # Ensure even length
        if len(data) % 2 != 0:
            data = data[:-1]

        # Parse real and imaginary parts
        real = np.array(data[0::2])
        imag = np.array(data[1::2])

        # Convert to magnitude (dB) and phase (degrees)
        comp = real + 1j * imag
        mag_db = 20 * np.log10(np.abs(comp) + 1e-15)
        phase_deg = np.angle(comp, deg=True)

        return mag_db, phase_deg

    def get_all_sparameters(self) -> Dict[str, Tuple[np.ndarray, np.ndarray]]:
        """
        Get all S-parameter data.

        Returns:
            Dictionary with keys 'S11', 'S21', 'S12', 'S22'
            and values as (magnitude_db, phase_deg) tuples
        """
        sparams = {}
        param_names = ["S11", "S21", "S12", "S22"]

        for idx, name in enumerate(param_names, start=1):
            sparams[name] = self.get_sparam_data(idx)

        return sparams

    def perform_measurement(
        self,
    ) -> Tuple[np.ndarray, Dict[str, Tuple[np.ndarray, np.ndarray]]]:
        """
        Perform complete measurement cycle.

        Returns:
            Tuple of (frequencies, s_parameters_dict)
        """
        # Configure VNA
        self.configure_frequency()
        self.configure_measurements()
        self.setup_s_parameters()

        # Trigger sweep
        self.trigger_sweep()

        # Get data
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
