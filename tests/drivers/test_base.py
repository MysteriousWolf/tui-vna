"""
Unit tests for VNA driver base classes and configuration.

Tests the base driver abstraction, driver discovery, and configuration.
"""

import pytest

from src.tina.drivers.base import (
    IDNInfo,
    VNABase,
    VNAConfig,
    detect_vna_driver,
    discover_drivers,
    list_available_drivers,
)
from tests.fixtures.mock_vna import MockVNA as DummyVNA


class TestIDNInfo:
    """Tests for IDNInfo parsing and formatting."""

    # --- from_idn_string ---

    @pytest.mark.unit
    def test_parse_full_idn(self):
        """Parse a complete four-field IDN string."""
        info = IDNInfo.from_idn_string("Agilent Technologies,E5071B,MY42402671,A.05.01")
        assert info.vendor == "Agilent Technologies"
        assert info.model == "E5071B"
        assert info.serial == "MY42402671"
        assert info.firmware == "A.05.01"
        assert info.raw == "Agilent Technologies,E5071B,MY42402671,A.05.01"

    @pytest.mark.unit
    def test_parse_idn_strips_whitespace(self):
        """Fields with surrounding whitespace are stripped."""
        info = IDNInfo.from_idn_string(" Agilent , E5071B , MY123 , A.01 ")
        assert info.vendor == "Agilent"
        assert info.model == "E5071B"
        assert info.serial == "MY123"
        assert info.firmware == "A.01"

    @pytest.mark.unit
    def test_parse_idn_three_fields(self):
        """IDN with only three fields leaves firmware empty."""
        info = IDNInfo.from_idn_string("Vendor,Model,Serial")
        assert info.vendor == "Vendor"
        assert info.model == "Model"
        assert info.serial == "Serial"
        assert info.firmware == ""

    @pytest.mark.unit
    def test_parse_idn_two_fields(self):
        """IDN with only two fields leaves serial and firmware empty."""
        info = IDNInfo.from_idn_string("Vendor,Model")
        assert info.vendor == "Vendor"
        assert info.model == "Model"
        assert info.serial == ""
        assert info.firmware == ""

    @pytest.mark.unit
    def test_parse_idn_one_field(self):
        """IDN with a single token fills only vendor."""
        info = IDNInfo.from_idn_string("OnlyVendor")
        assert info.vendor == "OnlyVendor"
        assert info.model == ""
        assert info.serial == ""
        assert info.firmware == ""

    @pytest.mark.unit
    def test_parse_empty_string(self):
        """Empty IDN string produces all-empty fields."""
        info = IDNInfo.from_idn_string("")
        assert info.vendor == ""
        assert info.model == ""
        assert info.serial == ""
        assert info.firmware == ""
        assert info.raw == ""

    @pytest.mark.unit
    def test_parse_preserves_raw(self):
        """raw field holds the original unmodified string."""
        raw = "  Agilent , E5071B , MY123 , A.01 "
        info = IDNInfo.from_idn_string(raw)
        assert info.raw == raw

    @pytest.mark.unit
    def test_parse_extra_fields_ignored(self):
        """Extra comma-separated fields beyond four are silently ignored."""
        info = IDNInfo.from_idn_string("V,M,S,F,extra,more")
        assert info.vendor == "V"
        assert info.model == "M"
        assert info.serial == "S"
        assert info.firmware == "F"

    @pytest.mark.unit
    def test_parse_hewlett_packard_idn(self):
        """Parse the legacy HEWLETT-PACKARD IDN format used in mock tests."""
        info = IDNInfo.from_idn_string("HEWLETT-PACKARD,E5071B,MY12345678,A.01.02")
        assert info.vendor == "HEWLETT-PACKARD"
        assert info.model == "E5071B"
        assert info.serial == "MY12345678"
        assert info.firmware == "A.01.02"

    # --- __str__ ---

    @pytest.mark.unit
    def test_str_all_fields(self):
        """All four fields produce the full formatted string."""
        info = IDNInfo(
            vendor="Agilent Technologies",
            model="E5071B",
            serial="MY42402671",
            firmware="A.05.01",
        )
        assert str(info) == "Agilent Technologies E5071B (SN: MY42402671, FW: A.05.01)"

    @pytest.mark.unit
    def test_str_no_serial(self):
        """Missing serial omits the SN label; FW label still appears."""
        info = IDNInfo(vendor="Agilent", model="E5071B", firmware="A.05.01")
        assert str(info) == "Agilent E5071B (FW: A.05.01)"

    @pytest.mark.unit
    def test_str_no_firmware(self):
        """Missing firmware omits the FW label; SN label still appears."""
        info = IDNInfo(vendor="Agilent", model="E5071B", serial="MY123")
        assert str(info) == "Agilent E5071B (SN: MY123)"

    @pytest.mark.unit
    def test_str_no_serial_no_firmware(self):
        """No serial and no firmware omit the parenthesised block entirely."""
        info = IDNInfo(vendor="Agilent", model="E5071B")
        assert str(info) == "Agilent E5071B"

    @pytest.mark.unit
    def test_str_only_vendor(self):
        """Only vendor present produces just the vendor name."""
        info = IDNInfo(vendor="Agilent")
        assert str(info) == "Agilent"

    @pytest.mark.unit
    def test_str_empty(self):
        """Fully empty IDNInfo produces an empty string."""
        assert str(IDNInfo()) == ""

    @pytest.mark.unit
    def test_str_serial_only_in_details(self):
        """Serial-only detail block uses SN label without FW."""
        info = IDNInfo(serial="MY123")
        assert str(info) == "(SN: MY123)"

    @pytest.mark.unit
    def test_str_firmware_only_in_details(self):
        """Firmware-only detail block uses FW label without SN."""
        info = IDNInfo(firmware="A.05.01")
        assert str(info) == "(FW: A.05.01)"

    # --- roundtrip ---

    @pytest.mark.unit
    def test_roundtrip_str_contains_model(self):
        """str(from_idn_string(s)) includes the model from the raw string."""
        idn = "Agilent Technologies,E5071B,MY42402671,A.05.01"
        assert "E5071B" in str(IDNInfo.from_idn_string(idn))


