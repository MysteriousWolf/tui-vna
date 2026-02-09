"""
Configuration management with XDG-compliant persistent settings.

Provides cross-platform configuration storage following OS conventions:
- Linux/Unix: XDG_CONFIG_HOME (~/.config/hp-e5071b/)
- macOS: ~/Library/Application Support/hp-e5071b/
- Windows: %APPDATA%/hp-e5071b/
"""

import json
from dataclasses import asdict, dataclass
from pathlib import Path

from platformdirs import user_config_dir


@dataclass
class AppSettings:
    """Application settings that persist across sessions."""

    # Connection settings
    last_host: str = ""
    last_port: str = "inst0"
    host_history: list[str] = None
    port_history: list[str] = None

    # Measurement parameters
    freq_unit: str = "MHz"
    start_freq_mhz: float = 1.0
    stop_freq_mhz: float = 1100.0
    sweep_points: int = 601
    averaging_count: int = 16

    # Override flags
    set_freq_range: bool = False
    set_sweep_points: bool = True
    enable_averaging: bool = False
    set_averaging_count: bool = False

    # Output settings
    output_folder: str = "measurement"
    filename_prefix: str = "measurement"
    use_custom_filename: bool = False
    custom_filename: str = ""
    export_s11: bool = True
    export_s21: bool = True
    export_s12: bool = True
    export_s22: bool = True

    # Plot settings
    plot_s11: bool = True
    plot_s21: bool = True
    plot_s12: bool = True
    plot_s22: bool = True
    plot_type: str = "magnitude"  # "magnitude", "phase", "phase_raw"
    plot_backend: str = "terminal"  # "terminal", "image"

    def __post_init__(self):
        """Initialize mutable defaults."""
        if self.host_history is None:
            self.host_history = []
        if self.port_history is None:
            self.port_history = []


class SettingsManager:
    """Manages application settings with automatic persistence."""

    APP_NAME = "hp-e5071b"
    CONFIG_FILE = "settings.json"

    # Sane port defaults for VISA instruments
    DEFAULT_PORTS = ["inst0", "inst1", "inst2", "inst3", "hislip0", "gpib0,16"]
    MAX_PORT_HISTORY = 10
    MAX_HOST_HISTORY = 10

    def __init__(self):
        """Initialize settings manager."""
        self.config_dir = Path(user_config_dir(self.APP_NAME))
        self.config_file = self.config_dir / self.CONFIG_FILE
        self.settings = AppSettings()

    def load(self) -> AppSettings:
        """
        Load settings from disk.

        Returns:
            Loaded settings (or defaults if file doesn't exist)
        """
        if not self.config_file.exists():
            # Initialize with defaults including default ports
            self.settings.port_history = self.DEFAULT_PORTS.copy()
            return self.settings

        try:
            with open(self.config_file, encoding="utf-8") as f:
                data = json.load(f)

            # Convert dict to dataclass
            self.settings = AppSettings(**data)

            # Ensure port history contains defaults and is properly merged
            self._merge_port_history()

            return self.settings

        except (json.JSONDecodeError, TypeError, ValueError):
            # If config is corrupted, start fresh with defaults
            self.settings = AppSettings()
            self.settings.port_history = self.DEFAULT_PORTS.copy()
            return self.settings

    def save(self, settings: AppSettings | None = None) -> None:
        """
        Save settings to disk.

        Args:
            settings: Settings to save (uses current if None)
        """
        if settings is not None:
            self.settings = settings

        # Ensure config directory exists
        self.config_dir.mkdir(parents=True, exist_ok=True)

        # Merge port history before saving
        self._merge_port_history()

        # Convert dataclass to dict and save
        with open(self.config_file, "w", encoding="utf-8") as f:
            json.dump(asdict(self.settings), f, indent=2)

    def _merge_port_history(self) -> None:
        """Merge default ports with history, ensuring defaults are always present."""
        if not self.settings.port_history:
            self.settings.port_history = self.DEFAULT_PORTS.copy()
            return

        # Add defaults that aren't in history
        for default_port in self.DEFAULT_PORTS:
            if default_port not in self.settings.port_history:
                self.settings.port_history.append(default_port)

        # Limit history size
        if len(self.settings.port_history) > self.MAX_PORT_HISTORY:
            # Keep defaults + most recent custom ports
            custom_ports = [
                p for p in self.settings.port_history if p not in self.DEFAULT_PORTS
            ]
            self.settings.port_history = (
                self.DEFAULT_PORTS
                + custom_ports[-(self.MAX_PORT_HISTORY - len(self.DEFAULT_PORTS)) :]
            )

    def add_port_to_history(self, port: str) -> None:
        """
        Add a port to history (recent first, after defaults).

        Args:
            port: Port identifier to add
        """
        if not port or not port.strip():
            return

        port = port.strip()

        # Remove if already exists
        if port in self.settings.port_history:
            self.settings.port_history.remove(port)

        # If it's a default port, ensure it stays in default section
        if port in self.DEFAULT_PORTS:
            # Find insertion point (after other defaults)
            insert_idx = 0
            for i, p in enumerate(self.settings.port_history):
                if p in self.DEFAULT_PORTS:
                    insert_idx = i + 1
            self.settings.port_history.insert(insert_idx, port)
        else:
            # Custom port goes after defaults
            defaults_count = sum(
                1 for p in self.settings.port_history if p in self.DEFAULT_PORTS
            )
            self.settings.port_history.insert(defaults_count, port)

        # Limit history size
        self._merge_port_history()

    def get_port_options(self) -> list[tuple[str, str]]:
        """
        Get port options for dropdown (value, label).

        Returns:
            List of (port_id, display_label) tuples for Select widget
        """
        options = []

        for port in self.settings.port_history:
            if port in self.DEFAULT_PORTS:
                # Show default ports with label
                options.append((port, port))
            else:
                # Show custom ports with indicator
                options.append((port, f"{port} (recent)"))

        return options

    def add_host_to_history(self, host: str) -> None:
        """
        Add a host IP to history (most recent first).

        Args:
            host: Host IP address to add
        """
        if not host or not host.strip():
            return

        host = host.strip()

        # Remove if already exists
        if host in self.settings.host_history:
            self.settings.host_history.remove(host)

        # Add to beginning
        self.settings.host_history.insert(0, host)

        # Limit history size
        if len(self.settings.host_history) > self.MAX_HOST_HISTORY:
            self.settings.host_history = self.settings.host_history[
                : self.MAX_HOST_HISTORY
            ]

    def get_host_options(self) -> list[tuple[str, str]]:
        """
        Get host options for dropdown (value, label).

        Returns:
            List of (host_ip, display_label) tuples for Select widget
        """
        options = []

        for host in self.settings.host_history:
            options.append((host, host))

        return options
