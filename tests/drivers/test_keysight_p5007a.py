"""
Unit tests for Keysight P5007A VNA driver.

Tests P5007A-specific functionality including identification, connection,
configuration, measurement sequences, and SCPI command generation.
"""

from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from tina.drivers.keysight_p5007a import KeysightP5007A


class TestKeysightP5007AIdentification:
    """Test Keysight P5007A identification and matching."""

    @pytest.mark.unit
    def test_idn_matcher_p5007a(self):
        """Test IDN matcher recognizes P5007A instruments."""
        assert KeysightP5007A.idn_matcher(
            "Keysight Technologies,P5007A,MY12345678,A.01.00"
        )
        assert KeysightP5007A.idn_matcher("keysight,p5007a,my12345678,a.01.00")

    @pytest.mark.unit
    def test_idn_matcher_pna_family(self):
        """Test IDN matcher recognizes PNA-family variants."""
        assert KeysightP5007A.idn_matcher("KEYSIGHT,P5007A,12345,1.0")

    @pytest.mark.unit
    def test_idn_matcher_rejects_other(self):
        """Test IDN matcher rejects non-P5007A instruments."""
        assert not KeysightP5007A.idn_matcher(
            "HEWLETT-PACKARD,E5071B,MY12345678,A.01.02"
        )
        assert not KeysightP5007A.idn_matcher("Keysight Technologies,N9913A,MY123,1.0")
        assert not KeysightP5007A.idn_matcher("UNKNOWN,MODEL,12345,1.0")
        assert not KeysightP5007A.idn_matcher("")

    @pytest.mark.unit
    def test_driver_name(self):
        """Test driver has correct name."""
        assert KeysightP5007A.driver_name == "Keysight P5007A"

    @pytest.mark.unit
    def test_parameter_names(self):
        """Test S-parameter names are correctly defined."""
        assert KeysightP5007A._S_PARAMETER_NAMES == ("S11", "S21", "S12", "S22")


