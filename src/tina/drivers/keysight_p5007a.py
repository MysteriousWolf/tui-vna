"""Keysight P5007A Vector Network Analyzer driver.

Implements the VNABase interface for the Keysight P5007A 2-port PNA-family VNA.
"""

from __future__ import annotations

import socket
import time
from typing import Any, Protocol, cast

import numpy as np
import pyvisa

from ..config.constants import (
    COMMAND_TIMEOUT_MS,
    LOG_EPSILON,
    OPERATION_TIMEOUT_SEC,
    SCPI_RAW_PORT,
    SOCKET_TIMEOUT_SEC,
    SWEEP_TIMEOUT_SEC,
    VXI11_PORTMAPPER_PORT,
)
from .base import VNABase, VNAConfig
from .scpi_commands import CMD_BUS_TRIGGER


class _VisaResourceProtocol(Protocol):
    """Subset of VISA resource methods used by the Keysight driver."""

    timeout: int

    def close(self) -> None:
        """Close the instrument resource."""
        ...

    def write(self, command: str) -> None:
        """Send a SCPI command."""
        ...

    def query(self, command: str) -> str:
        """Send a SCPI query and return the response."""
        ...

    def query_ascii_values(self, command: str) -> list[float]:
        """Query a list of ASCII float values."""
        ...


