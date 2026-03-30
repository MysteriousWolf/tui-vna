"""
Configuration management with XDG-compliant persistent settings.

Provides cross-platform configuration storage following OS conventions:
- Linux/Unix: XDG_CONFIG_HOME (~/.config/tina/)
- macOS: ~/Library/Application Support/tina/
- Windows: %APPDATA%/tina/

Settings are stored as YAML so the file is human-readable and comments
are preserved across saves.
"""

from dataclasses import asdict, dataclass, fields
from pathlib import Path

from platformdirs import user_config_dir
from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap

_yaml = YAML()
_yaml.default_flow_style = False
_yaml.width = 4096  # prevent unwanted line wrapping


def _build_commented_map(data: dict) -> CommentedMap:
    """Wrap *data* in a CommentedMap with human-readable section headers."""
    cm = CommentedMap(data)
    cm.yaml_set_start_comment(
        "TINA - Terminal UI Network Analyzer\n"
        "Settings file — edit the User settings section freely.\n"
    )
    cm.yaml_set_comment_before_after_key(
        "config_version",
        before="\nDo not modify config_version — it is used for future format migrations.\n",
    )
    cm.yaml_set_comment_before_after_key(
        "plot_backend",
        before=(
            "\n"
            "── User settings ────────────────────────────────────────────────────────\n"
            " Safe to edit manually. Changes take effect on the next launch.\n"
        ),
    )
    cm.yaml_set_comment_before_after_key(
        "last_host",
        before=(
            "\n"
            "── Machine-managed ──────────────────────────────────────────────────────\n"
            " Written automatically by tina.\n"
            " Manual edits are discouraged and may be overwritten on next launch.\n"
        ),
    )
    return cm


@dataclass
class AppSettings:
    """Application settings that persist across sessions."""

    # ── User settings (safe to edit) ─────────────────────────────────────────

    # Plot / display
    plot_backend: str = "terminal"  # "terminal" | "image"
    plot_type: str = "magnitude"  # "magnitude" | "phase" | "phase_raw" | "smith"
    tools_plot_type: str = "magnitude"  # "magnitude" | "phase" | "phase_raw"
    tools_trace: str = "S11"  # "S11" | "S21" | "S12" | "S22"
    tools_active_tool: str = ""  # "" | "cursor" | "distortion"
    cursor_marker_style: str = "▼"  # "▼" | "✕" | "○"
    plot_s11: bool = True
    plot_s21: bool = True
    plot_s12: bool = True
    plot_s22: bool = True

    # Measurement parameters
    freq_unit: str = "MHz"
    start_freq_mhz: float = 1.0
    stop_freq_mhz: float = 1100.0
    sweep_points: int = 601
    averaging_count: int = 16
    set_freq_range: bool = False
    set_sweep_points: bool = True
    enable_averaging: bool = False
    set_averaging_count: bool = False

    # Output / export
    output_folder: str = "measurement"
    filename_prefix: str = "measurement"
    use_custom_filename: bool = False
    custom_filename: str = ""
    export_s11: bool = True
    export_s21: bool = True
    export_s12: bool = True
    export_s22: bool = True

    # UI / status bar
    status_poll_interval: int = 5  # seconds; 0 = off
    debug_scpi: bool = False

    # ── Machine-managed (written by tina, do not edit) ────────────────────────

    last_host: str = ""
    last_port: str = "inst0"
    host_history: list = None
    port_history: list = None
    last_acknowledged_version: str = ""
    notified_prerelease: str = ""

    def __post_init__(self):
        """Initialize mutable defaults."""
        if self.host_history is None:
            self.host_history = []
        if self.port_history is None:
            self.port_history = []


