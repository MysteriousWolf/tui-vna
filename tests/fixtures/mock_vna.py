"""
Mock VNA drivers for testing without hardware.

Provides complete VNA implementations that can be used as drop-in replacements
for real drivers in tests.
"""

import numpy as np

from src.tina.drivers.base import VNABase, VNAConfig
from tests.fixtures.mock_visa import MockVisaResource


class MockVNA(VNABase):
    """
    Generic mock VNA for testing.

    Implements all VNABase methods with realistic behavior but no hardware.
    """

    driver_name = "Mock VNA"

    @staticmethod
    def idn_matcher(idn_string: str) -> bool:
        """Match any IDN string containing 'MOCK'."""
        return "mock" in idn_string.lower()

    def __init__(self, config: VNAConfig | None = None):
        super().__init__(config)
        self.inst: MockVisaResource | None = None
        self._connection_attempts = 0

    def connect(self, progress_callback=None) -> bool:
        """Simulate connection to mock VNA."""
        self._connection_attempts += 1

        if progress_callback:
            progress_callback("Connecting to mock VNA...", 25)

        # Create mock VISA resource
        self.inst = MockVisaResource(idn_string="MOCK,VNA1000,SERIAL123,1.0.0")

        if progress_callback:
            progress_callback("Reading IDN...", 75)

        self._idn = self.inst.query("*IDN?")
        self._connected = True

        if progress_callback:
            progress_callback("Connected", 100)

        return True

    def disconnect(self) -> None:
        """Simulate disconnection."""
        if self.inst:
            self.inst.close()
            self.inst = None
        self._connected = False
        self._idn = ""

    def configure_frequency(self) -> None:
        """Configure frequency range."""
        if not self._connected or not self.inst:
            raise RuntimeError("Not connected to VNA")

        if self.config.set_freq_range:
            self.inst.write(f":SENS:FREQ:STAR {self.config.start_freq_hz}")
            self.inst.write(f":SENS:FREQ:STOP {self.config.stop_freq_hz}")

    def configure_measurements(self) -> None:
        """Configure measurement settings."""
        if not self._connected or not self.inst:
            raise RuntimeError("Not connected to VNA")

        self.inst.write(":FORM:DATA ASC")
        self.inst.write(":SENS:SWE:TYPE LIN")

        if self.config.set_sweep_points:
            self.inst.write(f":SENS:SWE:POIN {self.config.sweep_points}")

        if self.config.enable_averaging:
            self.inst.write(":SENS:AVER:STAT ON")
        else:
            self.inst.write(":SENS:AVER:STAT OFF")

        if self.config.set_averaging_count:
            self.inst.write(f":SENS:AVER:COUN {self.config.averaging_count}")

    def setup_s_parameters(self) -> None:
        """Setup S-parameter measurements."""
        if not self._connected or not self.inst:
            raise RuntimeError("Not connected to VNA")

        self.inst.write(":CALC:PAR:COUN 4")
        for idx, param in enumerate(["S11", "S21", "S12", "S22"], start=1):
            self.inst.write(f":CALC:PAR{idx}:DEF {param}")

    def trigger_sweep(self) -> None:
        """Trigger a sweep."""
        if not self._connected or not self.inst:
            raise RuntimeError("Not connected to VNA")

        self.inst.write(":ABOR")
        self.inst.write(":INIT:CONT OFF")
        self.inst.write(":TRIG:SOUR BUS")
        self.inst.write(":INIT")
        self.inst.query("*OPC?")

    def get_frequency_axis(self) -> np.ndarray:
        """Get frequency axis."""
        if not self._connected or not self.inst:
            raise RuntimeError("Not connected to VNA")

        freqs = self.inst.query_ascii_values(":SENS:FREQ:DATA?")
        return np.array(freqs)

    def get_sparam_data(self, param_num: int) -> tuple[np.ndarray, np.ndarray]:
        """Get S-parameter data."""
        if not self._connected or not self.inst:
            raise RuntimeError("Not connected to VNA")

        # Select parameter
        self.inst._active_param = param_num

        data = self.inst.query_ascii_values(":CALC:DATA:SDAT?")

        # Parse real/imag pairs
        real = np.array(data[0::2])
        imag = np.array(data[1::2])

        # Convert to magnitude (dB) and phase (degrees)
        comp = real + 1j * imag
        mag_db = 20 * np.log10(np.abs(comp) + 1e-12)
        phase_deg = np.angle(comp, deg=True)

        return mag_db, phase_deg

    def get_all_sparameters(self) -> dict[str, tuple[np.ndarray, np.ndarray]]:
        """Get all S-parameters."""
        sparams = {}
        for idx, name in enumerate(["S11", "S21", "S12", "S22"], start=1):
            sparams[name] = self.get_sparam_data(idx)
        return sparams

    def get_current_parameters(self) -> dict[str, any]:
        """Get current VNA settings."""
        if not self._connected or not self.inst:
            raise RuntimeError("Not connected to VNA")

        return {
            "start_freq_hz": float(self.inst.query(":SENS:FREQ:STAR?")),
            "stop_freq_hz": float(self.inst.query(":SENS:FREQ:STOP?")),
            "sweep_points": int(self.inst.query(":SENS:SWE:POIN?")),
            "averaging_enabled": self.inst.query(":SENS:AVER:STAT?") == "1",
            "averaging_count": int(self.inst.query(":SENS:AVER:COUN?")),
        }

    def save_trigger_state(self) -> tuple[str, bool]:
        """Save trigger state."""
        if not self._connected or not self.inst:
            raise RuntimeError("Not connected to VNA")

        trigger = self.inst.query(":TRIG:SOUR?")
        continuous = self.inst.query(":INIT:CONT?") == "1"
        return (trigger, continuous)

    def restore_trigger_state(self, state: tuple[str, bool]) -> None:
        """Restore trigger state."""
        if not self._connected or not self.inst:
            raise RuntimeError("Not connected to VNA")

        trigger, continuous = state
        self.inst.write(f":TRIG:SOUR {trigger}")
        self.inst.write(f":INIT:CONT {'ON' if continuous else 'OFF'}")