class TestKeysightP5007AConnection:
    """Test Keysight P5007A connection functionality."""

    @pytest.mark.unit
    def test_instantiation(self, vna_config):
        """Test creating KeysightP5007A instance."""
        vna = KeysightP5007A(vna_config)
        assert vna is not None
        assert vna.config == vna_config
        assert not vna.is_connected()
        assert vna.inst is None

    @pytest.mark.unit
    @patch("socket.socket")
    def test_check_host_reachable_success(self, mock_socket, vna_config):
        """Test host reachability check succeeds."""
        mock_sock_instance = MagicMock()
        mock_sock_instance.connect_ex.return_value = 0
        mock_socket.return_value.__enter__.return_value = mock_sock_instance

        vna = KeysightP5007A(vna_config)
        result = vna._check_host_reachable("192.168.1.100")
        assert result is True

    @pytest.mark.unit
    @patch("socket.socket")
    def test_check_host_reachable_failure(self, mock_socket, vna_config):
        """Test host reachability check fails."""
        mock_sock_instance = MagicMock()
        mock_sock_instance.connect_ex.return_value = 1
        mock_socket.return_value.__enter__.return_value = mock_sock_instance

        vna = KeysightP5007A(vna_config)
        result = vna._check_host_reachable("192.168.1.100")
        assert result is False

    @pytest.mark.unit
    @patch("socket.socket")
    def test_check_host_reachable_timeout(self, mock_socket, vna_config):
        """Test host reachability check with timeout."""
        mock_sock_instance = MagicMock()
        mock_sock_instance.connect_ex.side_effect = OSError("Connection refused")
        mock_socket.return_value.__enter__.return_value = mock_sock_instance

        vna = KeysightP5007A(vna_config)
        result = vna._check_host_reachable("192.168.1.100")
        assert result is False

    @pytest.mark.unit
    def test_connect_success(self, vna_config):
        """Test successful connection to P5007A."""
        vna = KeysightP5007A(vna_config)

        mock_inst = MagicMock()
        mock_inst.timeout = None
        mock_inst.query.return_value = "Keysight Technologies,P5007A,MY12345678,A.01.00"

        with patch.object(vna, "_check_host_reachable", return_value=True):
            with patch("pyvisa.ResourceManager") as mock_rm_class:
                mock_rm = MagicMock()
                mock_rm.open_resource.return_value = mock_inst
                mock_rm_class.return_value = mock_rm

                result = vna.connect(progress_callback=None)
                assert result is True
                assert vna.is_connected()
                assert vna.inst is mock_inst

    @pytest.mark.unit
    def test_connect_rejects_mismatched_idn(self, vna_config):
        """Connection should fail when *IDN? identifies a different instrument."""
        vna = KeysightP5007A(vna_config)

        mock_inst = MagicMock()
        mock_inst.timeout = None
        mock_inst.query.return_value = "Keysight Technologies,N9913A,MY12345678,A.01.00"

        with patch.object(vna, "_check_host_reachable", return_value=True):
            with patch("pyvisa.ResourceManager") as mock_rm_class:
                mock_rm = MagicMock()
                mock_rm.open_resource.return_value = mock_inst
                mock_rm_class.return_value = mock_rm

                with pytest.raises(ConnectionError, match="Expected Keysight P5007A"):
                    vna.connect(progress_callback=None)
                assert not vna.is_connected()

    @pytest.mark.unit
    def test_connect_host_unreachable(self, vna_config):
        """Test connection fails when host is unreachable."""
        vna = KeysightP5007A(vna_config)

        with patch.object(vna, "_check_host_reachable", return_value=False):
            with pytest.raises(ConnectionError):
                vna.connect(progress_callback=None)
            assert not vna.is_connected()

    @pytest.mark.unit
    def test_connect_resource_manager_failure(self, vna_config):
        """Test connection handles ResourceManager failure gracefully."""
        vna = KeysightP5007A(vna_config)

        mock_inst = MagicMock()
        mock_inst.timeout = None
        mock_inst.query.return_value = "Keysight Technologies,P5007A,MY12345678,A.01.00"

        with patch.object(vna, "_check_host_reachable", return_value=True):
            # First call raises, second succeeds
            mock_rm_ok = MagicMock()
            mock_rm_ok.open_resource.return_value = mock_inst

            mock_rm_class = MagicMock()
            mock_rm_class.side_effect = [Exception("fail"), mock_rm_ok]

            with patch("pyvisa.ResourceManager", mock_rm_class):
                result = vna.connect(progress_callback=None)
                assert result is True
                assert vna.is_connected()

    @pytest.mark.unit
    def test_disconnect(self, vna_config):
        """Test disconnection from P5007A."""
        vna = KeysightP5007A(vna_config)
        mock_inst = MagicMock()
        vna.inst = mock_inst
        vna._connected = True
        vna._idn = "Keysight Technologies,P5007A,MY12345678,A.01.00"

        vna.disconnect()
        assert not vna.is_connected()
        assert vna.inst is None
        assert vna._idn == ""
        mock_inst.close.assert_called_once()

    @pytest.mark.unit
    def test_disconnect_when_not_connected(self, vna_config):
        """Test disconnect when already disconnected."""
        vna = KeysightP5007A(vna_config)
        vna.disconnect()  # Should not raise
        assert not vna.is_connected()

    @pytest.mark.unit
    def test_disconnect_cleanup_error(self, vna_config):
        """Test disconnect handles cleanup errors gracefully."""
        vna = KeysightP5007A(vna_config)
        mock_inst = MagicMock()
        mock_inst.close.side_effect = Exception("Close error")
        vna.inst = mock_inst
        vna._connected = True

        vna.disconnect()  # Should not raise
        assert not vna.is_connected()
        assert vna.inst is None