class TestVNABaseIDNProperties:
    """Tests for VNABase.idn_info and VNABase.display_name properties."""

    @pytest.mark.unit
    def test_idn_info_before_connect(self, mock_vna):
        """idn_info returns all-empty IDNInfo when not yet connected."""
        info = mock_vna.idn_info
        assert isinstance(info, IDNInfo)
        assert info.vendor == ""
        assert info.model == ""
        assert info.serial == ""
        assert info.firmware == ""

    @pytest.mark.unit
    def test_idn_info_after_connect(self, connected_mock_e5071b):
        """idn_info is populated with correct fields after connection."""
        info = connected_mock_e5071b.idn_info
        assert isinstance(info, IDNInfo)
        assert info.vendor != ""
        assert info.model != ""
        # MockE5071B IDN contains E5071B
        assert "E5071B" in info.model.upper() or "E5071B" in info.raw.upper()

    @pytest.mark.unit
    def test_idn_info_fields_match_idn_string(self, connected_mock_e5071b):
        """idn_info fields are consistent with the raw idn property."""
        idn_str = connected_mock_e5071b.idn
        info = connected_mock_e5071b.idn_info
        assert info.raw == idn_str
        parts = [p.strip() for p in idn_str.split(",")]
        assert info.vendor == parts[0]
        assert info.model == parts[1]

    @pytest.mark.unit
    def test_display_name_contains_driver_name(self, connected_mock_e5071b):
        """display_name includes the driver_name in square brackets."""
        name = connected_mock_e5071b.display_name
        assert f"[{connected_mock_e5071b.driver_name}]" in name

    @pytest.mark.unit
    def test_display_name_contains_model(self, connected_mock_e5071b):
        """display_name includes the model number from the IDN."""
        name = connected_mock_e5071b.display_name
        info = connected_mock_e5071b.idn_info
        assert info.model in name

    @pytest.mark.unit
    def test_display_name_contains_host_and_port(self, connected_mock_e5071b):
        """display_name includes the host:port from the config in parentheses."""
        name = connected_mock_e5071b.display_name
        cfg = connected_mock_e5071b.config
        assert f"({cfg.host}:{cfg.port})" in name

    @pytest.mark.unit
    def test_display_name_format(self, connected_mock_e5071b):
        """display_name matches '<vendor> <model> (<host>:<port>) [driver]'."""
        name = connected_mock_e5071b.display_name
        info = connected_mock_e5071b.idn_info
        cfg = connected_mock_e5071b.config
        instrument = " ".join(p for p in (info.vendor, info.model) if p)
        expected = f"{instrument} ({cfg.host}:{cfg.port}) [{connected_mock_e5071b.driver_name}]"
        assert name == expected

    @pytest.mark.unit
    def test_display_name_before_connect(self, mock_vna):
        """display_name before connection still returns a valid string."""
        name = mock_vna.display_name
        assert isinstance(name, str)
        assert f"[{mock_vna.driver_name}]" in name


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
