"""Tests for configuration constants."""

import pytest

from tina.config import constants


@pytest.mark.unit
def test_frequency_defaults():
    """Test that frequency defaults are reasonable."""
    assert constants.DEFAULT_START_FREQ_HZ == 1e6
    assert constants.DEFAULT_STOP_FREQ_HZ == 1100e6
    assert constants.DEFAULT_START_FREQ_HZ < constants.DEFAULT_STOP_FREQ_HZ


@pytest.mark.unit
def test_sweep_defaults():
    """Test sweep parameter defaults."""
    assert constants.DEFAULT_SWEEP_POINTS == 601
    assert constants.DEFAULT_AVERAGING_COUNT == 16
    assert constants.DEFAULT_SWEEP_POINTS > 0
    assert constants.DEFAULT_AVERAGING_COUNT > 0


@pytest.mark.unit
def test_timeout_values():
    """Test that timeout values are positive."""
    assert constants.DEFAULT_VISA_TIMEOUT_MS > 0
    assert constants.COMMAND_TIMEOUT_MS > 0
    assert constants.SOCKET_TIMEOUT_SEC > 0
    assert constants.OPERATION_TIMEOUT_SEC > 0
    assert constants.SWEEP_TIMEOUT_SEC > 0
    assert constants.PARAM_SETUP_TIMEOUT_SEC > 0


@pytest.mark.unit
def test_reference_impedance():
    """Test reference impedance default."""
    assert constants.DEFAULT_REFERENCE_IMPEDANCE == 50.0


@pytest.mark.unit
def test_log_epsilon():
    """Test that log epsilon is small positive number."""
    assert 0 < constants.LOG_EPSILON < 1e-10


@pytest.mark.unit
def test_plot_settings():
    """Test plot setting defaults."""
    assert constants.DEFAULT_PLOT_DPI > 0
    assert constants.DEFAULT_PLOT_RENDER_SCALE > 0
    assert 0 <= constants.DEFAULT_OUTLIER_PERCENTILE <= 100
    assert 0 <= constants.DEFAULT_SAFETY_MARGIN < 1
    assert constants.DEFAULT_TERMINAL_PLOT_HEIGHT > 0


@pytest.mark.unit
def test_sparam_theme_keys():
    """Test S-parameter theme mapping."""
    assert "S11" in constants.SPARAM_THEME_KEYS
    assert "S21" in constants.SPARAM_THEME_KEYS
    assert "S12" in constants.SPARAM_THEME_KEYS
    assert "S22" in constants.SPARAM_THEME_KEYS
    assert len(constants.SPARAM_THEME_KEYS) == 4


@pytest.mark.unit
def test_sparam_fallback_colors():
    """Test S-parameter fallback colors are valid hex."""
    for param, color in constants.SPARAM_FALLBACK_COLORS.items():
        assert param in ["S11", "S21", "S12", "S22"]
        assert color.startswith("#")
        assert len(color) == 7  # #RRGGBB format


@pytest.mark.unit
def test_default_colors():
    """Test default color definitions are valid hex."""
    assert constants.TRACE_COLOR_DEFAULT.startswith("#")
    assert constants.DEFAULT_FOREGROUND_COLOR.startswith("#")
    assert constants.DEFAULT_BACKGROUND_COLOR.startswith("#")
    assert constants.DEFAULT_GRID_COLOR.startswith("#")


@pytest.mark.unit
def test_worker_settings():
    """Test worker thread settings."""
    assert constants.MESSAGE_POLL_INTERVAL_SEC > 0
    assert constants.WORKER_SHUTDOWN_TIMEOUT_SEC > 0


@pytest.mark.unit
def test_default_visa_ports():
    """Test default VISA ports list."""
    assert len(constants.DEFAULT_VISA_PORTS) > 0
    assert "inst0" in constants.DEFAULT_VISA_PORTS
    assert all(isinstance(port, str) for port in constants.DEFAULT_VISA_PORTS)


@pytest.mark.unit
def test_history_limits():
    """Test history size limits."""
    assert constants.MAX_HOST_HISTORY > 0
    assert constants.MAX_PORT_HISTORY > 0


@pytest.mark.unit
def test_freq_unit_conversions():
    """Test frequency unit conversion factors."""
    assert constants.FREQ_UNIT_CONVERSIONS["Hz"] == 1.0
    assert constants.FREQ_UNIT_CONVERSIONS["kHz"] == 1e3
    assert constants.FREQ_UNIT_CONVERSIONS["MHz"] == 1e6
    assert constants.FREQ_UNIT_CONVERSIONS["GHz"] == 1e9


@pytest.mark.unit
def test_visa_connection_params():
    """Test VISA connection parameter defaults."""
    assert constants.DEFAULT_VISA_PROTOCOL == "TCPIP0"
    assert constants.DEFAULT_VISA_SUFFIX == "INSTR"
    assert constants.DEFAULT_VISA_PORT == "inst0"


@pytest.mark.unit
def test_port_numbers():
    """Test port numbers for connection testing."""
    assert constants.VXI11_PORTMAPPER_PORT == 111
    assert constants.SCPI_RAW_PORT == 5025
