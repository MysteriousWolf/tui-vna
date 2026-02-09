"""
HP E5071B Vector Network Analyzer driver.

Implements VNABase interface for HP/Agilent E5071B series VNAs.
"""

import socket
import time
from typing import Dict, List, Optional, Tuple

import numpy as np
import pyvisa

from ..config.constants import (
    COMMAND_TIMEOUT_MS,
    LOG_EPSILON,
    OPERATION_TIMEOUT_SEC,
    PARAM_SETUP_TIMEOUT_SEC,
    SCPI_RAW_PORT,
    SOCKET_TIMEOUT_SEC,
    SWEEP_TIMEOUT_SEC,
    VXI11_PORTMAPPER_PORT,
)
from .base import VNABase, VNAConfig
from .scpi_commands import (
    CMD_ABORT,
    CMD_GET_FREQ_DATA,
    CMD_GET_INIT_CONTINUOUS,
    CMD_GET_SDATA,
    CMD_GET_TRIGGER_SOURCE,
    CMD_IDN,
    CMD_INIT,
    CMD_INIT_CONTINUOUS_OFF,
    CMD_OPC,
    CMD_SET_FORMAT_ASCII,
    CMD_SET_SWEEP_LINEAR,
    CMD_SET_TRIGGER_BUS,
    cmd_define_param,
    cmd_select_param,
    cmd_set_averaging_count,
    cmd_set_averaging_state,
    cmd_set_freq_start,
    cmd_set_freq_stop,
    cmd_set_init_continuous,
    cmd_set_param_count,
    cmd_set_sweep_points,
    cmd_set_trigger_source,
)