class TestKeysightP5007AConfiguration:
    """Test Keysight P5007A configuration commands."""

    @pytest.fixture
    def connected_vna(self, vna_config):
        """Create a connected VNA with mocked instrument."""
        vna = KeysightP5007A(vna_config)
        mock_inst = MagicMock()
        vna.inst = mock_inst
        vna._connected = True
        return vna, mock_inst

    @pytest.mark.unit
    def test_configure_frequency(self, connected_vna):
        """Test frequency configuration commands."""
        vna, mock_inst = connected_vna
        vna.config.start_freq_hz = 10e6
        vna.config.stop_freq_hz = 1500e6
        vna.config.set_freq_range = True

        vna.configure_frequency()

        mock_inst.write.assert_any_call("SENS1:FREQ:STAR 10000000.0")
        mock_inst.write.assert_any_call("SENS1:FREQ:STOP 1500000000.0")

    @pytest.mark.unit
    def test_configure_frequency_not_set(self, connected_vna):
        """Test frequency configuration skipped when set_freq_range is False."""
        vna, mock_inst = connected_vna
        vna.config.set_freq_range = False

        vna.configure_frequency()

        mock_inst.write.assert_not_called()

    @pytest.mark.unit
    def test_configure_frequency_invalid_range(self, connected_vna):
        """Test frequency configuration rejects invalid range."""
        vna, mock_inst = connected_vna
        vna.config.start_freq_hz = 1500e6
        vna.config.stop_freq_hz = 10e6
        vna.config.set_freq_range = True

        with pytest.raises(ValueError, match="Stop frequency must be greater"):
            vna.configure_frequency()

    @pytest.mark.unit
    def test_configure_measurements(self, connected_vna):
        """Test measurement configuration commands."""
        vna, mock_inst = connected_vna

        vna.configure_measurements()

        mock_inst.write.assert_any_call("FORM:DATA ASCII")
        mock_inst.write.assert_any_call("SENS1:SWE:TYPE LIN")
        mock_inst.write.assert_any_call("SENS1:AVER:STAT OFF")

    @pytest.mark.unit
    def test_configure_measurements_with_averaging(self, connected_vna):
        """Test measurement configuration with averaging enabled."""
        vna, mock_inst = connected_vna
        vna.config.enable_averaging = True
        vna.config.set_averaging_count = True
        vna.config.averaging_count = 4

        vna.configure_measurements()

        mock_inst.write.assert_any_call("SENS1:AVER:STAT ON")
        mock_inst.write.assert_any_call("SENS1:AVER:COUN 4")

    @pytest.mark.unit
    @patch("time.sleep")
    def test_setup_s_parameters(self, mock_sleep, connected_vna):
        """Test S-parameter measurement setup."""
        vna, mock_inst = connected_vna

        vna.setup_s_parameters()

        # Collect all write calls
        write_calls = [args[0] for args, kwargs in mock_inst.write.call_args_list]

        assert "DISP:WIND1:STAT ON" in write_calls
        assert "CALC1:PAR:DEL:ALL" in write_calls
        assert "CALC1:PAR:EXT 'CH1_S11',S11" in write_calls
        assert "DISP:WIND1:TRAC1:FEED 'CH1_S11'" in write_calls
        assert "CALC1:PAR:SEL 'CH1_S11'" in write_calls

    @pytest.mark.unit
    def test_parameter_name(self, vna_config):
        """Test parameter name mapping."""
        vna = KeysightP5007A(vna_config)
        assert vna._parameter_name(1) == "CH1_S11"
        assert vna._parameter_name(2) == "CH1_S21"
        assert vna._parameter_name(3) == "CH1_S12"
        assert vna._parameter_name(4) == "CH1_S22"

    @pytest.mark.unit
    def test_parameter_name_invalid(self, vna_config):
        """Test parameter name rejects invalid index."""
        vna = KeysightP5007A(vna_config)
        with pytest.raises(ValueError, match="Unsupported S-parameter index"):
            vna._parameter_name(5)


