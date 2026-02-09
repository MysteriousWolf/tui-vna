"""
Unit tests for HP E5071B VNA driver.

Tests HP-specific functionality including connection, configuration,
measurement sequences, and SCPI command generation.
"""

from unittest.mock import MagicMock, patch

import numpy as np
import pytest
import pyvisa

from src.tina.drivers.base import VNAConfig
from src.tina.drivers.hp_e5071b import HPE5071B


class TestHPE5071BIdentification:
    """Test HP E5071B identification and matching."""

    @pytest.mark.unit
    def test_idn_matcher_hp(self):
        """Test IDN matcher recognizes HP instruments."""
        assert HPE5071B.idn_matcher("HEWLETT-PACKARD,E5071B,MY12345678,A.01.02")
        assert HPE5071B.idn_matcher("hewlett-packard,e5071b,my12345678,a.01.02")

    @pytest.mark.unit
    def test_idn_matcher_agilent(self):
        """Test IDN matcher recognizes Agilent instruments."""
        assert HPE5071B.idn_matcher("Agilent Technologies,E5071C,MY12345678,A.09.50")

    @pytest.mark.unit
    def test_idn_matcher_keysight(self):
        """Test IDN matcher recognizes Keysight instruments."""
        assert HPE5071B.idn_matcher("Keysight Technologies,E5071A,MY12345678,A.10.00")

    @pytest.mark.unit
    def test_idn_matcher_rejects_other(self):
        """Test IDN matcher rejects non-E5071 instruments."""
        assert not HPE5071B.idn_matcher("HEWLETT-PACKARD,8753D,MY12345678,A.01.02")
        assert not HPE5071B.idn_matcher("UNKNOWN,MODEL,12345,1.0")

    @pytest.mark.unit
    def test_driver_name(self):
        """Test driver has correct name."""
        assert HPE5071B.driver_name == "HP E5071B"


class TestHPE5071BConnection:
    """Test HP E5071B connection functionality."""

    @pytest.mark.unit
    def test_instantiation(self, vna_config):
        """Test creating HP E5071B instance."""
        vna = HPE5071B(vna_config)
        assert vna is not None
        assert vna.config == vna_config
        assert not vna.is_connected()
        assert vna.inst is None

    @pytest.mark.unit
    @patch("socket.socket")
    def test_check_host_reachable_success(self, mock_socket, vna_config):
        """Test host reachability check succeeds."""
        # Mock socket to simulate successful connection
        mock_sock_instance = MagicMock()
        mock_sock_instance.connect_ex.return_value = 0
        mock_socket.return_value.__enter__.return_value = mock_sock_instance

        vna = HPE5071B(vna_config)
        result = vna._check_host_reachable("192.168.1.100")
        assert result is True

    @pytest.mark.unit
    @patch("socket.socket")
    def test_check_host_reachable_failure(self, mock_socket, vna_config):
        """Test host reachability check fails."""
        # Mock socket to simulate failed connection
        mock_sock_instance = MagicMock()
        mock_sock_instance.connect_ex.return_value = 1  # Connection refused
        mock_socket.return_value.__enter__.return_value = mock_sock_instance

        vna = HPE5071B(vna_config)
        result = vna._check_host_reachable("192.168.1.100", timeout=0.1)
        assert result is False

    @pytest.mark.unit
    def test_connect_no_host(self):
        """Test that connecting without host raises error."""
        config = VNAConfig()  # No host specified
        vna = HPE5071B(config)

        with pytest.raises((ValueError, ConnectionError)):
            vna.connect()

    @pytest.mark.integration
    def test_connect_disconnect_cycle(
        self, vna_config, mock_pyvisa_resource_manager, patch_socket_reachable
    ):
        """Test connecting and disconnecting."""
        vna = HPE5071B(vna_config)

        # Connect
        assert vna.connect()
        assert vna.is_connected()
        assert vna.idn is not None
        assert vna.inst is not None

        # Disconnect
        vna.disconnect()
        assert not vna.is_connected()
        assert vna.idn == ""

    @pytest.mark.integration
    def test_double_connect(
        self, vna_config, mock_pyvisa_resource_manager, patch_socket_reachable
    ):
        """Test that connecting twice doesn't cause issues."""
        vna = HPE5071B(vna_config)

        # First connection
        vna.connect()
        idn1 = vna.idn

        # Second connection (should work or gracefully handle)
        vna.disconnect()
        vna.connect()
        idn2 = vna.idn

        assert idn1 == idn2
        vna.disconnect()

    @pytest.mark.integration
    def test_context_manager(
        self, vna_config, mock_pyvisa_resource_manager, patch_socket_reachable
    ):
        """Test using HP E5071B as context manager."""
        vna = HPE5071B(vna_config)

        with vna:
            assert vna.is_connected()

        assert not vna.is_connected()


