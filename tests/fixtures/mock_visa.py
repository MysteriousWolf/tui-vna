"""
Mock VISA resources for testing without hardware.

Provides realistic SCPI instrument simulation for comprehensive testing.
"""

import time
from typing import Any, Dict, List
from unittest.mock import MagicMock

import numpy as np
import pyvisa


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
        self.command_history: List[str] = []
        self.query_history: List[str] = []
        self.call_count: Dict[str, int] = {}

    def _track_call(self, command: str) -> None:
        """Track command calls for verification."""
        cmd_base = command.split()[0] if command else ""
        self.call_count[cmd_base] = self.call_count.get(cmd_base, 0) + 1

    def _simulate_delay(self, base_ms: float = 10.0) -> None:
        """Optionally simulate realistic instrument delays."""
        if self.simulate_delay:
            time.sleep(base_ms / 1000.0)

    def write(self, command: str) -> None:
        """
        Simulate writing a SCPI command.

        Args:
            command: SCPI command string

        Raises:
            pyvisa.VisaIOError: If resource is closed
        """
        if self._closed:
            raise pyvisa.VisaIOError(pyvisa.constants.VI_ERROR_INV_OBJECT)

        self.command_history.append(command)
        self._track_call(command)
        self._simulate_delay(5)

        # Parse and update instrument state
        cmd = command.strip().upper()

        # Frequency commands
        if ":SENS1:FREQ:STAR" in cmd or ":SENS:FREQ:STAR" in cmd:
            try:
                self._freq_start = float(command.split()[-1])
            except (ValueError, IndexError):
                pass
        elif ":SENS1:FREQ:STOP" in cmd or ":SENS:FREQ:STOP" in cmd:
            try:
                self._freq_stop = float(command.split()[-1])
            except (ValueError, IndexError):
                pass

        # Sweep points
        elif ":SENS1:SWE:POIN" in cmd or ":SENS:SWE:POIN" in cmd:
            try:
                self._sweep_points = int(command.split()[-1])
            except (ValueError, IndexError):
                pass

        # Sweep type
        elif ":SENS1:SWE:TYPE" in cmd or ":SENS:SWE:TYPE" in cmd:
            if "LIN" in cmd:
                self._sweep_type = "LIN"
            elif "LOG" in cmd:
                self._sweep_type = "LOG"

        # Data format
        elif ":FORM" in cmd:
            if "ASC" in cmd:
                self._data_format = "ASC"
            elif "REAL" in cmd:
                self._data_format = "REAL"

        # Averaging
        elif ":SENS1:AVER:STAT" in cmd or ":SENS:AVER:STAT" in cmd:
            self._averaging_enabled = any(x in cmd for x in ["ON", " 1"])
        elif ":SENS1:AVER:COUN" in cmd or ":SENS:AVER:COUN" in cmd:
            try:
                self._averaging_count = int(command.split()[-1])
            except (ValueError, IndexError):
                pass

        # Trigger/continuous mode
        elif ":INIT1:CONT" in cmd or ":INIT:CONT" in cmd:
            self._continuous_mode = any(x in cmd for x in ["ON", " 1"])
        elif ":TRIG:SOUR" in cmd:
            parts = command.split()
            if len(parts) >= 2:
                self._trigger_source = parts[-1].strip()

        # Parameter setup
        elif ":CALC1:PAR:COUN" in cmd or ":CALC:PAR:COUN" in cmd:
            try:
                self._param_count = int(command.split()[-1])
            except (ValueError, IndexError):
                pass

        # Measurement commands
        elif ":ABOR" in cmd:
            self._simulate_delay(20)
        elif cmd == ":INIT" or cmd == ":INIT1":
            self._simulate_delay(100)  # Simulate sweep time

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
            raise pyvisa.VisaIOError(pyvisa.constants.VI_ERROR_INV_OBJECT)

        self.query_history.append(command)
        self._track_call(command)
        self._simulate_delay(10)

        cmd = command.strip().upper()

        # Identification
        if cmd == "*IDN?":
            return self.idn_string

        # Operation complete
        elif cmd == "*OPC?":
            return "1"

        # Frequency queries
        elif ":SENS1:FREQ:STAR?" in cmd or ":SENS:FREQ:STAR?" in cmd:
            return str(self._freq_start)
        elif ":SENS1:FREQ:STOP?" in cmd or ":SENS:FREQ:STOP?" in cmd:
            return str(self._freq_stop)

        # Sweep points
        elif ":SENS1:SWE:POIN?" in cmd or ":SENS:SWE:POIN?" in cmd:
            return str(self._sweep_points)

        # Sweep type
        elif ":SENS1:SWE:TYPE?" in cmd or ":SENS:SWE:TYPE?" in cmd:
            return self._sweep_type

        # Data format
        elif ":FORM?" in cmd:
            return self._data_format

        # Averaging
        elif ":SENS1:AVER:STAT?" in cmd or ":SENS:AVER:STAT?" in cmd:
            return "1" if self._averaging_enabled else "0"
        elif ":SENS1:AVER:COUN?" in cmd or ":SENS:AVER:COUN?" in cmd:
            return str(self._averaging_count)

        # Trigger/continuous mode
        elif ":INIT1:CONT?" in cmd or ":INIT:CONT?" in cmd:
            return "1" if self._continuous_mode else "0"
        elif ":TRIG:SOUR?" in cmd:
            return self._trigger_source

        # Parameter count
        elif ":CALC1:PAR:COUN?" in cmd or ":CALC:PAR:COUN?" in cmd:
            return str(self._param_count)

        # Unknown command - return default
        else:
            return "0"

    def query_ascii_values(self, command: str) -> List[float]:
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
            raise pyvisa.VisaIOError(pyvisa.constants.VI_ERROR_INV_OBJECT)

        self.query_history.append(command)
        self._track_call(command)
        self._simulate_delay(50)

        cmd = command.strip().upper()

        # Frequency data
        if ":FREQ:DATA?" in cmd:
            if self._sweep_type == "LIN":
                return list(
                    np.linspace(self._freq_start, self._freq_stop, self._sweep_points)
                )
            else:  # LOG
                return list(
                    np.logspace(
                        np.log10(self._freq_start),
                        np.log10(self._freq_stop),
                        self._sweep_points,
                    )
                )

        # S-parameter data (SDATA returns real/imag pairs)
        elif ":DATA:SDAT?" in cmd or ":CALC1:DATA:SDAT?" in cmd:
            # Generate realistic S-parameter data
            t = np.linspace(0, 1, self._sweep_points)

            # Create complex S-parameter with realistic characteristics
            # Simulate different responses based on active parameter
            if self._active_param == 1:  # S11 - reflection
                mag = 0.3 * np.exp(-5 * t) + 0.1 * np.sin(10 * np.pi * t)
                phase = -180 * t + 20 * np.sin(8 * np.pi * t)
            elif self._active_param == 2:  # S21 - forward transmission
                mag = np.exp(-2 * t) * 0.9
                phase = -90 * t
            elif self._active_param == 3:  # S12 - reverse transmission
                mag = np.exp(-2.2 * t) * 0.85
                phase = -95 * t
            else:  # S22 - output reflection
                mag = 0.25 * np.exp(-4.5 * t) + 0.08 * np.sin(9 * np.pi * t)
                phase = -170 * t + 18 * np.sin(7 * np.pi * t)

            real = mag * np.cos(np.deg2rad(phase))
            imag = mag * np.sin(np.deg2rad(phase))

            # Interleave real and imaginary parts
            data = []
            for r, i in zip(real, imag):
                data.append(r)
                data.append(i)

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
        self._resources: Dict[str, MockVisaResource] = {}

    def open_resource(self, resource_name: str, **kwargs: Any) -> MockVisaResource:
        """
        Open a mock VISA resource.

        Args:
            resource_name: VISA resource address
            **kwargs: Additional arguments (ignored)

        Returns:
            MockVisaResource instance
        """
        # Create or reuse resource (but create new if closed)
        if (
            resource_name not in self._resources
            or self._resources[resource_name]._closed
        ):
            self._resources[resource_name] = MockVisaResource()

        return self._resources[resource_name]

    def list_resources(self) -> List[str]:
        """List available mock resources."""
        return list(self._resources.keys())

    def close(self) -> None:
        """Close all resources."""
        for resource in self._resources.values():
            resource.close()
        self._resources.clear()