class KeysightP5007A(VNABase):
    """Keysight P5007A VNA controller."""

    driver_name = "Keysight P5007A"
    _S_PARAMETER_NAMES = ("S11", "S21", "S12", "S22")

    @staticmethod
    def idn_matcher(idn_string: str) -> bool:
        """Return True when the IDN string identifies a P5007A."""
        return "p5007a" in idn_string.lower()

    def __init__(self, config: VNAConfig | None = None):
        """Initialize the Keysight P5007A driver."""
        super().__init__(config)
        self.inst: pyvisa.resources.Resource | None = None
        self._measurement_names = {
            1: "CH1_S11",
            2: "CH1_S21",
            3: "CH1_S12",
            4: "CH1_S22",
        }

    def _check_host_reachable(
        self, host: str, timeout: float = SOCKET_TIMEOUT_SEC
    ) -> bool:
        """Check whether the instrument host responds on a SCPI-capable port.

        Probes VXI11_PORTMAPPER_PORT and SCPI_RAW_PORT using a TCP connect.
        A successful connect only confirms OS-level reachability — it does NOT
        guarantee the peer implements VXI-11 or SCPI protocols. Callers must
        perform a proper protocol handshake (e.g. *IDN?) after this preflight.
        """
        for port in (VXI11_PORTMAPPER_PORT, SCPI_RAW_PORT):
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                    sock.settimeout(timeout)
                    if sock.connect_ex((host, port)) == 0:
                        return True
            except OSError:
                continue
        return False

    def connect(self, progress_callback=None) -> bool:
        """Connect to the Keysight P5007A over VISA."""

        def report(message: str, progress_pct: float) -> None:
            if progress_callback is not None:
                progress_callback(message, progress_pct)

        address = self.config.build_address()

        report("Checking host...", 10)
        if not self._check_host_reachable(self.config.host):
            self._connected = False
            raise ConnectionError(f"Host {self.config.host} not reachable")

        report("Initializing VISA...", 25)
        try:
            resource_manager = pyvisa.ResourceManager("@py")
        except Exception as exc:
            import logging
            logging.getLogger(__name__).debug(
                "pyvisa-py backend unavailable, falling back to default: %s", exc
            )
            resource_manager = pyvisa.ResourceManager()

        report("Opening connection...", 50)
        try:
            self.inst = resource_manager.open_resource(address)
            self.inst.timeout = COMMAND_TIMEOUT_MS
            self._connected = True

            report("Verifying connection...", 80)
            self._idn = self._query("*IDN?").strip()
            if not self.idn_matcher(self._idn):
                raise ConnectionError(
                    f"Expected {self.driver_name}, got {self._idn!r}"
                )

            report("Connected", 100)
            return True
        except Exception:
            self._cleanup_failed_connection()
            raise

    def _cleanup_failed_connection(self) -> None:
        """Close any partially-open resource after a failed connection."""
        if self.inst is not None:
            try:
                self.inst.close()
            except Exception:
                pass
            self.inst = None
        self._connected = False

    def disconnect(self) -> None:
        """Disconnect from the Keysight P5007A."""
        if self.inst is not None:
            try:
                self.inst.close()
            except Exception:
                pass
            self.inst = None
        self._connected = False
        self._idn = ""

    def _ensure_connected(self) -> None:
        """Raise when an operation is attempted without an active connection."""
        if not self._connected or self.inst is None:
            raise RuntimeError("Not connected to VNA")

    def _send_command(self, command: str) -> None:
        """Send a SCPI command to the instrument."""
        self._ensure_connected()
        cast(_VisaResourceProtocol, self.inst).write(command)

    def _query(self, command: str) -> str:
        """Send a SCPI query and return the raw response."""
        self._ensure_connected()
        return cast(_VisaResourceProtocol, self.inst).query(command)

    def _query_ascii_values(self, command: str) -> list[float]:
        """Query a comma-separated numeric response as floats."""
        self._ensure_connected()
        return cast(_VisaResourceProtocol, self.inst).query_ascii_values(command)

    def _query_first_successful(self, *commands: str) -> str:
        """Try several SCPI queries and return the first successful response."""
        last_error: Exception | None = None
        for command in commands:
            try:
                return self._query(command).strip()
            except Exception as exc:
                last_error = exc
        if last_error is not None:
            attempted = ", ".join(repr(c) for c in commands)
            raise RuntimeError(
                f"All SCPI alternates failed ({attempted})"
            ) from last_error
        raise RuntimeError("No SCPI commands were provided")

    def _parameter_name(self, param_num: int) -> str:
        """Return the instrument measurement name for a parameter index."""
        if param_num not in self._measurement_names:
            raise ValueError(f"Unsupported S-parameter index: {param_num}")
        return self._measurement_names[param_num]

    def _select_parameter(self, param_num: int) -> None:
        """Select a previously-defined measurement trace by name."""
        self._send_command(f"CALC1:PAR:SEL '{self._parameter_name(param_num)}'")

    def get_current_parameters(self) -> dict[str, Any]:
        """Read the currently active sweep and averaging settings."""
        params: dict[str, Any] = {}

        try:
            params["start_freq_hz"] = float(self._query("SENS1:FREQ:STAR?").strip())
        except Exception:
            params["start_freq_hz"] = None

        try:
            params["stop_freq_hz"] = float(self._query("SENS1:FREQ:STOP?").strip())
        except Exception:
            params["stop_freq_hz"] = None

        try:
            params["sweep_points"] = int(self._query("SENS1:SWE:POIN?").strip())
        except Exception:
            params["sweep_points"] = None

        try:
            averaging_state = self._query("SENS1:AVER:STAT?").strip().upper()
            params["averaging_enabled"] = averaging_state in {"1", "ON"}
        except Exception:
            params["averaging_enabled"] = None

        try:
            params["averaging_count"] = int(self._query("SENS1:AVER:COUN?").strip())
        except Exception:
            params["averaging_count"] = None

        return params

    def get_status(self) -> dict[str, Any]:
        """Query the live instrument status used by the status bar."""
        status: dict[str, Any] = {
            "cal_enabled": None,
            "cal_type": None,
            "smoothing_enabled": None,
            "smoothing_aperture": None,
            "if_bandwidth_hz": None,
            "port_power_dbm": None,
            "trigger_source": None,
        }

        try:
            raw = self._query_first_successful("SENS1:CORR:STAT?").upper()
            status["cal_enabled"] = raw in {"1", "ON"}
        except Exception:
            pass

        try:
            raw = self._query_first_successful(
                "SENS1:CORR:CSET:TYPE?",
                "SENS1:CORR:TYPE?",
            )
            status["cal_type"] = raw.split(",")[0].strip()
        except Exception:
            pass

        try:
            raw = self._query_first_successful("CALC1:SMO:STAT?").upper()
            status["smoothing_enabled"] = raw in {"1", "ON"}
        except Exception:
            pass

        try:
            status["smoothing_aperture"] = float(
                self._query_first_successful("CALC1:SMO:APER?")
            )
        except Exception:
            pass

        try:
            status["if_bandwidth_hz"] = float(
                self._query_first_successful("SENS1:BWID?")
            )
        except Exception:
            pass

        try:
            status["port_power_dbm"] = float(
                self._query_first_successful("SOUR1:POW1?", "SOUR1:POW?")
            )
        except Exception:
            pass

        try:
            status["trigger_source"] = self._query_first_successful("TRIG:SOUR?")
        except Exception:
            pass

        return status

    def configure_frequency(self) -> None:
        """Apply the configured start and stop frequencies when requested."""
        if not self.config.set_freq_range:
            return

        if self.config.stop_freq_hz <= self.config.start_freq_hz:
            raise ValueError("Stop frequency must be greater than start frequency")

        self._send_command(f"SENS1:FREQ:STAR {self.config.start_freq_hz}")
        self._send_command(f"SENS1:FREQ:STOP {self.config.stop_freq_hz}")
        time.sleep(0.3)

    def configure_measurements(self) -> None:
        """Configure sweep format, points, and averaging for channel 1."""
        self._send_command("FORM:DATA ASCII")
        self._send_command("SENS1:SWE:TYPE LIN")

        if self.config.set_sweep_points:
            self._send_command(f"SENS1:SWE:POIN {self.config.sweep_points}")

        self._send_command(
            f"SENS1:AVER:STAT {'ON' if self.config.enable_averaging else 'OFF'}"
        )

        if self.config.set_averaging_count:
            self._send_command(f"SENS1:AVER:COUN {self.config.averaging_count}")

        time.sleep(0.3)

    def setup_s_parameters(self) -> None:
        """Create named S11/S21/S12/S22 measurements on channel 1."""
        self._send_command("DISP:WIND1:STAT ON")
        self._send_command("CALC1:PAR:DEL:ALL")
        time.sleep(0.2)

        for index, sparam in enumerate(self._S_PARAMETER_NAMES, start=1):
            meas_name = self._parameter_name(index)
            self._send_command(f"CALC1:PAR:EXT '{meas_name}',{sparam}")
            self._send_command(f"DISP:WIND1:TRAC{index}:FEED '{meas_name}'")
            time.sleep(0.1)

        self._select_parameter(1)
        time.sleep(0.1)

    def _wait_for_operation_complete(
        self, timeout_seconds: float = OPERATION_TIMEOUT_SEC
    ) -> None:
        """Wait for the current operation to complete using *OPC?.

        Sets the VISA timeout to exactly timeout_seconds so the blocking *OPC?
        query respects the advertised deadline without overrunning it.
        """
        self._ensure_connected()
        resource = cast(_VisaResourceProtocol, self.inst)
        original_timeout = resource.timeout
        resource.timeout = int(timeout_seconds * 1000)
        try:
            try:
                if self._query("*OPC?").strip() in {"1", "+1"}:
                    return
            except pyvisa.errors.VisaIOError as exc:
                raise TimeoutError(
                    f"Operation did not complete within {timeout_seconds} seconds"
                ) from exc
        finally:
            resource.timeout = original_timeout

    def get_trigger_source(self) -> str:
        """Return the current trigger source."""
        return self._query("TRIG:SOUR?").strip()

    def set_trigger_source(self, source: str) -> None:
        """Set the instrument trigger source."""
        self._send_command(f"TRIG:SOUR {source.upper()}")
        time.sleep(0.1)

    def save_trigger_state(self) -> tuple[str, bool]:
        """Capture the current trigger source and continuous sweep state."""
        trigger_source = self.get_trigger_source()
        continuous_raw = self._query("INIT1:CONT?").strip().upper()
        return trigger_source, continuous_raw in {"1", "ON"}

    def restore_trigger_state(self, state: tuple[str, bool]) -> None:
        """Restore a previously-saved trigger source and continuous mode."""
        trigger_source, continuous_mode = state
        self._send_command(f"TRIG:SOUR {trigger_source}")
        self._send_command(f"INIT1:CONT {'ON' if continuous_mode else 'OFF'}")
        time.sleep(0.1)

    def trigger_sweep(self) -> None:
        """Trigger a single sweep on channel 1 and wait for completion.

        Mutates trigger state (sets INIT1:CONT OFF, TRIG:SOUR BUS). Callers must
        bracket this with save_trigger_state() / restore_trigger_state().
        """
        self._send_command("ABOR")
        time.sleep(0.1)

        if self.config.enable_averaging:
            try:
                self._send_command("SENS1:AVER:CLE")
                time.sleep(0.1)
            except Exception:
                pass

        self._send_command("INIT1:CONT OFF")
        self._send_command("TRIG:SOUR BUS")
        time.sleep(0.1)

        self._send_command("INIT1:IMM")
        self._send_command(CMD_BUS_TRIGGER)
        self._wait_for_operation_complete(timeout_seconds=SWEEP_TIMEOUT_SEC)

    def get_frequency_axis(self) -> np.ndarray:
        """Build the sweep frequency axis from the current sweep settings."""
        start_freq_hz = float(self._query("SENS1:FREQ:STAR?").strip())
        stop_freq_hz = float(self._query("SENS1:FREQ:STOP?").strip())
        sweep_points = int(self._query("SENS1:SWE:POIN?").strip())

        if sweep_points <= 0:
            raise ValueError("Sweep point count must be positive")
        if sweep_points == 1:
            return np.array([start_freq_hz], dtype=float)

        return np.linspace(start_freq_hz, stop_freq_hz, sweep_points, dtype=float)

    def get_sparam_data(self, param_num: int) -> tuple[np.ndarray, np.ndarray]:
        """Read complex S-parameter data and convert it to mag/phase arrays."""
        self._select_parameter(param_num)
        time.sleep(0.05)

        data = self._query_ascii_values("CALC1:DATA:SDAT?")
        if len(data) % 2 != 0:
            raise ValueError(
                "CALC1:DATA:SDAT? returned an odd number of values; expected "
                "real/imaginary pairs"
            )

        real = np.array(data[0::2], dtype=float)
        imag = np.array(data[1::2], dtype=float)
        complex_data = real + 1j * imag

        magnitude_db = 20 * np.log10(np.abs(complex_data) + LOG_EPSILON)
        phase_deg = np.angle(complex_data, deg=True)

        return magnitude_db, phase_deg

    def get_all_sparameters(self) -> dict[str, tuple[np.ndarray, np.ndarray]]:
        """Read all four 2-port S-parameters from the current measurement setup."""
        return {
            sparam: self.get_sparam_data(index)
            for index, sparam in enumerate(self._S_PARAMETER_NAMES, start=1)
        }
