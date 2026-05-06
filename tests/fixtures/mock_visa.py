"""
Mock VISA resources for testing without hardware.

Provides realistic SCPI instrument simulation for comprehensive testing.
"""

import re
import time
from typing import Any

import numpy as np
import pyvisa
from pyvisa import constants as visa_constants


class MockVisaResource:
    """
    Mock pyvisa Resource that simulates a SCPI instrument.

    This mock tracks all commands and queries, simulates instrument state,
    and provides realistic responses without needing actual hardware.

    Features:
    - Command/query history tracking
    - Realistic SCPI response generation
    - Configurable instrument state
    - Error simulation capabilities
    """

    def __init__(
        self,
        idn_string: str = "HEWLETT-PACKARD,E5071B,MY12345678,A.01.02",
        simulate_delay: bool = False,
    ):
        """
        Initialize mock VISA resource.

        Args:
            idn_string: Instrument identification string
            simulate_delay: If True, add realistic delays to operations
        """
        self.idn_string = idn_string
        self.simulate_delay = simulate_delay
        self.timeout = 60000
        self._closed = False

        # Instrument state
        self._freq_start = 1e6
        self._freq_stop = 1100e6
        self._sweep_points = 601
        self._averaging_enabled = False
        self._averaging_count = 16
        self._continuous_mode = True
        self._trigger_source = "INT"
        self._param_count = 4
        self._active_param = 1
        self._sweep_type = "LIN"
        self._data_format = "ASC"

        # Command/query tracking
        self.command_history: list[str] = []
        self.query_history: list[str] = []
        self.call_count: dict[str, int] = {}

    def _track_call(self, command: str) -> None:
        """Track command calls for verification."""
        cmd_base = command.split()[0] if command else ""
        self.call_count[cmd_base] = self.call_count.get(cmd_base, 0) + 1

    def _simulate_delay(self, base_ms: float = 10.0) -> None:
        """Optionally simulate realistic instrument delays."""
        if self.simulate_delay:
            time.sleep(base_ms / 1000.0)

    def _normalize_scpi(self, command: str) -> str:
        """Normalize command prefixes so optional leading colons compare equally."""
        normalized = command.strip().upper()
        if normalized.startswith(":"):
            return normalized[1:]
        return normalized

    def _extract_last_value(self, command: str) -> str | None:
        """Return the final whitespace-delimited value from a SCPI command."""
        parts = command.split()
        if len(parts) < 2:
            return None
        return parts[-1].strip().strip("\"'")

    def _parse_selected_parameter(self, command: str) -> int | None:
        """Parse active parameter selection from SCPI commands."""
        normalized = self._normalize_scpi(command)

        indexed_match = re.search(r"CALC1:PAR(\d+):SEL", normalized)
        if indexed_match:
            return int(indexed_match.group(1))

        named_match = re.search("CALC1:PAR:SEL\\s+['\"]?(S[12][12])['\"]?", normalized)
        if named_match:
            return {"S11": 1, "S21": 2, "S12": 3, "S22": 4}[named_match.group(1)]

        return None

    def write(self, command: str) -> None:
        """
        Simulate writing a SCPI command.

        Args:
            command: SCPI command string

        Raises:
            pyvisa.VisaIOError: If resource is closed
        """
        if self._closed:
            raise pyvisa.VisaIOError(visa_constants.VI_ERROR_INV_OBJECT)

        self.command_history.append(command)
        self._track_call(command)
        self._simulate_delay(5)

        cmd = self._normalize_scpi(command)

        if "SENS1:FREQ:STAR" in cmd or "SENS:FREQ:STAR" in cmd:
            value = self._extract_last_value(command)
            if value is not None:
                try:
                    self._freq_start = float(value)
                except ValueError:
                    pass
        elif "SENS1:FREQ:STOP" in cmd or "SENS:FREQ:STOP" in cmd:
            value = self._extract_last_value(command)
            if value is not None:
                try:
                    self._freq_stop = float(value)
                except ValueError:
                    pass
        elif "SENS1:SWE:POIN" in cmd or "SENS:SWE:POIN" in cmd:
            value = self._extract_last_value(command)
            if value is not None:
                try:
                    self._sweep_points = int(value)
                except ValueError:
                    pass
        elif "SENS1:SWE:TYPE" in cmd or "SENS:SWE:TYPE" in cmd:
            if "LIN" in cmd:
                self._sweep_type = "LIN"
            elif "LOG" in cmd:
                self._sweep_type = "LOG"
        elif cmd.startswith("FORM"):
            if "ASC" in cmd:
                self._data_format = "ASC"
            elif "REAL" in cmd:
                self._data_format = "REAL"
        elif "SENS1:AVER:STAT" in cmd or "SENS:AVER:STAT" in cmd:
            self._averaging_enabled = any(token in cmd for token in ["ON", " 1"])
        elif "SENS1:AVER:COUN" in cmd or "SENS:AVER:COUN" in cmd:
            value = self._extract_last_value(command)
            if value is not None:
                try:
                    self._averaging_count = int(value)
                except ValueError:
                    pass
        elif "INIT1:CONT" in cmd or "INIT:CONT" in cmd:
            self._continuous_mode = any(token in cmd for token in ["ON", " 1"])
        elif "TRIG:SOUR" in cmd:
            value = self._extract_last_value(command)
            if value is not None:
                self._trigger_source = value.upper()
        elif "CALC1:PAR:COUN" in cmd or "CALC:PAR:COUN" in cmd:
            value = self._extract_last_value(command)
            if value is not None:
                try:
                    self._param_count = int(value)
                except ValueError:
                    pass
        else:
            selected_param = self._parse_selected_parameter(command)
            if selected_param is not None:
                self._active_param = selected_param

        if "ABOR" in cmd:
            self._simulate_delay(20)
        elif cmd in {"INIT", "INIT1"}:
            self._simulate_delay(100)

    def query(self, command: str) -> str:
        """
        Simulate querying a SCPI command.

        Args:
            command: SCPI query string

        Returns:
            Simulated instrument response

        Raises:
            pyvisa.VisaIOError: If resource is closed
        """
        if self._closed:
            raise pyvisa.VisaIOError(visa_constants.VI_ERROR_INV_OBJECT)

        self.query_history.append(command)
        self._track_call(command)
        self._simulate_delay(10)

        cmd = self._normalize_scpi(command)

        if cmd == "*IDN?":
            return self.idn_string
        if cmd == "*OPC?":
            return "1"
        if "SENS1:FREQ:STAR?" in cmd or "SENS:FREQ:STAR?" in cmd:
            return str(self._freq_start)
        if "SENS1:FREQ:STOP?" in cmd or "SENS:FREQ:STOP?" in cmd:
            return str(self._freq_stop)
        if "SENS1:SWE:POIN?" in cmd or "SENS:SWE:POIN?" in cmd:
            return str(self._sweep_points)
        if "SENS1:SWE:TYPE?" in cmd or "SENS:SWE:TYPE?" in cmd:
            return self._sweep_type
        if cmd == "FORM?":
            return self._data_format
        if "SENS1:AVER:STAT?" in cmd or "SENS:AVER:STAT?" in cmd:
            return "1" if self._averaging_enabled else "0"
        if "SENS1:AVER:COUN?" in cmd or "SENS:AVER:COUN?" in cmd:
            return str(self._averaging_count)
        if "INIT1:CONT?" in cmd or "INIT:CONT?" in cmd:
            return "1" if self._continuous_mode else "0"
        if "TRIG:SOUR?" in cmd:
            return self._trigger_source
        if "CALC1:PAR:COUN?" in cmd or "CALC:PAR:COUN?" in cmd:
            return str(self._param_count)
        return "0"

    def query_ascii_values(self, command: str) -> list[float]:
        """
        Simulate querying ASCII values (arrays).

        Args:
            command: SCPI query string

        Returns:
            List of float values

        Raises:
            pyvisa.VisaIOError: If resource is closed
        """
        if self._closed:
            raise pyvisa.VisaIOError(visa_constants.VI_ERROR_INV_OBJECT)

        self.query_history.append(command)
        self._track_call(command)
        self._simulate_delay(50)

        cmd = self._normalize_scpi(command)

        if "FREQ:DATA?" in cmd:
            if self._sweep_type == "LIN":
                return list(
                    np.linspace(self._freq_start, self._freq_stop, self._sweep_points)
                )
            return list(
                np.logspace(
                    np.log10(self._freq_start),
                    np.log10(self._freq_stop),
                    self._sweep_points,
                )
            )

        if "DATA:SDAT?" in cmd or "CALC1:DATA:SDAT?" in cmd:
            t = np.linspace(0, 1, self._sweep_points)

            if self._active_param == 1:
                mag = 0.3 * np.exp(-5 * t) + 0.1 * np.sin(10 * np.pi * t)
                phase = -180 * t + 20 * np.sin(8 * np.pi * t)
            elif self._active_param == 2:
                mag = np.exp(-2 * t) * 0.9
                phase = -90 * t
            elif self._active_param == 3:
                mag = np.exp(-2.2 * t) * 0.85
                phase = -95 * t
            else:
                mag = 0.25 * np.exp(-4.5 * t) + 0.08 * np.sin(9 * np.pi * t)
                phase = -170 * t + 18 * np.sin(7 * np.pi * t)

            real = mag * np.cos(np.deg2rad(phase))
            imag = mag * np.sin(np.deg2rad(phase))

            data: list[float] = []
            for real_value, imag_value in zip(real, imag):
                data.append(real_value)
                data.append(imag_value)

            return data

        return []

    def close(self) -> None:
        """Close the resource."""
        self._closed = True

    def reset_history(self) -> None:
        """Reset command/query history for fresh test."""
        self.command_history.clear()
        self.query_history.clear()
        self.call_count.clear()


class MockResourceManager:
    """
    Mock pyvisa ResourceManager.

    Creates and manages mock VISA resources for testing.
    """

    def __init__(self, backend: str = "@py"):
        """
        Initialize mock resource manager.

        Args:
            backend: VISA backend string (ignored in mock)
        """
        self.backend = backend
        self._resources: dict[str, MockVisaResource] = {}

    def open_resource(self, resource_name: str, **kwargs: Any) -> MockVisaResource:
        """
        Open a mock VISA resource.

        Args:
            resource_name: VISA resource address
            **kwargs: Additional arguments (ignored)

        Returns:
            MockVisaResource instance
        """
        if (
            resource_name not in self._resources
            or self._resources[resource_name]._closed
        ):
            self._resources[resource_name] = MockVisaResource()

        return self._resources[resource_name]

    def list_resources(self) -> list[str]:
        """List available mock resources."""
        return list(self._resources.keys())

    def close(self) -> None:
        """Close all resources."""
        for resource in self._resources.values():
            resource.close()
        self._resources.clear()
