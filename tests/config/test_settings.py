"""Tests for settings persistence and management."""

import json
from unittest.mock import patch

import pytest

from tina.config.settings import AppSettings, SettingsManager


@pytest.fixture
def temp_config_dir(tmp_path):
    """Create temporary config directory."""
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    return config_dir


@pytest.fixture
def settings_manager(temp_config_dir):
    """Create settings manager with temporary config directory."""
    with patch(
        "tina.config.settings.user_config_dir", return_value=str(temp_config_dir)
    ):
        manager = SettingsManager()
        yield manager


@pytest.mark.unit
class TestAppSettings:
    """Test AppSettings dataclass."""

    def test_default_initialization(self):
        """Test default settings initialization."""
        settings = AppSettings()
        assert settings.last_host == ""
        assert settings.last_port == "inst0"
        assert settings.host_history == []
        assert settings.port_history == []
        assert settings.freq_unit == "MHz"
        assert settings.start_freq_mhz == 1.0
        assert settings.stop_freq_mhz == 1100.0

    def test_custom_initialization(self):
        """Test custom settings initialization."""
        settings = AppSettings(
            last_host="192.168.1.100",
            last_port="inst1",
            sweep_points=1001,
        )
        assert settings.last_host == "192.168.1.100"
        assert settings.last_port == "inst1"
        assert settings.sweep_points == 1001

    def test_post_init_mutable_defaults(self):
        """Test that mutable defaults are properly initialized."""
        settings1 = AppSettings()
        settings2 = AppSettings()

        settings1.host_history.append("test")
        assert "test" in settings1.host_history
        assert "test" not in settings2.host_history

    def test_export_flags(self):
        """Test export flag defaults."""
        settings = AppSettings()
        assert settings.export_s11 is True
        assert settings.export_s21 is True
        assert settings.export_s12 is True
        assert settings.export_s22 is True

    def test_plot_flags(self):
        """Test plot flag defaults."""
        settings = AppSettings()
        assert settings.plot_s11 is True
        assert settings.plot_s21 is True
        assert settings.plot_s12 is True
        assert settings.plot_s22 is True
        assert settings.plot_type == "magnitude"
        assert settings.plot_backend == "terminal"