class TestKeysightP5007ATrigger:
    """Test Keysight P5007A trigger and sweep functionality."""

    @pytest.fixture
    def connected_vna(self, vna_config):
        """Create a connected VNA with mocked instrument."""
        vna = KeysightP5007A(vna_config)
        mock_inst = MagicMock()
        vna.inst = mock_inst
        vna._connected = True
        return vna, mock_inst

    @pytest.mark.unit
    def test_get_trigger_source(self, connected_vna):
        """Test getting trigger source."""
        vna, mock_inst = connected_vna
        mock_inst.query.return_value = "IMM\n"
        assert vna.get_trigger_source() == "IMM"

    @pytest.mark.unit
    def test_set_trigger_source(self, connected_vna):
        """Test setting trigger source."""
        vna, mock_inst = connected_vna
        vna.set_trigger_source("BUS")
        mock_inst.write.assert_called_with("TRIG:SOUR BUS")

    @pytest.mark.unit
    def test_save_and_restore_trigger_state(self, connected_vna):
        """Test trigger state save and restore."""
        vna, mock_inst = connected_vna
        mock_inst.query.side_effect = ["IMM\n", "1\n"]

        state = vna.save_trigger_state()
        assert state == ("IMM", True)

        vna.restore_trigger_state(state)
        mock_inst.write.assert_any_call("TRIG:SOUR IMM")
        mock_inst.write.assert_any_call("INIT1:CONT ON")

    @pytest.mark.unit
    @patch("time.sleep")
    def test_trigger_sweep(self, mock_sleep, vna_config):
        """Test trigger sweep sequence."""
        vna = KeysightP5007A(vna_config)
        mock_inst = MagicMock()
        vna.inst = mock_inst
        vna._connected = True
        vna.config.enable_averaging = False

        # Mock _wait_for_operation_complete to return immediately
        vna._wait_for_operation_complete = MagicMock()

        vna.trigger_sweep()

        mock_inst.write.assert_any_call("ABOR")
        mock_inst.write.assert_any_call("INIT1:CONT OFF")
        mock_inst.write.assert_any_call("TRIG:SOUR BUS")
        mock_inst.write.assert_any_call("INIT1:IMM")
        mock_inst.write.assert_any_call("*TRG")

    @pytest.mark.unit
    @patch("time.sleep")
    def test_trigger_sweep_with_averaging(self, mock_sleep, vna_config):
        """Test trigger sweep with averaging enabled."""
        vna = KeysightP5007A(vna_config)
        mock_inst = MagicMock()
        vna.inst = mock_inst
        vna._connected = True
        vna.config.enable_averaging = True

        # Mock _wait_for_operation_complete to return immediately
        vna._wait_for_operation_complete = MagicMock()

        vna.trigger_sweep()

        mock_inst.write.assert_any_call("SENS1:AVER:CLE")
        mock_inst.write.assert_any_call("ABOR")


class TestKeysightP5007ADataAcquisition:
    """Test Keysight P5007A data acquisition methods."""

    @pytest.fixture
    def connected_vna(self, vna_config):
        """Create a connected VNA with mocked instrument."""
        vna = KeysightP5007A(vna_config)
        mock_inst = MagicMock()
        vna.inst = mock_inst
        vna._connected = True
        return vna, mock_inst

    @pytest.mark.unit
    def test_get_frequency_axis(self, connected_vna):
        """Test frequency axis acquisition."""
        vna, mock_inst = connected_vna
        mock_inst.query.side_effect = ["10000000.0", "1500000000.0", "201"]
        mock_inst.query_ascii_values.return_value = []

        freqs = vna.get_frequency_axis()
        assert len(freqs) == 201
        assert freqs[0] == pytest.approx(10e6)
        assert freqs[-1] == pytest.approx(1500e6)

    @pytest.mark.unit
    def test_get_frequency_axis_single_point(self, connected_vna):
        """Test frequency axis with single point."""
        vna, mock_inst = connected_vna
        mock_inst.query.side_effect = ["10000000.0", "10000000.0", "1"]

        freqs = vna.get_frequency_axis()
        assert len(freqs) == 1
        assert freqs[0] == pytest.approx(10e6)

    @pytest.mark.unit
    def test_get_sparam_data(self, connected_vna):
        """Test S-parameter data acquisition."""
        vna, mock_inst = connected_vna
        # Simulate complex data: real, imag pairs
        mock_inst.query_ascii_values.return_value = [0.5, -0.5, 0.7, -0.3]
        mock_inst.query.return_value = "1\n"

        mag, phase = vna.get_sparam_data(1)
        assert len(mag) == 2
        assert len(phase) == 2

    @pytest.mark.unit
    def test_get_sparam_data_odd_length(self, connected_vna):
        """Odd-length SDAT responses should raise a clear parse error."""
        vna, mock_inst = connected_vna
        mock_inst.query_ascii_values.return_value = [0.5, -0.5, 0.7]
        mock_inst.query.return_value = "1\n"

        with pytest.raises(ValueError, match="odd number of values"):
            vna.get_sparam_data(1)

    @pytest.mark.unit
    def test_get_all_sparameters(self, connected_vna):
        """Test getting all S-parameters."""
        vna, mock_inst = connected_vna

        # Mock frequency axis
        vna.get_frequency_axis = MagicMock(return_value=np.linspace(10e6, 1500e6, 201))

        # Mock get_sparam_data for each parameter
        def mock_sparam(param_num):
            return (np.ones(201) * param_num, np.zeros(201))

        vna.get_sparam_data = MagicMock(side_effect=mock_sparam)

        result = vna.get_all_sparameters()
        assert "S11" in result
        assert "S21" in result
        assert "S12" in result
        assert "S22" in result