class MockE5071B(MockVNA):
    """
    Mock HP/Agilent/Keysight E5071B VNA.

    Mimics the behavior of the real HP E5071B driver but without hardware.
    Uses HP-specific SCPI command format.
    """

    driver_name = "Mock HP E5071B"

    @staticmethod
    def idn_matcher(idn_string: str) -> bool:
        """Match HP E5071 series IDN strings."""
        idn_lower = idn_string.lower()
        return any(
            pattern in idn_lower for pattern in ["e5071", "e5071a", "e5071b", "e5071c"]
        )

    def __init__(self, config: VNAConfig | None = None):
        super().__init__(config)

    def connect(self, progress_callback=None) -> bool:
        """Simulate connection to mock E5071B."""
        self._connection_attempts += 1

        if progress_callback:
            progress_callback("Checking host...", 10)
            progress_callback("Initializing VISA...", 25)
            progress_callback("Opening connection...", 50)

        # Create mock VISA resource with HP E5071B IDN
        self.inst = MockVisaResource(
            idn_string="HEWLETT-PACKARD,E5071B,MY12345678,A.01.02"
        )

        if progress_callback:
            progress_callback("Verifying connection...", 80)

        self._idn = self.inst.query("*IDN?")
        self._connected = True

        if progress_callback:
            progress_callback("Connected", 100)

        return True

    def configure_frequency(self) -> None:
        """Configure frequency with HP-specific commands."""
        if not self._connected or not self.inst:
            raise RuntimeError("Not connected to VNA")

        if self.config.set_freq_range:
            self.inst.write(f":SENS1:FREQ:STAR {self.config.start_freq_hz}")
            self.inst.write(f":SENS1:FREQ:STOP {self.config.stop_freq_hz}")

    def configure_measurements(self) -> None:
        """Configure measurements with HP-specific commands."""
        if not self._connected or not self.inst:
            raise RuntimeError("Not connected to VNA")

        self.inst.write(":FORM:DATA ASC")
        self.inst.write(":SENS1:SWE:TYPE LIN")

        if self.config.set_sweep_points:
            self.inst.write(f":SENS1:SWE:POIN {self.config.sweep_points}")

        if self.config.enable_averaging:
            self.inst.write(":SENS1:AVER:STAT ON")
        else:
            self.inst.write(":SENS1:AVER:STAT OFF")

        if self.config.set_averaging_count:
            self.inst.write(f":SENS1:AVER:COUN {self.config.averaging_count}")

    def setup_s_parameters(self) -> None:
        """Setup S-parameters with HP-specific commands."""
        if not self._connected or not self.inst:
            raise RuntimeError("Not connected to VNA")

        self.inst.write(":CALC1:PAR:COUN 4")
        for idx, param in enumerate(["S11", "S21", "S12", "S22"], start=1):
            self.inst.write(f":CALC1:PAR{idx}:DEF {param}")
            self.inst.write(f":CALC1:PAR{idx}:SEL")

    def trigger_sweep(self) -> None:
        """Trigger sweep with HP-specific commands."""
        if not self._connected or not self.inst:
            raise RuntimeError("Not connected to VNA")

        self.inst.write(":ABOR")
        self.inst.write(":INIT1:CONT OFF")
        self.inst.write(":TRIG:SOUR BUS")
        self.inst.write(":INIT")
        self.inst.query("*OPC?")

    def get_frequency_axis(self) -> np.ndarray:
        """Get frequency axis with HP-specific commands."""
        if not self._connected or not self.inst:
            raise RuntimeError("Not connected to VNA")

        freqs = self.inst.query_ascii_values(":SENS1:FREQ:DATA?")
        return np.array(freqs)

    def get_sparam_data(self, param_num: int) -> tuple[np.ndarray, np.ndarray]:
        """Get S-parameter data with HP-specific commands."""
        if not self._connected or not self.inst:
            raise RuntimeError("Not connected to VNA")

        # Select parameter
        self.inst.write(f":CALC1:PAR{param_num}:SEL")
        self.inst._active_param = param_num

        data = self.inst.query_ascii_values(":CALC1:DATA:SDAT?")

        # Parse real/imag pairs
        real = np.array(data[0::2])
        imag = np.array(data[1::2])

        # Convert to magnitude (dB) and phase (degrees)
        comp = real + 1j * imag
        mag_db = 20 * np.log10(np.abs(comp) + 1e-12)
        phase_deg = np.angle(comp, deg=True)

        return mag_db, phase_deg

    def get_current_parameters(self) -> dict[str, any]:
        """Get current settings with HP-specific commands."""
        if not self._connected or not self.inst:
            raise RuntimeError("Not connected to VNA")

        return {
            "start_freq_hz": float(self.inst.query(":SENS1:FREQ:STAR?")),
            "stop_freq_hz": float(self.inst.query(":SENS1:FREQ:STOP?")),
            "sweep_points": int(self.inst.query(":SENS1:SWE:POIN?")),
            "averaging_enabled": self.inst.query(":SENS1:AVER:STAT?") == "1",
            "averaging_count": int(self.inst.query(":SENS1:AVER:COUN?")),
        }

    def save_trigger_state(self) -> tuple[str, bool]:
        """Save trigger state with HP-specific commands."""
        if not self._connected or not self.inst:
            raise RuntimeError("Not connected to VNA")

        trigger = self.inst.query(":TRIG:SOUR?")
        continuous = self.inst.query(":INIT1:CONT?") == "1"
        return (trigger, continuous)

    def restore_trigger_state(self, state: tuple[str, bool]) -> None:
        """Restore trigger state with HP-specific commands."""
        if not self._connected or not self.inst:
            raise RuntimeError("Not connected to VNA")

        trigger, continuous = state
        self.inst.write(f":TRIG:SOUR {trigger}")
        self.inst.write(f":INIT1:CONT {'ON' if continuous else 'OFF'}")