class HPE5071B(VNABase):
    """HP E5071B VNA controller."""

    # Driver registration - this is how the driver auto-discovery finds us
    driver_name = "HP E5071B"

    @staticmethod
    def idn_matcher(idn_string: str) -> bool:
        """
        Check if this driver matches the given IDN string.

        Args:
            idn_string: Response from *IDN? query

        Returns:
            True if this driver supports the instrument
        """
        idn_lower = idn_string.lower()
        # Match HP, Agilent, or Keysight E5071 series
        return any(
            pattern in idn_lower
            for pattern in [
                "e5071",
                "e5071a",
                "e5071b",
                "e5071c",
            ]
        )

    def __init__(self, config: Optional[VNAConfig] = None):
        """
        Initialize HP E5071B VNA controller.

        Args:
            config: VNA configuration (uses defaults if None)
        """
        super().__init__(config)
        self.inst: Optional[pyvisa.resources.Resource] = None

    def _check_host_reachable(
        self, host: str, timeout: float = SOCKET_TIMEOUT_SEC
    ) -> bool:
        """
        Quick check if host is reachable via TCP.

        Tries VXI-11 portmapper (port 111) and SCPI raw socket (port 5025).

        Args:
            host: IP address or hostname
            timeout: Socket timeout in seconds

        Returns:
            True if host is reachable on any port
        """
        for port in [VXI11_PORTMAPPER_PORT, SCPI_RAW_PORT]:
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
        Connect to HP E5071B VNA.

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

        # Quick reachability check first
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
            self.inst.timeout = COMMAND_TIMEOUT_MS

            report("Verifying connection...", 80)
            self._idn = self.inst.query(CMD_IDN).strip()

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
        """Disconnect from HP E5071B VNA."""
        if self.inst:
            try:
                self.inst.close()
            except Exception:
                pass
            self.inst = None
        self._connected = False
        self._idn = ""

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

    def get_current_parameters(self) -> Dict[str, any]:
        """
        Query current VNA settings.

        Returns:
            Dictionary with current VNA configuration:
            - start_freq_hz: Start frequency in Hz
            - stop_freq_hz: Stop frequency in Hz
            - sweep_points: Number of sweep points
            - averaging_enabled: Whether averaging is enabled
            - averaging_count: Averaging count
        """
        from .scpi_commands import (
            CMD_GET_AVERAGING_COUNT,
            CMD_GET_AVERAGING_STATE,
            CMD_GET_FREQ_START,
            CMD_GET_FREQ_STOP,
            CMD_GET_SWEEP_POINTS,
        )

        params = {}

        try:
            params["start_freq_hz"] = float(self._query(CMD_GET_FREQ_START).strip())
        except Exception:
            params["start_freq_hz"] = None

        try:
            params["stop_freq_hz"] = float(self._query(CMD_GET_FREQ_STOP).strip())
        except Exception:
            params["stop_freq_hz"] = None

        try:
            params["sweep_points"] = int(self._query(CMD_GET_SWEEP_POINTS).strip())
        except Exception:
            params["sweep_points"] = None

        try:
            avg_state = self._query(CMD_GET_AVERAGING_STATE).strip()
            params["averaging_enabled"] = avg_state in ("1", "ON")
        except Exception:
            params["averaging_enabled"] = None

        try:
            params["averaging_count"] = int(
                self._query(CMD_GET_AVERAGING_COUNT).strip()
            )
        except Exception:
            params["averaging_count"] = None

        return params

    def configure_frequency(self) -> None:
        """Configure frequency range from config."""
        if self.config.set_freq_range:
            self._send_command(cmd_set_freq_start(self.config.start_freq_hz))
            self._send_command(cmd_set_freq_stop(self.config.stop_freq_hz))
            time.sleep(0.5)

    def configure_measurements(self) -> None:
        """Configure measurement settings (does not touch trigger/continuous mode)."""
        # ASCII data format
        self._send_command(CMD_SET_FORMAT_ASCII)

        # Linear sweep
        self._send_command(CMD_SET_SWEEP_LINEAR)

        # Sweep points
        if self.config.set_sweep_points:
            self._send_command(cmd_set_sweep_points(self.config.sweep_points))

        # Averaging
        self._send_command(cmd_set_averaging_state(self.config.enable_averaging))

        # Averaging count (only if override enabled)
        if self.config.set_averaging_count:
            self._send_command(cmd_set_averaging_count(self.config.averaging_count))

        time.sleep(0.5)

    def setup_s_parameters(self) -> None:
        """Setup S-parameter measurements (S11, S21, S12, S22)."""
        # Set parameter count to 4
        self._send_command(cmd_set_param_count(4))
        time.sleep(0.3)

        # Define each S-parameter
        sparams = ["S11", "S21", "S12", "S22"]
        for idx, param in enumerate(sparams, start=1):
            self._send_command(cmd_define_param(idx, param))
            time.sleep(0.2)
            self._send_command(cmd_select_param(idx))
            time.sleep(0.1)

        # Select first parameter as active
        self._send_command(cmd_select_param(1))
        time.sleep(0.1)

    def _wait_for_operation_complete(
        self, timeout_seconds: float = OPERATION_TIMEOUT_SEC
    ) -> None:
        """
        Wait for VNA operation to complete using *OPC? query.

        Args:
            timeout_seconds: Maximum time to wait for completion

        Raises:
            TimeoutError: If operation doesn't complete within timeout
        """
        timeout = time.time() + timeout_seconds
        while time.time() < timeout:
            resp = self._query(CMD_OPC)
            if resp.strip() in ("1", "+1"):
                return
            time.sleep(0.1)

        raise TimeoutError(
            f"Operation did not complete within {timeout_seconds} seconds"
        )

    def get_trigger_source(self) -> str:
        """
        Get current trigger source setting.

        Returns:
            Trigger source string (INT, MAN, EXT, BUS)
        """
        response = self._query(CMD_GET_TRIGGER_SOURCE).strip()
        return response

    def set_trigger_source(self, source: str) -> None:
        """
        Set trigger source.

        Args:
            source: Trigger source (INT, MAN, EXT, BUS)
        """
        self._send_command(cmd_set_trigger_source(source))
        time.sleep(0.1)

    def save_trigger_state(self) -> Tuple[str, bool]:
        """
        Save current trigger configuration.

        Returns:
            Tuple of (trigger_source, continuous_mode)
        """
        trigger = self.get_trigger_source()
        continuous_resp = self._query(CMD_GET_INIT_CONTINUOUS).strip()
        continuous = continuous_resp in ("1", "ON")
        return (trigger, continuous)

    def restore_trigger_state(self, state: Tuple[str, bool]) -> None:
        """
        Restore trigger configuration.

        Args:
            state: Tuple of (trigger_source, continuous_mode) from save_trigger_state()
        """
        trigger, continuous = state
        self._send_command(cmd_set_trigger_source(trigger))
        time.sleep(0.1)
        self._send_command(cmd_set_init_continuous(continuous))
        time.sleep(0.1)

    def trigger_sweep(self) -> None:
        """
        Trigger a single sweep and wait for completion.

        Does NOT restore trigger state - caller must use save_trigger_state()
        before calling this and restore_trigger_state() after reading all data.

        This method:
        1. Aborts any ongoing measurement
        2. Sets to single sweep mode (continuous OFF) with BUS trigger
        3. Triggers a new sweep
        4. Waits for completion
        """
        # Abort any ongoing measurement to start fresh
        self._send_command(CMD_ABORT)
        time.sleep(0.2)

        # Set to single sweep mode (continuous OFF) with BUS trigger
        self._send_command(CMD_INIT_CONTINUOUS_OFF)
        time.sleep(0.1)
        self._send_command(CMD_SET_TRIGGER_BUS)
        time.sleep(0.1)

        # Trigger new measurement
        self._send_command(CMD_INIT)
        time.sleep(0.1)

        # Wait for sweep completion
        self._wait_for_operation_complete(timeout_seconds=SWEEP_TIMEOUT_SEC)

    def get_frequency_axis(self) -> np.ndarray:
        """
        Get frequency axis points.

        Returns:
            Numpy array of frequencies in Hz
        """
        freqs = self._query_ascii_values(CMD_GET_FREQ_DATA)
        return np.array(freqs, dtype=float)

    def get_sparam_data(self, param_num: int) -> Tuple[np.ndarray, np.ndarray]:
        """
        Get S-parameter data for a specific parameter.

        Args:
            param_num: Parameter number (1-4 for S11, S21, S12, S22)

        Returns:
            Tuple of (magnitude_db, phase_deg) numpy arrays
        """
        self._send_command(cmd_select_param(param_num))
        time.sleep(0.1)

        # Query complex data (real/imag pairs)
        data = self._query_ascii_values(CMD_GET_SDATA)

        # Ensure even length
        if len(data) % 2 != 0:
            data = data[:-1]

        # Parse real and imaginary parts
        real = np.array(data[0::2])
        imag = np.array(data[1::2])

        # Convert to magnitude (dB) and phase (degrees)
        comp = real + 1j * imag
        mag_db = 20 * np.log10(np.abs(comp) + LOG_EPSILON)
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
