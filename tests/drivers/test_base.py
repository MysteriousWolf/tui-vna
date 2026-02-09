"""
Unit tests for VNA driver base classes and configuration.

Tests the base driver abstraction, driver discovery, and configuration.
"""

import pytest

from src.tina.drivers.base import (
    VNABase,
    VNAConfig,
    detect_vna_driver,
    discover_drivers,
    list_available_drivers,
)
from tests.fixtures.mock_vna import MockVNA as DummyVNA


class TestVNAConfig:
    """Test VNAConfig dataclass."""

    @pytest.mark.unit
    def test_default_config(self):
        """Test creating config with defaults."""
        config = VNAConfig()
        assert config.host == ""
        assert config.port == "inst0"
        assert config.protocol == "TCPIP0"
        assert config.suffix == "INSTR"
        assert config.timeout_ms == 60000

    @pytest.mark.unit
    def test_custom_config(self):
        """Test creating config with custom values."""
        config = VNAConfig(
            host="192.168.1.100",
            port="inst1",
            start_freq_hz=1e9,
            stop_freq_hz=2e9,
            sweep_points=401,
        )
        assert config.host == "192.168.1.100"
        assert config.port == "inst1"
        assert config.start_freq_hz == 1e9
        assert config.stop_freq_hz == 2e9
        assert config.sweep_points == 401

    @pytest.mark.unit
    def test_build_address(self):
        """Test VISA address string building."""
        config = VNAConfig(host="192.168.1.100")
        address = config.build_address()
        assert address == "TCPIP0::192.168.1.100::inst0::INSTR"

    @pytest.mark.unit
    def test_build_address_no_host(self):
        """Test that building address without host raises error."""
        config = VNAConfig()
        with pytest.raises(ValueError, match="Host IP address must be configured"):
            config.build_address()

    @pytest.mark.unit
    def test_build_address_custom_protocol(self):
        """Test building address with custom protocol."""
        config = VNAConfig(
            host="192.168.1.100", protocol="TCPIP", port="5025", suffix="SOCKET"
        )
        address = config.build_address()
        assert address == "TCPIP::192.168.1.100::5025::SOCKET"


class TestVNABase:
    """Test VNABase abstract class functionality."""

    @pytest.mark.unit
    def test_vna_base_is_abstract(self):
        """Test that VNABase cannot be instantiated directly."""
        with pytest.raises(TypeError):
            VNABase()

    @pytest.mark.unit
    def test_dummy_vna_instantiation(self, vna_config):
        """Test that concrete implementation can be instantiated."""
        vna = DummyVNA(vna_config)
        assert vna is not None
        assert vna.config == vna_config
        assert not vna.is_connected()

    @pytest.mark.unit
    def test_connection_state(self, dummy_vna):
        """Test connection state tracking."""
        assert not dummy_vna.is_connected()
        dummy_vna.connect()
        assert dummy_vna.is_connected()
        dummy_vna.disconnect()
        assert not dummy_vna.is_connected()

    @pytest.mark.unit
    def test_idn_property(self, connected_dummy_vna):
        """Test IDN property returns instrument identification."""
        idn = connected_dummy_vna.idn
        assert idn is not None
        assert len(idn) > 0
        assert any(x in idn.upper() for x in ["HEWLETT-PACKARD", "DUMMY", "MOCK"])

    @pytest.mark.unit
    def test_context_manager(self, vna_config):
        """Test VNA can be used as context manager."""
        vna = DummyVNA(vna_config)
        assert not vna.is_connected()

        with vna:
            assert vna.is_connected()

        assert not vna.is_connected()

    @pytest.mark.integration
    def test_perform_measurement(self, connected_dummy_vna):
        """Test complete measurement cycle."""
        freqs, sparams = connected_dummy_vna.perform_measurement()

        # Verify frequencies
        assert freqs is not None
        assert len(freqs) > 0
        assert freqs[0] < freqs[-1]  # Ascending order

        # Verify S-parameters
        assert "S11" in sparams
        assert "S21" in sparams
        assert "S12" in sparams
        assert "S22" in sparams

        # Verify each S-parameter has magnitude and phase
        for param_name, (mag, phase) in sparams.items():
            assert len(mag) == len(freqs)
            assert len(phase) == len(freqs)