@pytest.mark.unit
class TestSettingsManager:
    """Test SettingsManager functionality."""

    def test_initialization(self, settings_manager):
        """Test manager initialization."""
        assert settings_manager.config_dir.exists()
        assert isinstance(settings_manager.settings, AppSettings)

    def test_load_creates_defaults(self, settings_manager):
        """Test loading when config file doesn't exist."""
        settings = settings_manager.load()
        assert isinstance(settings, AppSettings)
        assert "inst0" in settings.port_history
        assert set(SettingsManager.DEFAULT_PORTS).issubset(set(settings.port_history))

    def test_save_creates_config_file(self, settings_manager):
        """Test saving creates config file."""
        settings_manager.settings.last_host = "192.168.1.100"
        settings_manager.save()

        assert settings_manager.config_file.exists()

        with open(settings_manager.config_file) as f:
            data = json.load(f)

        assert data["last_host"] == "192.168.1.100"

    def test_save_load_roundtrip(self, settings_manager):
        """Test save/load preserves data."""
        settings_manager.settings.last_host = "192.168.1.100"
        settings_manager.settings.last_port = "inst2"
        settings_manager.settings.sweep_points = 1001
        settings_manager.save()

        # Load in new manager instance
        with patch(
            "tina.config.settings.user_config_dir",
            return_value=str(settings_manager.config_dir),
        ):
            new_manager = SettingsManager()
            loaded = new_manager.load()

        assert loaded.last_host == "192.168.1.100"
        assert loaded.last_port == "inst2"
        assert loaded.sweep_points == 1001

    def test_corrupted_config_returns_defaults(self, settings_manager):
        """Test that corrupted config returns defaults."""
        # Write invalid JSON
        settings_manager.config_file.write_text("{ invalid json }")

        settings = settings_manager.load()
        assert isinstance(settings, AppSettings)
        assert settings.last_host == ""

    def test_merge_port_history_adds_defaults(self, settings_manager):
        """Test that default ports are always present."""
        settings_manager.settings.port_history = ["custom_port"]
        settings_manager._merge_port_history()

        for default in SettingsManager.DEFAULT_PORTS:
            assert default in settings_manager.settings.port_history

    def test_merge_port_history_limits_size(self, settings_manager):
        """Test that port history respects max size."""
        # Add many custom ports
        custom_ports = [f"custom{i}" for i in range(20)]
        settings_manager.settings.port_history = (
            SettingsManager.DEFAULT_PORTS.copy() + custom_ports
        )
        settings_manager._merge_port_history()

        assert (
            len(settings_manager.settings.port_history)
            <= SettingsManager.MAX_PORT_HISTORY
        )

    def test_add_port_to_history_new_custom(self, settings_manager):
        """Test adding new custom port."""
        settings_manager.settings.port_history = SettingsManager.DEFAULT_PORTS.copy()
        settings_manager.add_port_to_history("custom_port")

        assert "custom_port" in settings_manager.settings.port_history
        # Custom port should come after defaults
        defaults_count = len(SettingsManager.DEFAULT_PORTS)
        custom_idx = settings_manager.settings.port_history.index("custom_port")
        assert custom_idx >= defaults_count

    def test_add_port_to_history_existing_default(self, settings_manager):
        """Test adding existing default port moves it."""
        settings_manager.settings.port_history = SettingsManager.DEFAULT_PORTS.copy()
        original_length = len(settings_manager.settings.port_history)

        settings_manager.add_port_to_history("inst0")

        # Should not duplicate
        assert len(settings_manager.settings.port_history) == original_length
        assert settings_manager.settings.port_history.count("inst0") == 1

    def test_add_port_to_history_removes_duplicates(self, settings_manager):
        """Test that adding duplicate port removes old entry."""
        settings_manager.settings.port_history = ["inst0", "custom1", "custom2"]
        settings_manager.add_port_to_history("custom1")

        assert settings_manager.settings.port_history.count("custom1") == 1

    def test_add_port_to_history_ignores_empty(self, settings_manager):
        """Test that empty/whitespace ports are ignored."""
        settings_manager.settings.port_history = ["inst0"]
        original_length = len(settings_manager.settings.port_history)

        settings_manager.add_port_to_history("")
        settings_manager.add_port_to_history("   ")

        assert len(settings_manager.settings.port_history) == original_length

    def test_get_port_options(self, settings_manager):
        """Test getting port options for UI."""
        settings_manager.settings.port_history = ["inst0", "inst1", "custom_port"]
        options = settings_manager.get_port_options()

        assert len(options) >= 3
        assert all(isinstance(opt, tuple) and len(opt) == 2 for opt in options)

        # Check that custom ports are labeled
        custom_options = [opt for opt in options if "custom_port" in opt[0]]
        assert len(custom_options) == 1
        assert "(recent)" in custom_options[0][1]

    def test_add_host_to_history_new(self, settings_manager):
        """Test adding new host to history."""
        settings_manager.add_host_to_history("192.168.1.100")

        assert "192.168.1.100" in settings_manager.settings.host_history
        assert settings_manager.settings.host_history[0] == "192.168.1.100"

    def test_add_host_to_history_existing(self, settings_manager):
        """Test adding existing host moves it to front."""
        settings_manager.settings.host_history = ["192.168.1.100", "192.168.1.101"]
        settings_manager.add_host_to_history("192.168.1.101")

        assert settings_manager.settings.host_history[0] == "192.168.1.101"
        assert len(settings_manager.settings.host_history) == 2

    def test_add_host_to_history_limits_size(self, settings_manager):
        """Test that host history respects max size."""
        # Add more hosts than limit
        for i in range(SettingsManager.MAX_HOST_HISTORY + 5):
            settings_manager.add_host_to_history(f"192.168.1.{i}")

        assert (
            len(settings_manager.settings.host_history)
            == SettingsManager.MAX_HOST_HISTORY
        )

    def test_add_host_to_history_ignores_empty(self, settings_manager):
        """Test that empty/whitespace hosts are ignored."""
        settings_manager.add_host_to_history("")
        settings_manager.add_host_to_history("   ")

        assert len(settings_manager.settings.host_history) == 0

    def test_get_host_options(self, settings_manager):
        """Test getting host options for UI."""
        settings_manager.settings.host_history = ["192.168.1.100", "192.168.1.101"]
        options = settings_manager.get_host_options()

        assert len(options) == 2
        assert all(isinstance(opt, tuple) and len(opt) == 2 for opt in options)
        assert options[0] == ("192.168.1.100", "192.168.1.100")

    def test_settings_persistence_with_history(self, settings_manager):
        """Test that history is properly persisted."""
        settings_manager.add_host_to_history("192.168.1.100")
        settings_manager.add_port_to_history("custom_port")
        settings_manager.save()

        # Load in new instance
        with patch(
            "tina.config.settings.user_config_dir",
            return_value=str(settings_manager.config_dir),
        ):
            new_manager = SettingsManager()
            loaded = new_manager.load()

        assert "192.168.1.100" in loaded.host_history
        assert "custom_port" in loaded.port_history

    def test_override_flags(self, settings_manager):
        """Test override flag settings."""
        settings_manager.settings.set_freq_range = True
        settings_manager.settings.enable_averaging = True
        settings_manager.save()

        loaded = settings_manager.load()
        assert loaded.set_freq_range is True
        assert loaded.enable_averaging is True

    def test_output_settings(self, settings_manager):
        """Test output-related settings."""
        settings_manager.settings.output_folder = "custom_output"
        settings_manager.settings.filename_prefix = "my_measurement"
        settings_manager.settings.use_custom_filename = True
        settings_manager.save()

        loaded = settings_manager.load()
        assert loaded.output_folder == "custom_output"
        assert loaded.filename_prefix == "my_measurement"
        assert loaded.use_custom_filename is True

    def test_plot_settings_persistence(self, settings_manager):
        """Test plot settings are persisted."""
        settings_manager.settings.plot_type = "phase"
        settings_manager.settings.plot_backend = "image"
        settings_manager.settings.plot_s11 = False
        settings_manager.save()

        loaded = settings_manager.load()
        assert loaded.plot_type == "phase"
        assert loaded.plot_backend == "image"
        assert loaded.plot_s11 is False
