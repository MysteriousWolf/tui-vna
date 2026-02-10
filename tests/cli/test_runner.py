"""Tests for CLI runner."""

from tina.cli.runner import create_vna_config
from tina.config.settings import AppSettings
from tina.drivers import VNAConfig


class TestCreateVNAConfig:
    """Test creating VNA config from settings."""

    def test_create_vna_config_from_defaults(self):
        """Test creating VNA config from default settings."""
        settings = AppSettings(last_host="192.168.1.100")
        config = create_vna_config(settings)

        assert isinstance(config, VNAConfig)
        assert config.host == "192.168.1.100"
        assert config.port == "inst0"

    def test_create_vna_config_with_custom_settings(self):
        """Test creating VNA config with custom settings."""
        settings = AppSettings(
            last_host="10.0.0.50",
            last_port="inst1",
            start_freq_mhz=100.0,
            stop_freq_mhz=2000.0,
            sweep_points=1001,
        )
        config = create_vna_config(settings)

        assert config.host == "10.0.0.50"
        assert config.port == "inst1"
        assert config.start_freq_hz == 100.0e6  # MHz to Hz
        assert config.stop_freq_hz == 2000.0e6  # MHz to Hz
        assert config.sweep_points == 1001

    def test_create_vna_config_frequency_conversion(self):
        """Test that frequencies are correctly converted from MHz to Hz."""
        settings = AppSettings(
            last_host="192.168.1.100",
            start_freq_mhz=1.0,
            stop_freq_mhz=1100.0,
        )
        config = create_vna_config(settings)

        assert config.start_freq_hz == 1.0e6
        assert config.stop_freq_hz == 1100.0e6

    def test_create_vna_config_override_flags(self):
        """Test that override flags are correctly passed."""
        settings = AppSettings(
            last_host="192.168.1.100",
            set_freq_range=True,
            set_sweep_points=True,
            enable_averaging=True,
            set_averaging_count=True,
        )
        config = create_vna_config(settings)

        assert config.set_freq_range is True
        assert config.set_sweep_points is True
        assert config.enable_averaging is True
        assert config.set_averaging_count is True

    def test_create_vna_config_averaging_settings(self):
        """Test that averaging settings are correctly passed."""
        settings = AppSettings(
            last_host="192.168.1.100",
            enable_averaging=True,
            averaging_count=32,
        )
        config = create_vna_config(settings)

        assert config.enable_averaging is True
        assert config.averaging_count == 32

    def test_create_vna_config_different_frequencies(self):
        """Test config creation with various frequency ranges."""
        test_cases = [
            (10.0, 100.0),  # Low frequencies
            (1000.0, 5000.0),  # Mid frequencies
            (10000.0, 20000.0),  # High frequencies
        ]

        for start_mhz, stop_mhz in test_cases:
            settings = AppSettings(
                last_host="192.168.1.100",
                start_freq_mhz=start_mhz,
                stop_freq_mhz=stop_mhz,
            )
            config = create_vna_config(settings)

            assert config.start_freq_hz == start_mhz * 1e6
            assert config.stop_freq_hz == stop_mhz * 1e6

    def test_create_vna_config_different_sweep_points(self):
        """Test config creation with various sweep point counts."""
        for points in [101, 201, 401, 601, 1001, 1601]:
            settings = AppSettings(last_host="192.168.1.100", sweep_points=points)
            config = create_vna_config(settings)

            assert config.sweep_points == points