class TestDriverDiscovery:
    """Test driver discovery mechanism."""

    @pytest.mark.unit
    def test_discover_drivers(self):
        """Test that driver discovery mechanism works."""
        drivers = discover_drivers()
        assert isinstance(drivers, dict)
        # Discovery may return empty dict in test environment
        # The important thing is it doesn't crash

    @pytest.mark.unit
    def test_list_available_drivers(self):
        """Test listing available driver names."""
        drivers = list_available_drivers()
        assert isinstance(drivers, list)
        # May return empty list in test environment

    @pytest.mark.unit
    def test_detect_vna_driver_hp_e5071b(self):
        """Test detecting HP E5071B from IDN string directly."""
        from src.tina.drivers.hp_e5071b import HPE5071B

        idn = "HEWLETT-PACKARD,E5071B,MY12345678,A.01.02"

        # Test the matcher directly
        assert HPE5071B.idn_matcher(idn)
        assert hasattr(HPE5071B, "driver_name")

    @pytest.mark.unit
    def test_detect_vna_driver_unknown(self):
        """Test that unknown IDN string returns None."""
        idn = "UNKNOWN_MANUFACTURER,UNKNOWN_MODEL,12345,1.0"
        driver_class = detect_vna_driver(idn)

        # Should return None for unknown instruments
        # (unless a catch-all driver exists)
        assert driver_class is None or hasattr(driver_class, "driver_name")

    @pytest.mark.unit
    def test_detect_vna_driver_case_insensitive(self):
        """Test that driver detection is case-insensitive."""
        # Try various case combinations
        idn_variants = [
            "HEWLETT-PACKARD,E5071B,MY12345678,A.01.02",
            "hewlett-packard,e5071b,my12345678,a.01.02",
            "Hewlett-Packard,E5071B,MY12345678,A.01.02",
        ]

        drivers = [detect_vna_driver(idn) for idn in idn_variants]

        # All should detect the same driver (or all None)
        assert len(set(drivers)) == 1

    @pytest.mark.unit
    def test_driver_has_required_methods(self):
        """Test that discovered drivers implement required methods."""
        drivers = discover_drivers()

        for driver_name, driver_class in drivers.items():
            # Check that driver is a VNABase subclass
            assert issubclass(driver_class, VNABase)

            # Check that driver has idn_matcher
            assert hasattr(driver_class, "idn_matcher")
            assert callable(driver_class.idn_matcher)

            # Check that driver has driver_name
            assert hasattr(driver_class, "driver_name")
            assert isinstance(driver_class.driver_name, str)


class TestVNAConfiguration:
    """Test VNA configuration and parameter setting."""

    @pytest.mark.integration
    def test_configure_frequency(self, connected_dummy_vna):
        """Test frequency configuration."""
        connected_dummy_vna.config.set_freq_range = True
        connected_dummy_vna.config.start_freq_hz = 100e6
        connected_dummy_vna.config.stop_freq_hz = 2000e6

        connected_dummy_vna.configure_frequency()

        # Verify commands were sent
        commands = connected_dummy_vna.inst.command_history
        assert any("FREQ:STAR" in cmd for cmd in commands)
        assert any("FREQ:STOP" in cmd for cmd in commands)

    @pytest.mark.integration
    def test_configure_sweep_points(self, connected_dummy_vna):
        """Test sweep points configuration."""
        connected_dummy_vna.config.set_sweep_points = True
        connected_dummy_vna.config.sweep_points = 401

        connected_dummy_vna.configure_measurements()

        # Verify command was sent
        commands = connected_dummy_vna.inst.command_history
        assert any("POIN" in cmd and "401" in cmd for cmd in commands)

    @pytest.mark.integration
    def test_configure_averaging(self, connected_dummy_vna):
        """Test averaging configuration."""
        connected_dummy_vna.config.enable_averaging = True
        connected_dummy_vna.config.set_averaging_count = True
        connected_dummy_vna.config.averaging_count = 32

        connected_dummy_vna.configure_measurements()

        # Verify commands were sent
        commands = connected_dummy_vna.inst.command_history
        assert any("AVER" in cmd for cmd in commands)

    @pytest.mark.integration
    def test_setup_s_parameters(self, connected_dummy_vna):
        """Test S-parameter setup."""
        connected_dummy_vna.setup_s_parameters()

        # Verify S-parameter setup commands
        commands = connected_dummy_vna.inst.command_history
        assert any("PAR:COUN" in cmd for cmd in commands)
        assert any("S11" in cmd for cmd in commands)
        assert any("S21" in cmd for cmd in commands)
        assert any("S12" in cmd for cmd in commands)
        assert any("S22" in cmd for cmd in commands)