class TestHPE5071BConfiguration:
    """Test HP E5071B configuration methods."""

    @pytest.mark.integration
    def test_get_current_parameters(
        self, vna_config, mock_pyvisa_resource_manager, patch_socket_reachable
    ):
        """Test reading current VNA parameters."""
        vna = HPE5071B(vna_config)
        vna.connect()

        params = vna.get_current_parameters()

        assert "start_freq_hz" in params
        assert "stop_freq_hz" in params
        assert "sweep_points" in params
        assert "averaging_enabled" in params
        assert "averaging_count" in params

        # All values should be present (not None)
        assert params["start_freq_hz"] is not None
        assert params["stop_freq_hz"] is not None
        assert params["sweep_points"] is not None

        vna.disconnect()

    @pytest.mark.integration
    def test_configure_frequency_when_enabled(
        self, vna_config, mock_pyvisa_resource_manager, patch_socket_reachable
    ):
        """Test frequency configuration when override is enabled."""
        vna = HPE5071B(vna_config)
        vna.config.set_freq_range = True
        vna.config.start_freq_hz = 100e6
        vna.config.stop_freq_hz = 2000e6
        vna.connect()

        vna.configure_frequency()

        # Verify commands were sent
        assert vna.inst is not None
        commands = vna.inst.command_history
        assert any("FREQ:STAR" in cmd for cmd in commands)
        assert any("FREQ:STOP" in cmd for cmd in commands)

        vna.disconnect()

    @pytest.mark.integration
    def test_configure_frequency_when_disabled(
        self, vna_config, mock_pyvisa_resource_manager, patch_socket_reachable
    ):
        """Test frequency configuration when override is disabled."""
        vna = HPE5071B(vna_config)
        vna.config.set_freq_range = False
        vna.connect()

        initial_cmd_count = len(vna.inst.command_history)
        vna.configure_frequency()

        # Should not send frequency commands
        new_commands = vna.inst.command_history[initial_cmd_count:]
        assert not any("FREQ:STAR" in cmd for cmd in new_commands)
        assert not any("FREQ:STOP" in cmd for cmd in new_commands)

        vna.disconnect()

    @pytest.mark.integration
    def test_configure_measurements(
        self, vna_config, mock_pyvisa_resource_manager, patch_socket_reachable
    ):
        """Test measurement configuration."""
        vna = HPE5071B(vna_config)
        vna.config.set_sweep_points = True
        vna.config.sweep_points = 401
        vna.config.enable_averaging = True
        vna.config.set_averaging_count = True
        vna.config.averaging_count = 32
        vna.connect()

        vna.configure_measurements()

        commands = vna.inst.command_history
        # Should set format, sweep type, points, averaging
        assert any("FORM" in cmd and "ASC" in cmd for cmd in commands)
        assert any("SWE" in cmd and "LIN" in cmd for cmd in commands)
        assert any("POIN" in cmd for cmd in commands)
        assert any("AVER" in cmd for cmd in commands)

        vna.disconnect()