class TestKeysightP5007AStatus:
    """Test Keysight P5007A status queries."""

    @pytest.fixture
    def connected_vna(self, vna_config):
        """Create a connected VNA with mocked instrument."""
        vna = KeysightP5007A(vna_config)
        mock_inst = MagicMock()
        vna.inst = mock_inst
        vna._connected = True
        return vna, mock_inst

    @pytest.mark.unit
    def test_get_status(self, connected_vna):
        """Test status query returns expected keys."""
        vna, mock_inst = connected_vna
        mock_inst.query.side_effect = [
            "1\n",  # cal_enabled
            "SOLT\n",  # cal_type
            "1\n",  # smoothing_enabled
            "3.0\n",  # smoothing_aperture
            "1000\n",  # if_bandwidth
            "-10\n",  # port_power
            "IMM\n",  # trigger_source
        ]

        status = vna.get_status()
        assert "cal_enabled" in status
        assert "cal_type" in status
        assert "smoothing_enabled" in status
        assert "smoothing_aperture" in status
        assert "if_bandwidth_hz" in status
        assert "port_power_dbm" in status
        assert "trigger_source" in status

    @pytest.mark.unit
    def test_get_status_handles_errors(self, connected_vna):
        """Test status query handles SCPI errors gracefully."""
        vna, mock_inst = connected_vna
        mock_inst.query.side_effect = Exception("SCPI error")

        status = vna.get_status()
        # All values should be None when queries fail
        assert status["cal_enabled"] is None
        assert status["cal_type"] is None

    @pytest.mark.unit
    def test_get_current_parameters(self, connected_vna):
        """Test reading current instrument parameters."""
        vna, mock_inst = connected_vna
        mock_inst.query.side_effect = [
            "10000000.0\n",  # start_freq
            "1500000000.0\n",  # stop_freq
            "201\n",  # sweep_points
            "1\n",  # averaging enabled
            "4\n",  # averaging count
        ]

        params = vna.get_current_parameters()
        assert params["start_freq_hz"] == pytest.approx(10e6)
        assert params["stop_freq_hz"] == pytest.approx(1500e6)
        assert params["sweep_points"] == 201
        assert params["averaging_enabled"] is True
        assert params["averaging_count"] == 4


class TestKeysightP5007AHelpers:
    """Test Keysight P5007A helper methods."""

    @pytest.mark.unit
    def test_ensure_connected_raises_when_disconnected(self, vna_config):
        """Test _ensure_connected raises when not connected."""
        vna = KeysightP5007A(vna_config)
        with pytest.raises(RuntimeError, match="Not connected"):
            vna._ensure_connected()

    @pytest.mark.unit
    def test_ensure_connected_raises_when_inst_none(self, vna_config):
        """Test _ensure_connected raises when inst is None."""
        vna = KeysightP5007A(vna_config)
        vna._connected = True
        vna.inst = None
        with pytest.raises(RuntimeError, match="Not connected"):
            vna._ensure_connected()

    @pytest.mark.unit
    def test_send_command(self, vna_config):
        """Test sending SCPI command."""
        vna = KeysightP5007A(vna_config)
        mock_inst = MagicMock()
        vna.inst = mock_inst
        vna._connected = True

        vna._send_command("SENS1:FREQ:STAR 10000000")
        mock_inst.write.assert_called_with("SENS1:FREQ:STAR 10000000")

    @pytest.mark.unit
    def test_query(self, vna_config):
        """Test querying SCPI command."""
        vna = KeysightP5007A(vna_config)
        mock_inst = MagicMock()
        vna.inst = mock_inst
        vna._connected = True

        mock_inst.query.return_value = "OK\n"
        result = vna._query("SENS1:FREQ:STAR?")
        assert result == "OK\n"
        mock_inst.query.assert_called_with("SENS1:FREQ:STAR?")