class SettingsManager:
    """Manages application settings with automatic YAML persistence."""

    APP_NAME = "tina"
    CONFIG_FILE = "settings.yaml"
    CONFIG_VERSION = 1

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
        """Load settings from disk, returning defaults if the file is absent or corrupt."""
        if not self.config_file.exists():
            self.settings.port_history = self.DEFAULT_PORTS.copy()
            return self.settings

        try:
            with open(self.config_file, encoding="utf-8") as f:
                data = _yaml.load(f)

            if not isinstance(data, dict):
                raise ValueError("Unexpected YAML structure")

            file_version = data.get("config_version")
            if file_version is not None and file_version != self.CONFIG_VERSION:
                import warnings

                warnings.warn(
                    f"settings.yaml config_version={file_version} does not match "
                    f"expected {self.CONFIG_VERSION}; loading with best-effort defaults",
                    UserWarning,
                    stacklevel=2,
                )

            valid = {f.name for f in fields(AppSettings)}
            filtered = {k: v for k, v in data.items() if k in valid}
            self.settings = AppSettings(**filtered)
            self._merge_port_history()
            return self.settings

        except Exception:
            self.settings = AppSettings()
            self.settings.port_history = self.DEFAULT_PORTS.copy()
            return self.settings

    def save(self, settings: AppSettings | None = None) -> None:
        """Save settings to disk, preserving any existing comments."""
        if settings is not None:
            self.settings = settings

        self._merge_port_history()
        self.config_dir.mkdir(parents=True, exist_ok=True)

        data = {"config_version": self.CONFIG_VERSION, **asdict(self.settings)}

        if self.config_file.exists():
            try:
                with open(self.config_file, encoding="utf-8") as f:
                    existing = _yaml.load(f)
                if not isinstance(existing, dict):
                    existing = CommentedMap()
            except Exception:
                existing = CommentedMap()

            # Update values in place so comments are preserved
            for key, value in data.items():
                existing[key] = value

            with open(self.config_file, "w", encoding="utf-8") as f:
                _yaml.dump(existing, f)
        else:
            cm = _build_commented_map(data)
            with open(self.config_file, "w", encoding="utf-8") as f:
                _yaml.dump(cm, f)

    def _merge_port_history(self) -> None:
        """Merge default ports with history, ensuring defaults are always present."""
        if not self.settings.port_history:
            self.settings.port_history = self.DEFAULT_PORTS.copy()
            return

        for default_port in self.DEFAULT_PORTS:
            if default_port not in self.settings.port_history:
                self.settings.port_history.append(default_port)

        if len(self.settings.port_history) > self.MAX_PORT_HISTORY:
            custom_ports = [
                p for p in self.settings.port_history if p not in self.DEFAULT_PORTS
            ]
            self.settings.port_history = (
                self.DEFAULT_PORTS
                + custom_ports[-(self.MAX_PORT_HISTORY - len(self.DEFAULT_PORTS)) :]
            )

    def add_port_to_history(self, port: str) -> None:
        """Add a port to history (recent first, after defaults)."""
        if not port or not port.strip():
            return

        port = port.strip()

        if port in self.settings.port_history:
            self.settings.port_history.remove(port)

        if port in self.DEFAULT_PORTS:
            insert_idx = 0
            for i, p in enumerate(self.settings.port_history):
                if p in self.DEFAULT_PORTS:
                    insert_idx = i + 1
            self.settings.port_history.insert(insert_idx, port)
        else:
            defaults_count = sum(
                1 for p in self.settings.port_history if p in self.DEFAULT_PORTS
            )
            self.settings.port_history.insert(defaults_count, port)

        self._merge_port_history()

    def get_port_options(self) -> list[tuple[str, str]]:
        """Get port options for the dropdown as (value, label) tuples."""
        return [
            (port, port) if port in self.DEFAULT_PORTS else (port, f"{port} (recent)")
            for port in self.settings.port_history
        ]

    def add_host_to_history(self, host: str) -> None:
        """Add a host IP to history (most recent first)."""
        if not host or not host.strip():
            return

        host = host.strip()

        if host in self.settings.host_history:
            self.settings.host_history.remove(host)

        self.settings.host_history.insert(0, host)

        if len(self.settings.host_history) > self.MAX_HOST_HISTORY:
            self.settings.host_history = self.settings.host_history[
                : self.MAX_HOST_HISTORY
            ]

    def get_host_options(self) -> list[tuple[str, str]]:
        """Get host options for the dropdown as (value, label) tuples."""
        return [(host, host) for host in self.settings.host_history]