class TestHPE5071BMeasurement:
    """Test HP E5071B measurement functionality."""

    @pytest.mark.integration
    def test_setup_s_parameters(
        self, vna_config, mock_pyvisa_resource_manager, patch_socket_reachable
    ):
        """Test S-parameter setup."""
        vna = HPE5071B(vna_config)
        vna.connect()

        vna.setup_s_parameters()

        commands = vna.inst.command_history
        # Should configure 4 parameters
        assert any("PAR:COUN" in cmd and "4" in cmd for cmd in commands)
        # Should define all S-parameters
        assert any("S11" in cmd for cmd in commands)
        assert any("S21" in cmd for cmd in commands)
        assert any("S12" in cmd for cmd in commands)
        assert any("S22" in cmd for cmd in commands)

        vna.disconnect()

    @pytest.mark.integration
    def test_trigger_sweep(
        self, vna_config, mock_pyvisa_resource_manager, patch_socket_reachable
    ):
        """Test triggering a sweep."""
        vna = HPE5071B(vna_config)
        vna.connect()

        vna.trigger_sweep()

        commands = vna.inst.command_history
        queries = vna.inst.query_history

        # Should abort, set single mode, set BUS trigger, init
        assert any("ABOR" in cmd for cmd in commands)
        assert any("INIT1:CONT" in cmd and "OFF" in cmd for cmd in commands)
        assert any("TRIG:SOUR" in cmd and "BUS" in cmd for cmd in commands)
        assert any("INIT" in cmd for cmd in commands)
        assert "*OPC?" in queries

        vna.disconnect()

    @pytest.mark.integration
    def test_get_frequency_axis(
        self, vna_config, mock_pyvisa_resource_manager, patch_socket_reachable
    ):
        """Test getting frequency axis."""
        vna = HPE5071B(vna_config)
        vna.connect()

        freqs = vna.get_frequency_axis()

        assert isinstance(freqs, np.ndarray)
        assert len(freqs) > 0
        assert freqs[0] < freqs[-1]  # Ascending

        vna.disconnect()

    @pytest.mark.integration
    def test_get_sparam_data(
        self, vna_config, mock_pyvisa_resource_manager, patch_socket_reachable
    ):
        """Test getting S-parameter data."""
        vna = HPE5071B(vna_config)
        vna.connect()

        mag_db, phase_deg = vna.get_sparam_data(1)  # S11

        assert isinstance(mag_db, np.ndarray)
        assert isinstance(phase_deg, np.ndarray)
        assert len(mag_db) == len(phase_deg)
        assert len(mag_db) > 0

        # Magnitude should be in dB (likely negative for reflection)
        # Phase should be in degrees (-180 to 180 or unwrapped)
        assert np.all(np.isfinite(mag_db))
        assert np.all(np.isfinite(phase_deg))

        vna.disconnect()

    @pytest.mark.integration
    def test_get_all_sparameters(
        self, vna_config, mock_pyvisa_resource_manager, patch_socket_reachable
    ):
        """Test getting all S-parameters."""
        vna = HPE5071B(vna_config)
        vna.connect()

        sparams = vna.get_all_sparameters()

        assert "S11" in sparams
        assert "S21" in sparams
        assert "S12" in sparams
        assert "S22" in sparams

        for param_name, (mag, phase) in sparams.items():
            assert isinstance(mag, np.ndarray)
            assert isinstance(phase, np.ndarray)
            assert len(mag) == len(phase)
            assert len(mag) > 0

        vna.disconnect()

    @pytest.mark.integration
    def test_perform_measurement(
        self, vna_config, mock_pyvisa_resource_manager, patch_socket_reachable
    ):
        """Test complete measurement cycle."""
        vna = HPE5071B(vna_config)
        vna.connect()

        freqs, sparams = vna.perform_measurement()

        # Verify frequencies
        assert isinstance(freqs, np.ndarray)
        assert len(freqs) > 0

        # Verify S-parameters
        assert len(sparams) == 4
        for param_name, (mag, phase) in sparams.items():
            assert len(mag) == len(freqs)
            assert len(phase) == len(freqs)

        vna.disconnect()


class TestHPE5071BTriggerState:
    """Test HP E5071B trigger state save/restore."""

    @pytest.mark.integration
    def test_save_trigger_state(
        self, vna_config, mock_pyvisa_resource_manager, patch_socket_reachable
    ):
        """Test saving trigger state."""
        vna = HPE5071B(vna_config)
        vna.connect()

        state = vna.save_trigger_state()

        assert isinstance(state, tuple)
        assert len(state) == 2
        trigger_source, continuous = state
        assert isinstance(trigger_source, str)
        assert isinstance(continuous, bool)

        vna.disconnect()

    @pytest.mark.integration
    def test_restore_trigger_state(
        self, vna_config, mock_pyvisa_resource_manager, patch_socket_reachable
    ):
        """Test restoring trigger state."""
        vna = HPE5071B(vna_config)
        vna.connect()

        # Save initial state
        initial_state = vna.save_trigger_state()

        # Change state
        vna.set_trigger_source("BUS")

        # Restore state
        vna.restore_trigger_state(initial_state)

        # Verify restoration
        current_state = vna.save_trigger_state()
        assert current_state == initial_state

        vna.disconnect()


class TestHPE5071BErrorHandling:
    """Test HP E5071B error handling and edge cases."""

    @pytest.mark.unit
    def test_ensure_connected_raises_when_disconnected(self, vna_config):
        """Test that operations fail when not connected."""
        vna = HPE5071B(vna_config)

        with pytest.raises(RuntimeError, match="Not connected"):
            vna._ensure_connected()

    @pytest.mark.integration
    def test_disconnect_when_not_connected(self, vna_config):
        """Test that disconnecting when not connected is safe."""
        vna = HPE5071B(vna_config)
        # Should not raise
        vna.disconnect()

    @pytest.mark.integration
    def test_operations_after_disconnect_fail(
        self, vna_config, mock_pyvisa_resource_manager, patch_socket_reachable
    ):
        """Test that operations after disconnect fail gracefully."""
        vna = HPE5071B(vna_config)
        vna.connect()
        vna.disconnect()

        with pytest.raises((RuntimeError, pyvisa.VisaIOError)):
            vna.get_frequency_axis()
