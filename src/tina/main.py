"""
TINA - Terminal UI Network Analyzer
"""

import asyncio
import importlib.resources
import os
import platform
import queue
import subprocess
import sys
import tkinter as tk
from pathlib import Path
from tkinter import filedialog

import matplotlib
import numpy as np
from textual import on, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical
from textual.widgets import (
    Button,
    Checkbox,
    Header,
    Input,
    Label,
    Markdown,
    ProgressBar,
    RadioSet,
    RichLog,
    Select,
    Static,
    TabbedContent,
    TabPane,
    TextArea,
)

# Set matplotlib to non-interactive backend
matplotlib.use("Agg")

from . import __version__
from .config.settings import SettingsManager
from .drivers import VNAConfig
from .export import (
    DEFAULT_TEMPLATE_TAGS,
    PATH_INVALID_CHARS,
    CsvExporter,
    build_image_export_metadata,
    embed_png_metadata,
    embed_svg_metadata,
    read_png_metadata,
    read_svg_metadata,
    render_template,
)
from .gui.components import (
    StatusFooter,
)
from .gui.modals import HelpScreen, build_update_screen, build_welcome_screen
from .gui.modals.help import (
    TEXTUAL_IMAGE_AVAILABLE,
    ImageWidget,
)
from .gui.plotting import (
    calculate_plot_range_with_outlier_filtering,
    create_matplotlib_plot,
    create_smith_chart,
    get_plot_colors,
    get_terminal_font,
    truncate_path_intelligently,
    unwrap_phase,
)
from .gui.providers import (
    CursorMarkerProvider,
    PlotBackendProvider,
    SetupImportProvider,
    StatusPollProvider,
)
from .gui.tabs import (
    apply_tool_ui,
    compose_log_tab,
    compose_measurement_tab,
    compose_setup_tab,
    compose_tools_tab,
    delayed_redraw_tools_plot,
    delayed_tools_refresh,
    get_distortion_comp_enabled,
    get_tools_trace,
    log_logic,
    rebuild_tools_params,
    refresh_tools_plot,
    run_tools_computation,
    set_active_tool,
    setup_logic,
    tools_logic,
)
from .utils import TouchstoneExporter
from .utils.update_checker import (
    fetch_test_update_data,
    get_changelogs_since,
    get_update_info,
)
from .worker import (
    LogMessage,
    MeasurementResult,
    MeasurementWorker,
    MessageType,
    ParamsResult,
    ProgressUpdate,
    StatusResult,
)


class VNAApp(App):
    """TINA - Terminal UI Network Analyzer"""

    CSS_PATH = [
        "gui/styles/core.tcss",
        "gui/styles/plots.tcss",
        "gui/styles/setup_tab.tcss",
        "gui/styles/measurement_tab.tcss",
        "gui/styles/tools_tab.tcss",
        "gui/styles/log_tab.tcss",
    ]

    COMMANDS = App.COMMANDS | {
        StatusPollProvider,
        PlotBackendProvider,
        CursorMarkerProvider,
        SetupImportProvider,
    }

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("ctrl+d", "toggle_debug_scpi", "SCPI Debug", show=False),
    ]

    TITLE = "TINA - Terminal UI Network Analyzer"

    def __init__(
        self,
        test_updates: bool = False,
        dev_mode: bool = False,
        migration_message: str | None = None,
    ):
        """
        Initialize application state, configuration, worker, timers, and temporary plot directory.

        Sets up settings (via SettingsManager), measurement worker, VNA configuration, UI-related flags and caches, timers used for polling and debouncing, tools tab state, a temporary directory for rendered plot images, and detects terminal font/program for consistent rendering.

        Parameters:
            test_updates (bool): When True, enable test-mode update behavior used by the background update checker (shows test/welcome notifications).
            dev_mode (bool): When True, suppress the post-update welcome popup and skip persisting the version acknowledgement to disk.
            migration_message (str | None): If set, logged at startup to inform the user that legacy settings were migrated.
        """
        super().__init__()

        self._test_updates = test_updates
        self._dev_mode = dev_mode
        self._migration_message = migration_message
        self.settings_manager = SettingsManager()
        self.settings = self.settings_manager.load()
        self.worker = MeasurementWorker()
        self.config = VNAConfig()
        self.connected = False
        self.measuring = False
        self.last_measurement = None  # Store last measurement data
        self.measurement_notes = ""  # Store raw markdown notes for current measurement
        self.last_output_path = None  # Store last output file path
        self.last_plot_path = None  # Store last plot image path
        self.log_messages = []  # Store all log messages for filtering
        self._message_check_timer = None  # Timer for checking worker messages
        self._resize_timer = None  # Timer for debouncing resize events
        self._path_update_timer = None  # Timer for updating path label on resize
        self._poll_timer = None  # Timer for status bar polling
        self._status_poll_in_flight = False  # True while a STATUS_POLL is outstanding
        self._debug_scpi = self.settings.debug_scpi
        self._filename_template_validation = None
        self._folder_template_validation = None
        self._minimal_export_mode = False

        # Tools tab state
        self._tools_cursor1_hz: float | None = None
        self._tools_cursor2_hz: float | None = None
        self._tools_resize_timer = None
        self._tools_input_timer = None  # Timer for debouncing cursor input changes
        self._template_input_timer = None

        # Create temporary directory for plot images
        self.plot_temp_dir = Path("/tmp/tui-vna-plots")
        self.plot_temp_dir.mkdir(parents=True, exist_ok=True)

        # Detect terminal and font once at boot
        self.terminal_font, self.terminal_font_size = get_terminal_font()
        self.terminal_program = os.getenv("TERM_PROGRAM", "unknown")

    def compose(self) -> ComposeResult:
        """Create child widgets."""
        yield Header()

        with TabbedContent(id="content"):
            with TabPane("Setup", id="tab_measure"):
                yield from compose_setup_tab(self)

            with TabPane("Measurement", id="tab_results"):
                yield from compose_measurement_tab(self)

            with TabPane("Tools", id="tab_tools"):
                yield from compose_tools_tab(self)

            with TabPane("Log", id="tab_log"):
                yield from compose_log_tab()

        yield Static("", id="footer_separator")

        # Controls panel with progress bar (left) and buttons (right)
        with Container(id="controls_panel"):
            with Horizontal(id="action_bar"):
                with Vertical(id="progress_container"):
                    yield Label("Disconnected", id="progress_label")
                    yield ProgressBar(id="progress_bar")
                yield Button(
                    "📡\nConnect", id="btn_connect", variant="primary", flat=True
                )
                yield Button(
                    "🔍\nRead Parameters",
                    id="btn_read_params",
                    variant="default",
                    disabled=True,
                    flat=True,
                )
                yield Button(
                    "📊\nMeasure",
                    id="btn_measure",
                    variant="success",
                    disabled=True,
                    flat=True,
                )
                yield Button(
                    "📁\nImport File",
                    id="btn_import_results",
                    variant="warning",
                    flat=True,
                )

        yield StatusFooter()

    def on_mount(self) -> None:
        """
        Initialize application UI and background services when the app is mounted.

        Performs startup initialization: updates window title and footer debug state, initializes progress bar and plot-type options, applies tool UI state, starts the measurement worker and its message polling, and schedules a background update check once the UI is ready.
        """
        self._update_title()
        self.query_one(StatusFooter).set_debug_mode(self._debug_scpi, connected=False)
        self.call_after_refresh(self._log_startup)
        self.call_after_refresh(setup_logic.mount_setup_autocompletes, self)
        self.call_after_refresh(setup_logic.refresh_export_template_validation, self)
        self.call_after_refresh(self._load_measurement_notes_into_editor)
        self.call_after_refresh(self._refresh_measurement_notes_preview)
        self.call_after_refresh(self._refresh_export_button_labels)
        # Initialize progress bar to 0 (not indeterminate)
        self.query_one("#progress_bar", ProgressBar).update(total=100, progress=0)
        # Initialize plot-type options based on backend
        self._update_plot_type_options()
        # Apply active tool UI state at startup
        self._apply_tool_ui()
        # Start worker thread
        self.worker.start()
        # Start message polling
        self._start_message_polling()
        # Check for updates in background (after UI is ready)
        self.call_after_refresh(self._check_for_updates)

    def _log_startup(self) -> None:
        """Log startup message after UI is ready."""
        self.log_message(f"TINA v{__version__} ready. Connect to start.", "info")
        if self._migration_message:
            self.log_message(self._migration_message, "info")
        # Log detected terminal and font info
        font_info = self.terminal_font
        if self.terminal_font_size:
            font_info += f" {self.terminal_font_size}pt"
        self.log_message(
            f"Detected terminal: {self.terminal_program} | Font: {font_info}", "debug"
        )

    @work
    async def _check_for_updates(self) -> None:
        """Check GitHub for newer releases and show modals as appropriate."""
        loop = asyncio.get_event_loop()

        # --- Test mode: show all three modals with lorem ipsum content -------
        if self._test_updates:
            welcome_cl, stable_fake, pre_fake = await loop.run_in_executor(
                None, fetch_test_update_data, __version__
            )
            await self.push_screen_wait(build_welcome_screen(__version__, welcome_cl))
            await self.push_screen_wait(build_update_screen(stable_fake))
            await self.push_screen_wait(build_update_screen(pre_fake))
            return

        # --- Post-update welcome (shown once per version after upgrading) ---
        # Skipped entirely in dev mode to avoid polluting the persistent state
        # file with dev-build version numbers, which would suppress the popup
        # for real users after a genuine update.
        last_ack = self.settings.last_acknowledged_version
        if not self._dev_mode:
            if last_ack and last_ack != __version__:
                changelog = await loop.run_in_executor(
                    None, get_changelogs_since, last_ack, __version__
                )
                await self.push_screen_wait(
                    build_welcome_screen(__version__, changelog)
                )
                self.settings.last_acknowledged_version = __version__
                self.settings_manager.save(self.settings)
            elif not last_ack:
                # First run — just record the version silently, no welcome shown
                self.settings.last_acknowledged_version = __version__
                self.settings_manager.save(self.settings)

        # --- Check for newer releases ---
        stable, pre = await loop.run_in_executor(None, get_update_info, __version__)

        if stable:
            await self.push_screen_wait(build_update_screen(stable))
        elif pre:
            if self.settings.notified_prerelease != pre.version:
                await self.push_screen_wait(build_update_screen(pre))
                if not self._dev_mode:
                    self.settings.notified_prerelease = pre.version
                    self.settings_manager.save(self.settings)

    def _update_plot_type_options(self) -> None:
        """Update plot type dropdown options based on selected backend."""
        plot_backend = self.settings.plot_backend
        plot_type_select = self.query_one("#select_plot_type", Select)
        current_type = plot_type_select.value

        if plot_backend == "terminal":
            # Text-based backend: magnitude, phase, phase_raw
            new_options = [
                ("Magnitude", "magnitude"),
                ("Phase", "phase"),
                ("Phase Raw", "phase_raw"),
            ]
        else:  # image backend
            # Image-based backend: magnitude, phase, phase_raw, smith
            new_options = [
                ("Magnitude", "magnitude"),
                ("Phase", "phase"),
                ("Phase Raw", "phase_raw"),
                ("Smith Chart", "smith"),
            ]

        # Update options
        plot_type_select.set_options(new_options)

        # Try to preserve the current selection if it's still valid
        valid_values = [opt[1] for opt in new_options]
        if current_type in valid_values:
            plot_type_select.value = current_type
        else:
            # Default to magnitude if current type not available
            plot_type_select.value = "magnitude"

    def on_app_theme_changed(self) -> None:
        """
        Handle theme change by clearing cached styles and updating UI components.

        Clears the cached style map, re-renders the log using the updated theme colors, and—if a measurement is loaded—schedules refreshed tools and results plots to run after the next render cycle.
        """
        self._cached_style_map = None
        log_logic.refresh_log_display(self)
        if self.last_measurement is not None:
            self.call_after_refresh(self._refresh_tools_plot)
            self.call_after_refresh(self._refresh_results_plot)

    def on_unmount(self) -> None:
        """
        Perform shutdown tasks for the application.

        Saves current settings and attempts to stop the background measurement worker, waiting up to 5.0 seconds for it to terminate.
        """
        # Save settings before exit
        self._save_current_settings()
        # Stop worker thread gracefully
        if self.worker:
            self.worker.stop(timeout=5.0)

    def _save_current_settings(self) -> None:
        """Save current UI state to settings."""
        try:
            # Connection settings
            self.settings.last_host = self.query_one("#input_host", Input).value.strip()
            self.settings.last_port = (
                self.query_one("#input_port", Input).value.strip() or "inst0"
            )

            # Measurement parameters
            freq_unit_value = self.query_one("#select_freq_unit", Select).value
            if isinstance(freq_unit_value, str):
                self.settings.freq_unit = freq_unit_value
            self.settings.start_freq_mhz = float(
                self.query_one("#input_start_freq", Input).value or "1.0"
            )
            self.settings.stop_freq_mhz = float(
                self.query_one("#input_stop_freq", Input).value or "1100.0"
            )
            self.settings.sweep_points = int(
                self.query_one("#input_points", Input).value or "601"
            )
            self.settings.averaging_count = int(
                self.query_one("#input_avg_count", Input).value or "16"
            )

            # Override flags
            self.settings.set_freq_range = self.query_one(
                "#check_set_freq", Checkbox
            ).value
            self.settings.set_sweep_points = self.query_one(
                "#check_set_points", Checkbox
            ).value
            self.settings.enable_averaging = self.query_one(
                "#check_averaging", Checkbox
            ).value
            self.settings.set_averaging_count = self.query_one(
                "#check_set_avg_count", Checkbox
            ).value

            # Output settings
            self.settings.output_folder = self.query_one(
                "#input_output_folder", Input
            ).value
            self.settings.folder_template = self.settings.output_folder
            self.settings.filename_prefix = self.query_one(
                "#input_filename_prefix", Input
            ).value
            self.settings.filename_template = self.settings.filename_prefix
            self.settings.export_s11 = self.query_one(
                "#check_export_s11", Checkbox
            ).value
            self.settings.export_s21 = self.query_one(
                "#check_export_s21", Checkbox
            ).value
            self.settings.export_s12 = self.query_one(
                "#check_export_s12", Checkbox
            ).value
            self.settings.export_s22 = self.query_one(
                "#check_export_s22", Checkbox
            ).value
            self.settings.export_bundle_s2p = self.query_one(
                "#check_export_bundle_s2p", Checkbox
            ).value
            self.settings.export_bundle_csv = self.query_one(
                "#check_export_bundle_csv", Checkbox
            ).value
            self.settings.export_bundle_png = self.query_one(
                "#check_export_bundle_png", Checkbox
            ).value
            self.settings.export_bundle_svg = self.query_one(
                "#check_export_bundle_svg", Checkbox
            ).value
            self.settings_manager.touch_template_history(
                "filename_template_history",
                self.settings.filename_template,
            )
            self.settings_manager.touch_template_history(
                "folder_template_history",
                self.settings.folder_template,
            )

            # Plot settings
            self.settings.plot_s11 = self.query_one("#check_plot_s11", Checkbox).value
            self.settings.plot_s21 = self.query_one("#check_plot_s21", Checkbox).value
            self.settings.plot_s12 = self.query_one("#check_plot_s12", Checkbox).value
            self.settings.plot_s22 = self.query_one("#check_plot_s22", Checkbox).value
            plot_type_value = self.query_one("#select_plot_type", Select).value
            if isinstance(plot_type_value, str):
                self.settings.plot_type = plot_type_value

            # Tools tab settings
            self.settings.tools_trace = self._get_tools_trace()
            try:
                tools_plot_type_value = self.query_one(
                    "#select_tools_plot_type", Select
                ).value
                if isinstance(tools_plot_type_value, str):
                    self.settings.tools_plot_type = tools_plot_type_value
            except Exception:
                pass

            # Save to disk
            self.settings_manager.save(self.settings)
        except Exception:
            # Silently fail during shutdown to avoid errors
            pass

    def _build_touchstone_export_metadata(
        self,
        *,
        exported_traces: list[str],
        output_path: str | None = None,
    ) -> dict[str, object]:
        """Build machine-readable metadata for Touchstone export and recovery."""
        metadata: dict[str, object] = {
            "setup": {
                "host": self.settings.last_host,
                "port": self.settings.last_port,
                "freq_unit": self.settings.freq_unit,
                "start_freq_mhz": self.settings.start_freq_mhz,
                "stop_freq_mhz": self.settings.stop_freq_mhz,
                "sweep_points": self.settings.sweep_points,
                "averaging_count": self.settings.averaging_count,
                "set_freq_range": self.settings.set_freq_range,
                "set_sweep_points": self.settings.set_sweep_points,
                "enable_averaging": self.settings.enable_averaging,
                "set_averaging_count": self.settings.set_averaging_count,
                "output_folder": self.settings.output_folder,
                "filename_template": self.settings.filename_template,
                "folder_template": self.settings.folder_template,
                "export_bundle_s2p": self.settings.export_bundle_s2p,
                "export_bundle_csv": self.settings.export_bundle_csv,
                "export_bundle_png": self.settings.export_bundle_png,
                "export_bundle_svg": self.settings.export_bundle_svg,
                "export_s11": self.settings.export_s11,
                "export_s21": self.settings.export_s21,
                "export_s12": self.settings.export_s12,
                "export_s22": self.settings.export_s22,
            },
            "measurement": {
                "plot_type": self.settings.plot_type,
                "plot_s11": self.settings.plot_s11,
                "plot_s21": self.settings.plot_s21,
                "plot_s12": self.settings.plot_s12,
                "plot_s22": self.settings.plot_s22,
                "exported_traces": exported_traces,
                "notes_present": bool(self.measurement_notes.strip()),
            },
            "tools": {
                "trace": self.settings.tools_trace,
                "plot_type": self.settings.tools_plot_type,
                "active_tool": self.settings.tools_active_tool,
            },
        }
        if output_path:
            metadata["export"] = {"path": output_path}
        return metadata

    def _notify_export_result(
        self,
        *,
        kind: str,
        path: str,
        exported_items: str,
    ) -> None:
        """Show a toaster notification summarizing a completed export."""
        self.notify(
            f"Saved {kind}: {Path(path).name} — {exported_items}",
            severity="information",
            timeout=4,
        )

    def _notify_import_result(
        self,
        *,
        path: str,
        imported_items: str,
    ) -> None:
        """Show a toaster notification summarizing a completed import."""
        self.notify(
            f"Loaded {Path(path).name} — {imported_items}",
            severity="information",
            timeout=4,
        )

    def _build_image_export_metadata(
        self,
        *,
        exported_traces: list[str],
        plot_type: str,
        output_path: str,
    ) -> dict[str, object]:
        """Build image-export metadata including raw measurement payload for recovery."""
        metadata = self._build_touchstone_export_metadata(
            exported_traces=exported_traces,
            output_path=output_path,
        )
        measurement_data = metadata.get("measurement", {})
        measurement = (
            dict(measurement_data) if isinstance(measurement_data, dict) else {}
        )
        measurement["plot_type"] = plot_type
        measurement["raw_data"] = {
            "freqs_hz": (
                self.last_measurement["freqs"].tolist()
                if self.last_measurement is not None
                else []
            ),
            "sparams": {
                name: {
                    "magnitude_db": values[0].tolist(),
                    "phase_deg": values[1].tolist(),
                }
                for name, values in (
                    self.last_measurement.get("sparams", {}).items()
                    if self.last_measurement is not None
                    else []
                )
            },
        }
        metadata["measurement"] = measurement
        return build_image_export_metadata(
            notes_markdown=self.measurement_notes,
            machine_settings=metadata,
        ).machine_settings

    def _is_minimal_export_enabled(self) -> bool:
        """Return whether minimal export mode is enabled in the Measurement tab."""
        return self._minimal_export_mode

    @staticmethod
    def _minimal_export_suffix(minimal_export: bool) -> str:
        """Return a short label suffix for minimal export notifications."""
        return " (minimal)" if minimal_export else ""

    def _write_image_export(
        self,
        *,
        file_path: str,
        plot_type: str,
        plot_params: list[str],
        dpi: int,
        metadata_writer,
        minimal_export: bool = False,
    ) -> None:
        """Render an image export and optionally embed notes plus recovery metadata."""
        if self.last_measurement is None:
            raise ValueError("No measurement data available for image export")

        measurement = self.last_measurement

        if plot_type == "smith":
            create_smith_chart(
                measurement["freqs"],
                measurement["sparams"],
                plot_params,
                Path(file_path),
                dpi=dpi,
                colors=get_plot_colors(self.get_css_variables()),
            )
        else:
            create_matplotlib_plot(
                measurement["freqs"],
                measurement["sparams"],
                plot_params,
                str(plot_type),
                Path(file_path),
                dpi=dpi,
                colors=get_plot_colors(self.get_css_variables()),
            )

        if minimal_export:
            return

        metadata_writer(
            file_path,
            notes_markdown=str(measurement.get("notes", "")),
            machine_settings=self._build_image_export_metadata(
                exported_traces=plot_params,
                plot_type=str(plot_type),
                output_path=file_path,
            ),
        )

    def _restore_setup_from_metadata(self, metadata: dict[str, object]) -> None:
        """Restore Setup tab widgets and persisted settings from imported metadata."""
        setup = metadata.get("setup", {})
        if not isinstance(setup, dict):
            return

        def _set_input(selector: str, value: object) -> None:
            if value is not None:
                self.query_one(selector, Input).value = str(value)

        def _set_checkbox(selector: str, value: object) -> None:
            if isinstance(value, bool):
                self.query_one(selector, Checkbox).value = value

        def _set_select(selector: str, value: object) -> None:
            if value is not None:
                self.query_one(selector, Select).value = value

        _set_input("#input_host", setup.get("host"))
        _set_input("#input_port", setup.get("port"))
        _set_select("#select_freq_unit", setup.get("freq_unit"))
        _set_input("#input_start_freq", setup.get("start_freq_mhz"))
        _set_input("#input_stop_freq", setup.get("stop_freq_mhz"))
        _set_input("#input_points", setup.get("sweep_points"))
        _set_input("#input_avg_count", setup.get("averaging_count"))
        _set_checkbox("#check_set_freq", setup.get("set_freq_range"))
        _set_checkbox("#check_set_points", setup.get("set_sweep_points"))
        _set_checkbox("#check_averaging", setup.get("enable_averaging"))
        _set_checkbox("#check_set_avg_count", setup.get("set_averaging_count"))

        folder_template = setup.get("folder_template")
        output_folder = setup.get("output_folder")
        restored_folder_template = (
            folder_template if isinstance(folder_template, str) else output_folder
        )
        _set_input("#input_output_folder", restored_folder_template)

        filename_template = setup.get("filename_template")
        filename_prefix = setup.get("filename_prefix")
        restored_filename_template = (
            filename_template if isinstance(filename_template, str) else filename_prefix
        )
        _set_input("#input_filename_prefix", restored_filename_template)

        _set_checkbox("#check_export_s11", setup.get("export_s11"))
        _set_checkbox("#check_export_s21", setup.get("export_s21"))
        _set_checkbox("#check_export_s12", setup.get("export_s12"))
        _set_checkbox("#check_export_s22", setup.get("export_s22"))
        _set_checkbox("#check_export_bundle_s2p", setup.get("export_bundle_s2p"))
        _set_checkbox("#check_export_bundle_csv", setup.get("export_bundle_csv"))
        _set_checkbox("#check_export_bundle_png", setup.get("export_bundle_png"))
        _set_checkbox("#check_export_bundle_svg", setup.get("export_bundle_svg"))

        host = setup.get("host")
        if isinstance(host, str):
            self.settings.last_host = host
            self.settings_manager.add_host_to_history(host)

        port = setup.get("port")
        if isinstance(port, str):
            self.settings.last_port = port
            self.settings_manager.add_port_to_history(port)

        freq_unit = setup.get("freq_unit")
        if isinstance(freq_unit, str):
            self.settings.freq_unit = freq_unit

        start_freq = setup.get("start_freq_mhz")
        if isinstance(start_freq, (int, float)):
            self.settings.start_freq_mhz = float(start_freq)

        stop_freq = setup.get("stop_freq_mhz")
        if isinstance(stop_freq, (int, float)):
            self.settings.stop_freq_mhz = float(stop_freq)

        sweep_points = setup.get("sweep_points")
        if isinstance(sweep_points, int):
            self.settings.sweep_points = sweep_points

        averaging_count = setup.get("averaging_count")
        if isinstance(averaging_count, int):
            self.settings.averaging_count = averaging_count

        for key in (
            "set_freq_range",
            "set_sweep_points",
            "enable_averaging",
            "set_averaging_count",
            "export_s11",
            "export_s21",
            "export_s12",
            "export_s22",
            "export_bundle_s2p",
            "export_bundle_csv",
            "export_bundle_png",
            "export_bundle_svg",
        ):
            value = setup.get(key)
            if isinstance(value, bool):
                setattr(self.settings, key, value)

        if isinstance(restored_folder_template, str):
            self.settings.output_folder = restored_folder_template
            self.settings.folder_template = restored_folder_template

        if isinstance(restored_filename_template, str):
            self.settings.filename_template = restored_filename_template
            self.settings.filename_prefix = restored_filename_template

        self.settings_manager.save(self.settings)
        setup_logic.refresh_export_template_validation(self)

    def _restore_measurement_view_from_metadata(
        self,
        metadata: dict[str, object],
        *,
        sparams: dict[str, tuple[np.ndarray, np.ndarray]] | None = None,
    ) -> None:
        """Restore Measurement tab plot state from imported metadata."""
        measurement = metadata.get("measurement", {})
        if not isinstance(measurement, dict):
            measurement = {}

        plot_type = measurement.get("plot_type")
        if isinstance(plot_type, str):
            self.query_one("#select_plot_type", Select).value = plot_type
            self.settings.plot_type = plot_type

        available_params = sparams or {}
        for key, selector, fallback_name in (
            ("plot_s11", "#check_plot_s11", "S11"),
            ("plot_s21", "#check_plot_s21", "S21"),
            ("plot_s12", "#check_plot_s12", "S12"),
            ("plot_s22", "#check_plot_s22", "S22"),
        ):
            value = measurement.get(key)
            checkbox = self.query_one(selector, Checkbox)
            if isinstance(value, bool):
                checkbox.value = value
                setattr(self.settings, key, value)
            else:
                fallback = fallback_name in available_params
                checkbox.value = fallback
                setattr(self.settings, key, fallback)

    def _activate_measurement_tab(self) -> None:
        """Switch the UI to the Measurement tab."""
        self.query_one(TabbedContent).active = "tab_results"

    def _import_measurement_output(
        self,
        *,
        restore_measurement: bool,
    ) -> None:
        """Import metadata from a measurement output, optionally restoring measurement state."""
        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)

        try:
            file_path = filedialog.askopenfilename(
                title="Select Measurement Output",
                filetypes=[
                    ("Measurement Outputs", "*.s2p *.png *.svg"),
                    ("Touchstone Files", "*.s2p"),
                    ("PNG Images", "*.png"),
                    ("SVG Images", "*.svg"),
                    ("All Files", "*.*"),
                ],
                initialdir=(
                    self.settings.output_folder if self.settings.output_folder else "."
                ),
            )
        finally:
            root.destroy()

        if not file_path:
            return

        self.log_message(f"Importing: {file_path}", "progress")

        suffix = Path(file_path).suffix.lower()
        freqs: np.ndarray | None = None
        sparams: dict[str, tuple[np.ndarray, np.ndarray]] | None = None
        notes_markdown = ""
        imported_metadata: dict[str, object] = {}

        if suffix == ".s2p":
            import_result = TouchstoneExporter.import_with_metadata(file_path)
            freqs = import_result.frequencies_hz
            sparams = import_result.s_parameters
            notes_markdown = import_result.metadata.notes_markdown
            imported_metadata = import_result.metadata.machine_settings or {}
        elif suffix == ".png":
            image_metadata = read_png_metadata(file_path)
            notes_markdown = image_metadata.notes_markdown
            imported_metadata = image_metadata.machine_settings
        elif suffix == ".svg":
            image_metadata = read_svg_metadata(file_path)
            notes_markdown = image_metadata.notes_markdown
            imported_metadata = image_metadata.machine_settings
        else:
            raise ValueError(f"Unsupported measurement output format: {suffix}")

        self._restore_setup_from_metadata(imported_metadata)

        imported_measurement = imported_metadata.get("measurement", {})
        restored_panels = ["Setup"]

        if restore_measurement:
            if freqs is None or sparams is None:
                raw_data = (
                    imported_measurement.get("raw_data", {})
                    if isinstance(imported_measurement, dict)
                    else {}
                )
                if not isinstance(raw_data, dict):
                    raise ValueError(
                        "Measurement output does not contain recoverable measurement data"
                    )

                freqs_hz = raw_data.get("freqs_hz", [])
                raw_sparams = raw_data.get("sparams", {})
                if not isinstance(freqs_hz, list) or not isinstance(raw_sparams, dict):
                    raise ValueError(
                        "Measurement output contains invalid recovery payload"
                    )

                freqs = np.array(freqs_hz, dtype=float)
                sparams = {}
                for name, values in raw_sparams.items():
                    if not isinstance(name, str) or not isinstance(values, dict):
                        continue
                    magnitude_db = values.get("magnitude_db", [])
                    phase_deg = values.get("phase_deg", [])
                    if isinstance(magnitude_db, list) and isinstance(phase_deg, list):
                        sparams[name] = (
                            np.array(magnitude_db, dtype=float),
                            np.array(phase_deg, dtype=float),
                        )

                if len(freqs) == 0 or not sparams:
                    raise ValueError(
                        "Measurement output does not contain recoverable measurement data"
                    )

            imported_freq_unit = "MHz"
            imported_setup = imported_metadata.get("setup", {})
            if isinstance(imported_setup, dict):
                imported_freq_unit_value = imported_setup.get("freq_unit")
                if isinstance(imported_freq_unit_value, str):
                    imported_freq_unit = imported_freq_unit_value

            self.measurement_notes = notes_markdown
            self.last_measurement = {
                "freqs": freqs,
                "sparams": sparams,
                "output_path": file_path,
                "touchstone_path": file_path if suffix == ".s2p" else None,
                "png_path": file_path if suffix == ".png" else None,
                "svg_path": file_path if suffix == ".svg" else None,
                "freq_unit": imported_freq_unit,
                "notes": self.measurement_notes,
                "metadata": imported_metadata,
            }
            self.last_output_path = file_path
            self._load_measurement_notes_into_editor()
            self._refresh_measurement_notes_preview()
            self._restore_measurement_view_from_metadata(
                imported_metadata,
                sparams=sparams,
            )
            self._activate_measurement_tab()
            restored_panels.append("Measurement")

            self.log_message(
                f"Imported {len(freqs)} points, {len(sparams)} S-parameters", "success"
            )

            asyncio.create_task(self._update_results(freqs, sparams, file_path))
            asyncio.create_task(self._refresh_tools_plot())
            self._run_tools_computation()
            self.call_after_refresh(self._rebuild_tools_params)
            self._notify_import_result(
                path=file_path,
                imported_items=(
                    f"{len(sparams)} traces, {len(freqs)} points; "
                    f"restored {', '.join(restored_panels)}"
                ),
            )
        else:
            self.log_message("Imported setup from measurement output", "success")
            self.notify(
                f"Loaded setup from {Path(file_path).name} — restored {', '.join(restored_panels)}",
                severity="information",
                timeout=4,
            )

    def _start_message_polling(self):
        """Start polling worker thread for messages."""
        self._message_check_timer = self.set_interval(0.05, self._check_worker_messages)

    def _start_status_polling(self, interval_s: int) -> None:
        """Start (or restart) periodic VNA status polling."""
        if self._poll_timer is not None:
            self._poll_timer.stop()
            self._poll_timer = None
        if interval_s > 0:
            self._poll_timer = self.set_interval(interval_s, self._do_status_poll)

    def _stop_status_polling(self) -> None:
        """Stop status polling and clear the status bar."""
        if self._poll_timer is not None:
            self._poll_timer.stop()
            self._poll_timer = None
        self.query_one(StatusFooter).set_disconnected()

    def _do_status_poll(self) -> None:
        """Send a status poll request to the worker.

        Skipped when disconnected, measuring, or a previous poll has not yet
        returned a STATUS_UPDATE — prevents backlog when polls take longer than
        the polling interval.
        """
        if self.connected and not self.measuring and not self._status_poll_in_flight:
            self._status_poll_in_flight = True
            self.worker.send_command(MessageType.STATUS_POLL)

    def _check_worker_messages(self):
        """Check for messages from worker thread (called periodically)."""
        try:
            while True:
                msg = self.worker.get_response(timeout=0.001)
                self._handle_worker_message(msg)
        except queue.Empty:
            pass

    def _handle_worker_message(self, msg):
        """Handle message from worker thread."""
        if msg.type == MessageType.LOG:
            log_msg: LogMessage = msg.data
            self.log_message(log_msg.message, log_msg.level)

        elif msg.type == MessageType.PROGRESS:
            update: ProgressUpdate = msg.data
            self.set_progress(update.message, update.progress_pct)

        elif msg.type == MessageType.CONNECTED:
            display_name = msg.data
            self.connected = True
            self.sub_title = display_name
            self._update_title()
            self.log_message(f"Connected: {display_name}", "success")
            self.update_connect_button()
            self.enable_buttons_for_state()
            self.reset_progress()
            self._start_status_polling(self.settings.status_poll_interval)
            if self._debug_scpi:
                self.worker.send_command(MessageType.SET_DEBUG_SCPI, data=True)
            # Immediate first poll without waiting for the interval
            self._status_poll_in_flight = True
            self.worker.send_command(MessageType.STATUS_POLL)

        elif msg.type == MessageType.DISCONNECTED:
            self.connected = False
            self._status_poll_in_flight = False
            self.sub_title = ""
            self._update_title()
            self.log_message("Disconnected from VNA", "success")
            self.update_connect_button()
            self.enable_buttons_for_state()
            self.reset_progress()
            self._stop_status_polling()

        elif msg.type == MessageType.PARAMS_READ:
            params_result: ParamsResult = msg.data
            self._update_params_ui(params_result)
            self.log_message("Parameters retrieved successfully", "success")
            self.enable_buttons_for_state()
            self.reset_progress()

        elif msg.type == MessageType.MEASUREMENT_COMPLETE:
            measurement_result: MeasurementResult = msg.data
            self.log_message(
                f"Received measurement complete with {len(measurement_result.frequencies)} points",
                "debug",
            )
            # Schedule the async handler
            asyncio.create_task(self._handle_measurement_complete(measurement_result))

        elif msg.type == MessageType.STATUS_UPDATE:
            self._status_poll_in_flight = False
            status_result: StatusResult = msg.data
            self.query_one(StatusFooter).update_status(status_result)

        elif msg.type == MessageType.SCPI_ERROR_UPDATE:
            if self._debug_scpi:
                self.query_one(StatusFooter).update_last_error(
                    msg.data["command"], msg.data["error"]
                )

        elif msg.type == MessageType.ERROR:
            self.log_message(msg.error, "error")
            if "Connection failed" in msg.error or "Disconnect failed" in msg.error:
                self.connected = False
                self.sub_title = ""
                self._update_title()
                self.update_connect_button()
                self._stop_status_polling()
            self.enable_buttons_for_state()
            self.reset_progress()
            self.measuring = False

    @on(Select.Changed, "#sb_poll_interval")
    def on_poll_interval_change(self, event: Select.Changed) -> None:
        """Handle status poll interval change."""
        if event.value == Select.BLANK or not isinstance(event.value, int):
            return
        self.settings.status_poll_interval = event.value
        if self.connected:
            self._start_status_polling(event.value)

    @on(Input.Changed, "#input_filename_prefix, #input_output_folder")
    def on_export_template_change(self, event: Input.Changed) -> None:
        """Refresh export-template validation when the template inputs change."""
        del event
        setup_logic.handle_export_template_change(self)

    @on(Button.Pressed, "#check_minimal_export")
    def on_minimal_export_toggle_pressed(self, event: Button.Pressed) -> None:
        """Toggle minimal export mode from the Measurement tab button."""
        del event
        self._minimal_export_mode = not self._minimal_export_mode
        self._refresh_export_button_labels()

    @on(TabbedContent.TabActivated)
    def on_tab_activated(self, event: TabbedContent.TabActivated) -> None:
        """
        Handle tab activation events by updating the UI: scroll the log when the Log tab is opened and schedule plot redraws when Results or Tools tabs are opened.

        When the Log tab is activated, scroll the log widget to the end. When the Results or Tools tab is activated, schedule a delayed redraw (0.3 seconds) of the corresponding plot if a measurement is available.

        Parameters:
            event (TabbedContent.TabActivated): The tab activation event containing the activated pane (used to check pane.id).
        """
        if event.pane.id == "tab_log":
            # Scroll log to bottom when opening log tab
            log_content = self.query_one("#log_content", RichLog)
            log_content.scroll_end(animate=False)
        elif event.pane.id == "tab_results":
            # Redraw plot with correct sizing when switching to results tab
            if self.last_measurement is not None:
                self.set_timer(0.3, self._delayed_redraw_plot)
        elif event.pane.id == "tab_tools":
            # Redraw tools plot when switching to tools tab
            if self.last_measurement is not None:
                self.set_timer(0.3, self._delayed_redraw_tools_plot)

    @on(
        Checkbox.Changed,
        "#check_log_tx, #check_log_rx, #check_log_info, #check_log_progress, #check_log_success, #check_log_error, #check_log_debug, #check_log_poll",
    )
    def on_log_filter_change(self, event: Checkbox.Changed) -> None:
        """Handle log filter checkbox changes."""
        del event
        log_logic.handle_log_filter_change(self)

    # Cached level→(icon, Rich style) map; None means rebuild on next use.
    # Invalidated by on_app_theme_changed so colors always match the active theme.
    _cached_style_map: dict[str, tuple[str, str]] | None = None

    def log_message(self, message: str, level: str = "info"):
        """Add message to log."""
        log_logic.log_message(self, message, level)

    def set_progress(self, label: str, progress: float = 0):
        """Update progress bar and label. Progress is 0-100."""
        self.query_one("#progress_label", Label).update(f"{label} ({progress:.0f}%)")
        progress_bar = self.query_one("#progress_bar", ProgressBar)
        progress_bar.update(total=100, progress=progress)

    def reset_progress(self):
        """Reset progress bar based on connection state."""
        if self.connected:
            self.query_one("#progress_label", Label).update("Ready")
        else:
            self.query_one("#progress_label", Label).update("Disconnected")
        progress_bar = self.query_one("#progress_bar", ProgressBar)
        progress_bar.update(total=100, progress=0)

    def disable_all_buttons(self):
        """Disable all action buttons during operations."""
        self.query_one("#btn_connect", Button).disabled = True
        self.query_one("#btn_read_params", Button).disabled = True
        self.query_one("#btn_measure", Button).disabled = True

    def enable_buttons_for_state(self):
        """Enable buttons based on connection state."""
        self.query_one("#btn_connect", Button).disabled = False
        self.query_one("#btn_read_params", Button).disabled = not self.connected
        self.query_one("#btn_measure", Button).disabled = not self.connected
        self._refresh_export_button_labels()

    def update_connect_button(self):
        """
        Update the connect button's label and visual variant to reflect the current connection state.

        When connected, sets the button label to "🔌\nDisconnect" and its variant to "error".
        When disconnected, sets the button label to "📡\nConnect" and its variant to "primary".
        """
        btn = self.query_one("#btn_connect", Button)
        if self.connected:
            btn.label = "🔌\nDisconnect"
            btn.variant = "error"
        else:
            btn.label = "📡\nConnect"
            btn.variant = "primary"

    def _refresh_export_button_labels(self) -> None:
        """Update Measurement-tab export controls to reflect minimal export mode."""
        toggle_button = self.query_one("#check_minimal_export", Button)
        minimal_export = self._minimal_export_mode
        variant = "warning" if minimal_export else "success"

        toggle_button.variant = "warning" if minimal_export else "default"
        toggle_button.label = "▣\nMin" if minimal_export else "▢\nMin"
        toggle_button.set_class(minimal_export, "-minimal-export")

        show_button = self.query_one("#btn_open_output", Button)
        show_button.styles.margin = (0, 0, 0, 0)

        for selector in (
            "#btn_export_touchstone",
            "#btn_export_csv",
            "#btn_export_png",
            "#btn_export_svg",
        ):
            button = self.query_one(selector, Button)
            button.variant = variant
            button.set_class(minimal_export, "-minimal-export")

    def _show_help_document(self, filename: str, title: str) -> None:
        """Load a markdown help document from package resources and show it."""
        try:
            help_files = importlib.resources.files("tina") / "help"
            content = (help_files / filename).read_text(encoding="utf-8")
        except (OSError, FileNotFoundError, ModuleNotFoundError):
            content = "_Help file not found._"
        self.push_screen(HelpScreen(title, content))

    def action_show_tool_help(self) -> None:
        """
        Show the help viewer for the currently selected tool.

        If no tool is active, notifies the user and returns. Otherwise loads the tool's markdown help file from the package's tina/help resources (falls back to a short "Help file not found." message on load failure) and opens a HelpScreen displaying the content.
        """
        active = self.settings.tools_active_tool
        help_map = {
            "cursor": ("cursor.md", "Cursor Tool Help"),
            "distortion": ("distortion.md", "Distortion Tool Help"),
        }
        if active not in help_map:
            self.notify("Activate a tool to see its help.", timeout=2)
            return
        filename, title = help_map[active]
        self._show_help_document(filename, title)

    def action_show_output_help(self) -> None:
        """Show help for output template rendering and validation."""
        self._show_help_document("output.md", "Output Help")

    def action_copy_cell_value(self, value: str) -> None:
        """
        Copy the provided string to the system clipboard and display a short notification.

        Parameters:
            value (str): Text to copy to the clipboard.
        """
        self.copy_to_clipboard(value)
        self.notify(f"Copied: {value}", timeout=1.5)

    def action_copy_log(self) -> None:
        """Copy visible log entries as plain text to the system clipboard."""
        log_logic.copy_log(self)

    @on(Button.Pressed, "#btn_connect")
    def handle_connect(self) -> None:
        """Connect or disconnect from VNA."""
        self.disable_all_buttons()

        if self.connected:
            # Stop polling immediately so no more STATUS_POLLs queue up
            self.connected = False
            self._update_title()
            if self._poll_timer is not None:
                self._poll_timer.stop()
                self._poll_timer = None
            # Disconnect
            self.set_progress("Disconnecting...", 50)
            self.log_message("Disconnecting from VNA...", "progress")
            self.worker.clear_commands()
            self.worker.send_command(MessageType.DISCONNECT)
        else:
            # Connect
            try:
                self.config.host = self.query_one("#input_host", Input).value.strip()
                self.config.port = (
                    self.query_one("#input_port", Input).value.strip() or "inst0"
                )

                # Validate host is provided
                if not self.config.host:
                    self.log_message("Please enter VNA IP address", "error")
                    self.enable_buttons_for_state()
                    self.reset_progress()
                    return

                # Add host to history
                self.settings_manager.add_host_to_history(self.config.host)

                # Add port to history
                self.settings_manager.add_port_to_history(self.config.port)

                # Save settings on successful connection attempt
                self._save_current_settings()

                self.log_message(f"Connecting to {self.config.host}...", "progress")
                self.sub_title = "Connecting..."

                self.worker.send_command(MessageType.CONNECT, self.config)

            except Exception as e:
                self.log_message(f"Connection setup failed: {str(e)}", "error")
                self.enable_buttons_for_state()
                self.reset_progress()

    def action_toggle_debug_scpi(self) -> None:
        """Toggle per-command SCPI error checking (debug mode)."""
        self._debug_scpi = not self._debug_scpi
        self.settings.debug_scpi = self._debug_scpi
        self.worker.send_command(MessageType.SET_DEBUG_SCPI, data=self._debug_scpi)
        self._update_title()
        self.query_one(StatusFooter).set_debug_mode(self._debug_scpi, self.connected)
        state = "ON" if self._debug_scpi else "OFF"
        self.log_message(
            f"SCPI debug mode {state} — queries SYST:ERR? after each command", "info"
        )

    def _update_title(self) -> None:
        """Reflect connection and debug mode state in the app title."""
        base = (
            "TINA"
            if self.connected
            else f"TINA v{__version__} - Terminal UI Network Analyzer"
        )
        self.title = f"{base} 🐛" if self._debug_scpi else base

    @on(Button.Pressed, "#btn_read_params")
    def handle_read_params(self) -> None:
        """Read current settings from VNA and populate inputs."""
        self.disable_all_buttons()
        self.log_message("Reading VNA parameters...", "progress")
        self.worker.send_command(MessageType.READ_PARAMS)

    def _update_params_ui(self, result: ParamsResult) -> None:
        """Update UI with parameters read from VNA."""
        freq_unit_value = self.query_one("#select_freq_unit", Select).value
        freq_unit = freq_unit_value if isinstance(freq_unit_value, str) else "MHz"
        unit_multipliers = {"Hz": 1, "kHz": 1e3, "MHz": 1e6, "GHz": 1e9}
        multiplier = unit_multipliers.get(freq_unit, 1e6)

        start_val = result.start_freq / multiplier
        stop_val = result.stop_freq / multiplier

        self.query_one("#input_start_freq", Input).value = f"{start_val:.2f}"
        self.query_one("#input_stop_freq", Input).value = f"{stop_val:.2f}"
        self.query_one("#input_points", Input).value = str(result.points)
        self.query_one("#check_averaging", Checkbox).value = result.averaging_enabled
        self.query_one("#input_avg_count", Input).value = str(result.averaging_count)

    @on(Button.Pressed, "#btn_measure")
    def handle_measure(self) -> None:
        """Handle measure button."""
        if self.measuring:
            return

        self.measuring = True
        self.disable_all_buttons()

        try:
            # Get frequency unit and convert to Hz
            freq_unit_value = self.query_one("#select_freq_unit", Select).value
            freq_unit = freq_unit_value if isinstance(freq_unit_value, str) else "MHz"
            unit_multipliers = {"Hz": 1, "kHz": 1e3, "MHz": 1e6, "GHz": 1e9}
            multiplier = unit_multipliers.get(freq_unit, 1e6)

            # Update config from inputs
            self.config.start_freq_hz = (
                float(self.query_one("#input_start_freq", Input).value) * multiplier
            )
            self.config.stop_freq_hz = (
                float(self.query_one("#input_stop_freq", Input).value) * multiplier
            )
            self.config.sweep_points = int(self.query_one("#input_points", Input).value)
            self.config.averaging_count = int(
                self.query_one("#input_avg_count", Input).value
            )

            # Update config toggles
            self.config.set_freq_range = self.query_one(
                "#check_set_freq", Checkbox
            ).value
            self.config.set_sweep_points = self.query_one(
                "#check_set_points", Checkbox
            ).value
            self.config.enable_averaging = self.query_one(
                "#check_averaging", Checkbox
            ).value
            self.config.set_averaging_count = self.query_one(
                "#check_set_avg_count", Checkbox
            ).value

        except ValueError as e:
            self.log_message(f"Invalid configuration: {e}", "error")
            self.measuring = False
            self.enable_buttons_for_state()
            self.reset_progress()
            return

        # Save settings before measurement
        self._save_current_settings()

        self.sub_title = "Measuring..."
        self.log_message("Starting measurement...", "progress")

        # Send measurement command to worker
        self.worker.send_command(MessageType.MEASURE, self.config)

    async def _handle_measurement_complete(self, result: MeasurementResult):
        """
        Process a completed measurement: export selected S-parameters, cache the measurement, and update the UI and plots.

        Parameters:
            result (MeasurementResult): Measurement outcome containing frequency array and S-parameter data.

        Behavior:
            - Exports the S-parameters selected in the UI to a Touchstone file.
            - Updates `self.last_measurement` and `self.last_output_path` with the saved file and raw measurement data.
            - Synchronizes plot selection checkboxes to match export selections.
            - Triggers redraw of the main results plot and the Tools plot, then runs tool computations.
            - Updates progress indicators, logs success or errors, and sets the app subtitle to reflect completion or failure.
        """
        try:
            self.log_message("Processing measurement result...", "debug")
            freqs = result.frequencies
            sparams = result.sparams

            self.log_message(
                f"Result contains {len(freqs)} frequencies, {len(sparams)} S-parameters",
                "debug",
            )

            self.log_message(
                f"Measurement complete: {len(freqs)} points captured", "success"
            )

            # Filter S-parameters based on export checkboxes
            self.log_message("Filtering S-parameters for export...", "debug")
            export_params = {}
            if self.query_one("#check_export_s11", Checkbox).value:
                export_params["S11"] = sparams["S11"]
            if self.query_one("#check_export_s21", Checkbox).value:
                export_params["S21"] = sparams["S21"]
            if self.query_one("#check_export_s12", Checkbox).value:
                export_params["S12"] = sparams["S12"]
            if self.query_one("#check_export_s22", Checkbox).value:
                export_params["S22"] = sparams["S22"]

            self.log_message(
                f"Exporting {len(export_params)} S-parameters: {', '.join(export_params.keys())}",
                "debug",
            )

            if not export_params:
                self.log_message("No S-parameters selected for export", "error")
                self.sub_title = "Connected"
                return

            # Export to touchstone
            self.set_progress("Exporting...", 80)
            self.log_message("Exporting to Touchstone format...", "progress")

            freq_unit_value = self.query_one("#select_freq_unit", Select).value
            freq_unit = freq_unit_value if isinstance(freq_unit_value, str) else "MHz"
            exporter = TouchstoneExporter(freq_unit=freq_unit)

            filename_template = self.query_one(
                "#input_filename_prefix", Input
            ).value.strip()
            if not filename_template:
                filename_template = (
                    self.settings.filename_template or "measurement_{date}_{time}"
                )

            folder_template = self.query_one(
                "#input_output_folder", Input
            ).value.strip()
            if not folder_template:
                folder_template = self.settings.folder_template or "measurement"

            filename_validation = setup_logic.validate_export_template_for_app(
                filename_template,
                allow_path_separators=False,
            )
            folder_validation = setup_logic.validate_export_template_for_app(
                folder_template,
                allow_path_separators=True,
            )

            self._filename_template_validation = filename_validation
            self._folder_template_validation = folder_validation
            setup_logic.apply_template_input_state(
                self,
                "#input_filename_prefix",
                filename_validation,
                kind="filename template",
            )
            setup_logic.apply_template_input_state(
                self,
                "#input_output_folder",
                folder_validation,
                kind="folder template",
            )

            if filename_validation.has_errors or folder_validation.has_errors:
                self.notify(
                    "Export blocked: fix output template path errors first.",
                    severity="error",
                    timeout=3,
                )
                self.log_message(
                    "Export blocked due to invalid output template characters.",
                    "error",
                )
                self.sub_title = "Connected"
                return

            export_context = setup_logic.build_export_template_context_for_app(self)
            rendered_filename = render_template(
                filename_template,
                context=export_context,
                allowed_tags=set(DEFAULT_TEMPLATE_TAGS),
            )
            rendered_folder = render_template(
                folder_template,
                context=export_context,
                allowed_tags=set(DEFAULT_TEMPLATE_TAGS),
                invalid_path_chars=set(PATH_INVALID_CHARS) - {"/", "\\"},
            )

            if rendered_filename.validation.has_warnings:
                self.log_message(
                    "Filename template contains unknown tags: "
                    + ", ".join(rendered_filename.validation.unknown_tags),
                    "info",
                )
            if rendered_folder.validation.has_warnings:
                self.log_message(
                    "Folder template contains unknown tags: "
                    + ", ".join(rendered_folder.validation.unknown_tags),
                    "info",
                )

            filename = rendered_filename.rendered.strip() or "measurement"
            output_folder = rendered_folder.rendered.strip() or "measurement"

            self.settings_manager.touch_template_history(
                "filename_template_history",
                filename_template,
            )
            self.settings_manager.touch_template_history(
                "folder_template_history",
                folder_template,
            )
            self.settings_manager.save(self.settings)

            export_folder: str = output_folder
            export_filename: str = filename
            export_name: str = "measurement"
            exported_trace_names = list(export_params.keys())
            minimal_export = self._is_minimal_export_enabled()
            touchstone_metadata = (
                None
                if minimal_export
                else self._build_touchstone_export_metadata(
                    exported_traces=exported_trace_names,
                )
            )
            output_path = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: exporter.export(
                    freqs,
                    export_params,
                    export_folder,
                    export_filename,
                    export_name,
                    notes_markdown="" if minimal_export else self.measurement_notes,
                    metadata=touchstone_metadata,
                ),
            )

            self.log_message(
                f"Saved{self._minimal_export_suffix(minimal_export)}: {output_path}",
                "success",
            )
            self._notify_export_result(
                kind=f"Touchstone{self._minimal_export_suffix(minimal_export)}",
                path=output_path,
                exported_items=", ".join(exported_trace_names),
            )

            csv_path = None
            if self.query_one("#check_export_bundle_csv", Checkbox).value:
                csv_exporter = CsvExporter(freq_unit=str(self.settings.freq_unit))
                csv_path = await asyncio.get_event_loop().run_in_executor(
                    None,
                    csv_exporter.export,
                    freqs,
                    export_params,
                    export_folder,
                    export_filename,
                    export_name,
                )
                self.log_message(f"Saved: {csv_path}", "success")
                self._notify_export_result(
                    kind="CSV",
                    path=csv_path,
                    exported_items=", ".join(exported_trace_names),
                )

            png_path = None
            if self.query_one("#check_export_bundle_png", Checkbox).value:
                png_path = str(Path(export_folder) / f"{export_filename}.png")
                await asyncio.get_event_loop().run_in_executor(
                    None,
                    lambda: self._write_image_export(
                        file_path=png_path,
                        plot_type=str(self.settings.plot_type),
                        plot_params=exported_trace_names,
                        dpi=300,
                        metadata_writer=embed_png_metadata,
                        minimal_export=minimal_export,
                    ),
                )
                self.log_message(
                    f"Saved{self._minimal_export_suffix(minimal_export)}: {png_path}",
                    "success",
                )
                self._notify_export_result(
                    kind=f"PNG{self._minimal_export_suffix(minimal_export)}",
                    path=png_path,
                    exported_items=", ".join(exported_trace_names),
                )

            svg_path = None
            if self.query_one("#check_export_bundle_svg", Checkbox).value:
                svg_path = str(Path(export_folder) / f"{export_filename}.svg")
                await asyncio.get_event_loop().run_in_executor(
                    None,
                    lambda: self._write_image_export(
                        file_path=svg_path,
                        plot_type=str(self.settings.plot_type),
                        plot_params=exported_trace_names,
                        dpi=150,
                        metadata_writer=embed_svg_metadata,
                        minimal_export=minimal_export,
                    ),
                )
                self.log_message(
                    f"Saved{self._minimal_export_suffix(minimal_export)}: {svg_path}",
                    "success",
                )
                self._notify_export_result(
                    kind=f"SVG{self._minimal_export_suffix(minimal_export)}",
                    path=svg_path,
                    exported_items=", ".join(exported_trace_names),
                )

            # Store measurement data with frequency unit
            freq_unit = self.query_one("#select_freq_unit", Select).value
            self.last_measurement = {
                "freqs": freqs,
                "sparams": sparams,
                "output_path": output_path,
                "touchstone_path": output_path,
                "csv_path": csv_path,
                "png_path": png_path,
                "svg_path": svg_path,
                "freq_unit": freq_unit,
                "notes": self.measurement_notes,
            }
            self.last_output_path = output_path

            # Set plot checkboxes to match export parameters
            self.query_one("#check_plot_s11", Checkbox).value = self.query_one(
                "#check_export_s11", Checkbox
            ).value
            self.query_one("#check_plot_s21", Checkbox).value = self.query_one(
                "#check_export_s21", Checkbox
            ).value
            self.query_one("#check_plot_s12", Checkbox).value = self.query_one(
                "#check_export_s12", Checkbox
            ).value
            self.query_one("#check_plot_s22", Checkbox).value = self.query_one(
                "#check_export_s22", Checkbox
            ).value

            # Generate plot and update results
            self.set_progress("Updating results...", 90)
            self.log_message("Updating results display...", "debug")
            await self._update_results(freqs, sparams, output_path)
            self.log_message("Results display updated", "debug")

            # Also refresh tools tab with new data
            await self._refresh_tools_plot()
            self._run_tools_computation()
            self.call_after_refresh(self._rebuild_tools_params)

            self.set_progress("Done", 100)
            self.sub_title = "Measurement complete"

        except Exception as e:
            self.log_message(f"Post-measurement processing failed: {str(e)}", "error")
            self.sub_title = f"Error: {str(e)}"

        finally:
            self.measuring = False
            self.enable_buttons_for_state()
            self.reset_progress()

    @on(Button.Pressed, "#btn_import_results")
    def handle_import_results(self) -> None:
        """Import and display results from a Touchstone file."""
        try:
            self._import_measurement_output(restore_measurement=True)
        except FileNotFoundError as e:
            self.log_message(str(e), "error")
        except ValueError as e:
            self.log_message(f"Invalid file format: {e}", "error")
        except Exception as e:
            self.log_message(f"Import failed: {e}", "error")

    def action_import_setup_from_measurement_output(self) -> None:
        """Restore only the Setup tab from an exported measurement file."""
        try:
            self._import_measurement_output(restore_measurement=False)
        except FileNotFoundError as e:
            self.log_message(str(e), "error")
        except ValueError as e:
            self.log_message(f"Invalid file format: {e}", "error")
        except Exception as e:
            self.log_message(f"Setup import failed: {e}", "error")

    def _get_selected_export_params(self) -> dict[str, tuple[np.ndarray, np.ndarray]]:
        """Return the currently selected S-parameters available in cached data."""
        if not self.last_measurement:
            return {}

        sparams = self.last_measurement["sparams"]
        export_params: dict[str, tuple[np.ndarray, np.ndarray]] = {}

        if self.query_one("#check_export_s11", Checkbox).value and "S11" in sparams:
            export_params["S11"] = sparams["S11"]
        if self.query_one("#check_export_s21", Checkbox).value and "S21" in sparams:
            export_params["S21"] = sparams["S21"]
        if self.query_one("#check_export_s12", Checkbox).value and "S12" in sparams:
            export_params["S12"] = sparams["S12"]
        if self.query_one("#check_export_s22", Checkbox).value and "S22" in sparams:
            export_params["S22"] = sparams["S22"]

        return export_params

    def _choose_measurement_export_path(
        self,
        *,
        title: str,
        extension: str,
        filetypes: list[tuple[str, str]],
        default_source: str | None,
        fallback_name: str,
    ) -> str:
        """Open a save dialog for a measurement export and return the chosen path."""
        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)

        if default_source:
            default_name = Path(str(default_source)).stem + extension
        else:
            default_name = fallback_name

        try:
            return filedialog.asksaveasfilename(
                title=title,
                defaultextension=extension,
                filetypes=filetypes,
                initialdir=(
                    self.settings.output_folder if self.settings.output_folder else "."
                ),
                initialfile=default_name,
            )
        finally:
            root.destroy()

    @on(Button.Pressed, "#btn_export_touchstone")
    def handle_export_touchstone(self, event: Button.Pressed | None = None) -> None:
        """Export current measurement as a Touchstone file."""
        if not self.last_measurement:
            self.log_message("No measurement data to export", "error")
            return

        try:
            file_path = self._choose_measurement_export_path(
                title="Export Measurement as Touchstone (SxP)",
                extension=".s2p",
                filetypes=[("Touchstone / SxP File", "*.s2p"), ("All Files", "*.*")],
                default_source=(
                    self.last_measurement.get("touchstone_path")
                    or self.last_output_path
                ),
                fallback_name="measurement.s2p",
            )

            if not file_path:
                return

            export_params = self._get_selected_export_params()
            if not export_params:
                self.log_message(
                    "No S-parameters selected for Touchstone export", "error"
                )
                return

            freq_unit_value = self.query_one("#select_freq_unit", Select).value
            freq_unit = freq_unit_value if isinstance(freq_unit_value, str) else "MHz"
            exporter = TouchstoneExporter(freq_unit=freq_unit)
            exported_trace_names = list(export_params.keys())
            minimal_export = self._is_minimal_export_enabled()
            notes_markdown = (
                "" if minimal_export else str(self.last_measurement.get("notes", ""))
            )
            metadata = (
                None
                if minimal_export
                else self._build_touchstone_export_metadata(
                    exported_traces=exported_trace_names,
                    output_path=file_path,
                )
            )
            exporter.export(
                self.last_measurement["freqs"],
                export_params,
                str(Path(file_path).parent),
                filename=Path(file_path).name,
                notes_markdown=notes_markdown,
                metadata=metadata,
            )

            self.last_measurement["touchstone_path"] = file_path
            self.log_message(
                f"Exported Touchstone (SxP){self._minimal_export_suffix(minimal_export)}: {file_path}",
                "success",
            )
            self._notify_export_result(
                kind=f"Touchstone{self._minimal_export_suffix(minimal_export)}",
                path=file_path,
                exported_items=", ".join(exported_trace_names),
            )

        except Exception as e:
            self.log_message(f"Touchstone export failed: {e}", "error")

    @on(Button.Pressed, "#btn_export_csv")
    def handle_export_csv(self, event: Button.Pressed | None = None) -> None:
        """Export current measurement as a CSV file."""
        if not self.last_measurement:
            self.log_message("No measurement data to export", "error")
            return

        try:
            file_path = self._choose_measurement_export_path(
                title="Export Measurement as CSV",
                extension=".csv",
                filetypes=[("CSV File", "*.csv"), ("All Files", "*.*")],
                default_source=self.last_measurement.get("csv_path")
                or self.last_output_path,
                fallback_name="measurement.csv",
            )

            if not file_path:
                return

            export_params = self._get_selected_export_params()
            if not export_params:
                self.log_message("No S-parameters selected for CSV export", "error")
                return

            freq_unit_value = self.query_one("#select_freq_unit", Select).value
            freq_unit = freq_unit_value if isinstance(freq_unit_value, str) else "MHz"
            exporter = CsvExporter(freq_unit=freq_unit)
            exporter.export(
                self.last_measurement["freqs"],
                export_params,
                str(Path(file_path).parent),
                filename=Path(file_path).name,
            )

            self.last_measurement["csv_path"] = file_path
            self.log_message(f"Exported CSV: {file_path}", "success")
            self._notify_export_result(
                kind="CSV",
                path=file_path,
                exported_items=", ".join(export_params.keys()),
            )

        except Exception as e:
            self.log_message(f"CSV export failed: {e}", "error")

    @on(Button.Pressed, "#btn_export_png")
    def handle_export_png(self, event: Button.Pressed | None = None) -> None:
        """Export current plot as PNG."""
        if not self.last_measurement:
            self.log_message("No measurement data to export", "error")
            return

        try:
            # Use tkinter file dialog
            root = tk.Tk()
            root.withdraw()
            root.attributes("-topmost", True)

            # Use s2p filename as default if available
            if self.last_output_path:
                default_name = Path(self.last_output_path).stem + ".png"
            else:
                default_name = "plot.png"

            file_path = filedialog.asksaveasfilename(
                title="Export Plot as PNG",
                defaultextension=".png",
                filetypes=[("PNG Image", "*.png"), ("All Files", "*.*")],
                initialdir=(
                    self.settings.output_folder if self.settings.output_folder else "."
                ),
                initialfile=default_name,
            )
            root.destroy()

            if not file_path:
                return  # User cancelled

            # Get current plot settings
            plot_type = self.query_one("#select_plot_type", Select).value
            plot_params = []
            if self.query_one("#check_plot_s11", Checkbox).value:
                plot_params.append("S11")
            if self.query_one("#check_plot_s21", Checkbox).value:
                plot_params.append("S21")
            if self.query_one("#check_plot_s12", Checkbox).value:
                plot_params.append("S12")
            if self.query_one("#check_plot_s22", Checkbox).value:
                plot_params.append("S22")

            minimal_export = self._is_minimal_export_enabled()

            self._write_image_export(
                file_path=file_path,
                plot_type=str(plot_type),
                plot_params=plot_params,
                dpi=300,
                metadata_writer=embed_png_metadata,
                minimal_export=minimal_export,
            )

            self.log_message(
                f"Exported PNG{self._minimal_export_suffix(minimal_export)}: {file_path}",
                "success",
            )
            self._notify_export_result(
                kind=f"PNG{self._minimal_export_suffix(minimal_export)}",
                path=file_path,
                exported_items=", ".join(plot_params),
            )

        except Exception as e:
            self.log_message(f"PNG export failed: {e}", "error")

    @on(Button.Pressed, "#btn_export_svg")
    def handle_export_svg(self, event: Button.Pressed | None = None) -> None:
        """Export current plot as SVG."""
        if not self.last_measurement:
            self.log_message("No measurement data to export", "error")
            return

        try:
            # Use tkinter file dialog
            root = tk.Tk()
            root.withdraw()
            root.attributes("-topmost", True)

            # Use s2p filename as default if available
            if self.last_output_path:
                default_name = Path(self.last_output_path).stem + ".svg"
            else:
                default_name = "plot.svg"

            file_path = filedialog.asksaveasfilename(
                title="Export Plot as SVG",
                defaultextension=".svg",
                filetypes=[("SVG Vector Image", "*.svg"), ("All Files", "*.*")],
                initialdir=(
                    self.settings.output_folder if self.settings.output_folder else "."
                ),
                initialfile=default_name,
            )
            root.destroy()

            if not file_path:
                return  # User cancelled

            # Get current plot settings
            plot_type = self.query_one("#select_plot_type", Select).value
            plot_params = []
            if self.query_one("#check_plot_s11", Checkbox).value:
                plot_params.append("S11")
            if self.query_one("#check_plot_s21", Checkbox).value:
                plot_params.append("S21")
            if self.query_one("#check_plot_s12", Checkbox).value:
                plot_params.append("S12")
            if self.query_one("#check_plot_s22", Checkbox).value:
                plot_params.append("S22")

            minimal_export = self._is_minimal_export_enabled()

            self._write_image_export(
                file_path=file_path,
                plot_type=str(plot_type),
                plot_params=plot_params,
                dpi=150,
                metadata_writer=embed_svg_metadata,
                minimal_export=minimal_export,
            )

            self.log_message(
                f"Exported SVG{self._minimal_export_suffix(minimal_export)}: {file_path}",
                "success",
            )
            self._notify_export_result(
                kind=f"SVG{self._minimal_export_suffix(minimal_export)}",
                path=file_path,
                exported_items=", ".join(plot_params),
            )

        except Exception as e:
            self.log_message(f"SVG export failed: {e}", "error")

    @on(Button.Pressed, "#btn_reset_freq_limits")
    async def handle_reset_freq_limits(self) -> None:
        """Reset frequency limits to original measurement range."""
        if self.last_measurement is None:
            return

        # Clear the frequency input fields
        self.query_one("#input_plot_freq_min", Input).value = ""
        self.query_one("#input_plot_freq_max", Input).value = ""

        # Redraw plot with full frequency range
        await self._update_results(
            self.last_measurement["freqs"],
            self.last_measurement["sparams"],
            self.last_measurement["output_path"],
        )

    @on(Button.Pressed, "#btn_reset_y_limits")
    async def handle_reset_y_limits(self) -> None:
        """Reset Y-axis limits to auto-detected range."""
        if self.last_measurement is None:
            return

        # Clear the Y-axis input fields
        self.query_one("#input_plot_y_min", Input).value = ""
        self.query_one("#input_plot_y_max", Input).value = ""

        # Redraw plot with auto Y range
        await self._update_results(
            self.last_measurement["freqs"],
            self.last_measurement["sparams"],
            self.last_measurement["output_path"],
        )

    @on(Button.Pressed, "#btn_open_output")
    def handle_open_output(self) -> None:
        """Open the output file location in file explorer."""
        if not self.last_output_path or not os.path.exists(self.last_output_path):
            self.log_message("Output file not found", "error")
            return

        try:
            file_path = os.path.abspath(self.last_output_path)
            folder_path = os.path.dirname(file_path)

            system = platform.system()
            if system == "Windows":
                # Open folder and select file
                subprocess.run(["explorer", "/select,", file_path])
            elif system == "Darwin":  # macOS
                # Open folder and select file
                subprocess.run(["open", "-R", file_path])
            elif system == "Linux":
                # Try various file managers
                # First try to select the file if file manager supports it
                try:
                    subprocess.run(
                        [
                            "dbus-send",
                            "--print-reply",
                            "--dest=org.freedesktop.FileManager1",
                            "/org/freedesktop/FileManager1",
                            "org.freedesktop.FileManager1.ShowItems",
                            f"array:string:file://{file_path}",
                            "string:",
                        ]
                    )
                except Exception:
                    # Fall back to just opening the folder
                    for fm in ["xdg-open", "nautilus", "dolphin", "thunar", "nemo"]:
                        try:
                            subprocess.run([fm, folder_path])
                            break
                        except FileNotFoundError:
                            continue

            self.log_message(f"Opened: {folder_path}", "success")
        except Exception as e:
            self.log_message(f"Failed to open file location: {e}", "error")

    def _is_tools_tab_active(self) -> bool:
        """
        Determine whether the Tools tab is the currently active tab.

        If the TabbedContent lookup fails or any error occurs while querying, this returns False.

        Returns:
            `True` if the Tools tab is active, `False` otherwise.
        """
        try:
            return self.query_one(TabbedContent).active == "tab_tools"
        except Exception:
            return False

    def on_resize(self, event) -> None:
        """
        Handle window resize events and schedule debounced UI updates.

        If a measurement is loaded, cancels any pending main-plot timer and schedules a debounced redraw of the results plot after 300 milliseconds. If the Tools tab is active and a measurement exists, cancels any pending tools-plot timer and schedules a debounced tools-plot refresh after 300 milliseconds. If an output path is set, cancels any pending path-update timer and schedules a debounced update of the displayed output-file label after 300 milliseconds.

        Parameters:
            event: The resize event object provided by the Textual framework.
        """
        if self.last_measurement is not None:
            # Cancel any pending resize timer
            if self._resize_timer is not None:
                self._resize_timer.stop()
            # Debounce: redraw only after 300ms of no resize events
            self._resize_timer = self.set_timer(0.3, self._redraw_plot)

        # Debounce tools plot redraw — only when Tools tab is visible
        if self.last_measurement is not None and self._is_tools_tab_active():
            if self._tools_resize_timer is not None:
                self._tools_resize_timer.stop()
            self._tools_resize_timer = self.set_timer(0.3, self._refresh_tools_plot)

        # Update output file path label
        if self.last_output_path is not None:
            if self._path_update_timer is not None:
                self._path_update_timer.stop()
            self._path_update_timer = self.set_timer(
                0.3, self._update_output_path_label
            )

    async def _delayed_redraw_plot(self) -> None:
        """Delayed plot redraw to ensure proper container sizing."""
        if self.last_measurement is not None:
            await self._update_results(
                self.last_measurement["freqs"],
                self.last_measurement["sparams"],
                self.last_measurement["output_path"],
            )

    async def _redraw_plot(self) -> None:
        """
        Trigger an update of the displayed measurement plot using the stored last measurement.

        If no last measurement is available this method does nothing.
        """
        if self.last_measurement is not None:
            await self._update_results(
                self.last_measurement["freqs"],
                self.last_measurement["sparams"],
                self.last_measurement["output_path"],
            )

    # ------------------------------------------------------------------ #
    # Tools tab helpers
    # ------------------------------------------------------------------ #

    def _get_tools_trace(self) -> str:
        """Return the currently selected tools trace."""
        return get_tools_trace(self)

    def _apply_tool_ui(self) -> None:
        """Update the tools button UI to reflect the active tool."""
        apply_tool_ui(self)

    def _set_active_tool(self, tool_name: str) -> None:
        """Activate or deactivate a tools panel by name."""
        set_active_tool(self, tool_name)

    def _get_distortion_comp_enabled(self) -> list[bool]:
        """Return enabled state for distortion component overlays."""
        return get_distortion_comp_enabled(self)

    async def _rebuild_tools_params(self) -> None:
        """Rebuild the tools parameter panel UI."""
        await rebuild_tools_params(self)

    async def _delayed_redraw_tools_plot(self) -> None:
        """Trigger a deferred tools plot refresh after layout settles."""
        await delayed_redraw_tools_plot(self)

    async def _delayed_tools_refresh(self) -> None:
        """Debounced handler: refresh tools plot then run computation."""
        await delayed_tools_refresh(self)

    async def _refresh_results_plot(self) -> None:
        """Re-render the Measurement tab plot from cached data (e.g. after a theme change)."""
        if self.last_measurement is None:
            return
        await self._update_results(
            self.last_measurement["freqs"],
            self.last_measurement["sparams"],
            self.last_measurement["output_path"],
        )

    def _sync_measurement_notes_from_editor(self) -> None:
        """Copy the current notes editor contents into app and measurement state."""
        editor = self.query_one("#measurement_notes_editor", TextArea)
        self.measurement_notes = editor.text
        if self.last_measurement is not None:
            self.last_measurement["notes"] = self.measurement_notes

    def _load_measurement_notes_into_editor(self) -> None:
        """Load cached measurement notes into the notes editor."""
        editor = self.query_one("#measurement_notes_editor", TextArea)
        notes = self.measurement_notes
        if self.last_measurement is not None:
            notes = str(self.last_measurement.get("notes", notes))
        self.measurement_notes = notes
        editor.text = notes
        self._refresh_measurement_notes_preview()

    def _refresh_measurement_notes_preview(self) -> None:
        """Render the current raw markdown notes into the preview pane."""
        editor = self.query_one("#measurement_notes_editor", TextArea)
        preview = self.query_one("#measurement_notes_preview", Markdown)
        notes = editor.text.strip()
        self.measurement_notes = editor.text
        if self.last_measurement is not None:
            self.last_measurement["notes"] = self.measurement_notes
        if notes:
            preview.update(self.measurement_notes)
        else:
            preview.update("No notes yet")

    async def _refresh_tools_plot(self) -> None:
        """Render the Tools tab plot for the currently selected trace."""
        await refresh_tools_plot(self)

    def _run_tools_computation(self) -> None:
        """Run the currently selected tools module and populate the results display."""
        run_tools_computation(self)

    def _update_output_path_label(self) -> None:
        """
        Update the output file label in the UI to a truncated path that fits the available container width.

        If `self.last_output_path` is None the method returns immediately. The method measures the widths of
        the output container and the export/show buttons (#btn_open_output, #btn_export_touchstone,
        #btn_export_csv, #btn_export_png, #btn_export_svg), computes the remaining width, and uses
        `truncate_path_intelligently` to produce a shortened path prefixed with "📁 ". If the computed
        available width is too small (<= 10) the label is not updated. The method ignores exceptions raised
        while querying widgets (e.g., widgets not yet mounted).
        """
        if self.last_output_path is None:
            return

        try:
            output_file_label = self.query_one("#output_file_label", Static)
            container = self.query_one("#output_file_container")

            # Calculate actual button widths
            btn_show = self.query_one("#btn_open_output", Button)
            btn_touchstone = self.query_one("#btn_export_touchstone", Button)
            btn_csv = self.query_one("#btn_export_csv", Button)
            btn_png = self.query_one("#btn_export_png", Button)
            btn_svg = self.query_one("#btn_export_svg", Button)

            # Sum of button widths + margins (each button has margin-left: 1)
            buttons_width = (
                btn_show.size.width
                + btn_touchstone.size.width
                + btn_csv.size.width
                + btn_png.size.width
                + btn_svg.size.width
                + 10  # 5 buttons × 2 margin (left+right spacing)
            )

            # Available width for path = container width - buttons - buffer
            available_width = container.size.width - buttons_width - 4

            if available_width > 10:
                truncated_path = truncate_path_intelligently(
                    str(self.last_output_path), available_width
                )
                output_file_label.update(f"📁 {truncated_path}")
        except Exception:
            # If query fails (widget not yet mounted), ignore
            pass

    @on(
        Checkbox.Changed,
        "#check_plot_s11, #check_plot_s21, #check_plot_s12, #check_plot_s22",
    )
    async def on_plot_param_change(self, event: Checkbox.Changed) -> None:
        """Handle S-parameter plot checkbox change."""
        if self.last_measurement is None:
            return

        # Redraw plot with selected parameters
        await self._update_results(
            self.last_measurement["freqs"],
            self.last_measurement["sparams"],
            self.last_measurement["output_path"],
        )

    @on(Select.Changed, "#select_plot_type")
    async def on_plot_type_change(self, event: Select.Changed) -> None:
        """Handle plot type change."""
        if self.last_measurement is None:
            return

        # Redraw plot with new type
        await self._update_results(
            self.last_measurement["freqs"],
            self.last_measurement["sparams"],
            self.last_measurement["output_path"],
        )

    @on(TextArea.Changed, "#measurement_notes_editor")
    def handle_measurement_notes_change(self, event: TextArea.Changed) -> None:
        """Track raw markdown notes entered for the current measurement."""
        del event
        self._sync_measurement_notes_from_editor()
        self._refresh_measurement_notes_preview()

    @on(Button.Pressed, "#btn_apply_limits")
    async def handle_apply_limits(self) -> None:
        """
        Reapply the current frequency and Y-axis limits to the cached measurement and refresh the results plot.

        If a cached measurement exists in self.last_measurement, calls _update_results with its frequencies, S-parameters, and output path to redraw the plot using the UI's current limit settings. Does nothing when no cached measurement is available.
        """
        if self.last_measurement is None:
            return

        # Redraw plot with new limits
        await self._update_results(
            self.last_measurement["freqs"],
            self.last_measurement["sparams"],
            self.last_measurement["output_path"],
        )

    # ------------------------------------------------------------------ #
    # Tools tab event handlers
    # ------------------------------------------------------------------ #

    @on(Button.Pressed, "#btn_tool_measure")
    def handle_tool_measure_pressed(self) -> None:
        """Activate or deactivate the cursor tool."""
        tools_logic.handle_tool_measure_pressed(self)

    @on(Button.Pressed, "#btn_tool_distortion")
    def handle_tool_distortion_pressed(self) -> None:
        """Toggle the Distortion tool."""
        tools_logic.handle_tool_distortion_pressed(self)

    @on(Input.Changed, "#input_tools_cursor1, #input_tools_cursor2")
    def handle_tools_cursor_change(self, event: Input.Changed) -> None:
        """Update internal cursor frequencies from the tools input fields."""
        del event
        tools_logic.handle_tools_cursor_change(self)

    @on(Checkbox.Changed, ".distortion-comp-check")
    def handle_distortion_comp_change(self, event: Checkbox.Changed) -> None:
        """Refresh tools plot when a distortion component overlay checkbox changes."""
        del event
        tools_logic.handle_distortion_comp_change(self)

    @on(RadioSet.Changed, "#tools_trace_radioset")
    async def handle_tools_trace_changed(self, event: RadioSet.Changed) -> None:
        """Update tools plot and results when the trace selection changes."""
        del event
        await tools_logic.handle_tools_trace_changed(self)

    @on(Select.Changed, "#select_tools_plot_type")
    async def on_tools_plot_type_change(self, event: Select.Changed) -> None:
        """Handle changes to the tools plot type by refreshing the tools plot and recomputing results."""
        del event
        await tools_logic.on_tools_plot_type_change(self)

    # ------------------------------------------------------------------ #

    async def _update_results(self, freqs, sparams, output_path):
        """
        Render measurement results into the Results tab and update related UI state.

        Renders the provided frequency and S-parameter measurement data into the Results
        panel using the currently selected plot backend and UI options. Updates input
        placeholders, applies optional frequency and Y-axis filtering from the UI,
        generates and displays either a terminal or image plot (Smith or magnitude/phase),
        updates cached plot/output paths, and enables export/open controls.

        Parameters:
            freqs (array-like): Frequencies in Hz for each measurement point, in ascending order.
            sparams (dict): Mapping from S-parameter name (e.g., "S11") to a tuple
                (magnitude_db_array, phase_deg_array), where arrays are aligned with `freqs`.
            output_path (pathlike | str): Path where measurement results (Touchstone or related)
                were written; used to update the output file display and export controls.
        """
        self.log_message(
            f"_update_results called with {len(freqs)} freqs, {len(sparams)} sparams",
            "debug",
        )

        # Get frequency unit from measurement data
        measurement = self.last_measurement or {}
        measurement_freq_unit = measurement.get("freq_unit", "MHz")
        freq_unit = (
            measurement_freq_unit if isinstance(measurement_freq_unit, str) else "MHz"
        )
        unit_multipliers = {"Hz": 1, "kHz": 1e3, "MHz": 1e6, "GHz": 1e9}
        multiplier = unit_multipliers.get(freq_unit, 1e6)

        # Update input placeholders with original values and unit
        freq_min_orig = freqs[0] / multiplier
        freq_max_orig = freqs[-1] / multiplier
        self.query_one("#input_plot_freq_min", Input).placeholder = (
            f"Min: {freq_min_orig:.2f} {freq_unit}"
        )
        self.query_one("#input_plot_freq_max", Input).placeholder = (
            f"Max: {freq_max_orig:.2f} {freq_unit}"
        )

        # Apply frequency filtering based on user input
        freq_min_str = self.query_one("#input_plot_freq_min", Input).value.strip()
        freq_max_str = self.query_one("#input_plot_freq_max", Input).value.strip()

        # Filter frequencies if limits are specified
        if freq_min_str or freq_max_str:
            try:
                # Convert from current unit to Hz
                freq_min_hz = (
                    float(freq_min_str) * multiplier if freq_min_str else freqs[0]
                )
                freq_max_hz = (
                    float(freq_max_str) * multiplier if freq_max_str else freqs[-1]
                )

                # Find indices within range
                mask = (freqs >= freq_min_hz) & (freqs <= freq_max_hz)
                if not mask.any():
                    # No points in range, use full range
                    filtered_freqs = freqs
                    filtered_sparams = sparams
                else:
                    filtered_freqs = freqs[mask]
                    # Filter all S-parameters
                    filtered_sparams = {}
                    for param, (mag, phase) in sparams.items():
                        filtered_sparams[param] = (mag[mask], phase[mask])
            except (ValueError, IndexError):
                # Invalid input, use full range
                filtered_freqs = freqs
                filtered_sparams = sparams
        else:
            # No filtering
            filtered_freqs = freqs
            filtered_sparams = sparams

        freq_range = (
            f"{filtered_freqs[0] / 1e6:.1f} - {filtered_freqs[-1] / 1e6:.1f} MHz"
        )

        # Calculate min, max, avg for all S-parameters (using filtered data)
        stats = {}
        for param in ["S11", "S21", "S12", "S22"]:
            if param in filtered_sparams:
                mag = filtered_sparams[param][0]
                stats[param] = {"min": mag.min(), "max": mag.max(), "avg": mag.mean()}

        # Get selected parameters for plot from checkboxes
        plot_params = []
        if (
            self.query_one("#check_plot_s11", Checkbox).value
            and "S11" in filtered_sparams
        ):
            plot_params.append("S11")
        if (
            self.query_one("#check_plot_s21", Checkbox).value
            and "S21" in filtered_sparams
        ):
            plot_params.append("S21")
        if (
            self.query_one("#check_plot_s12", Checkbox).value
            and "S12" in filtered_sparams
        ):
            plot_params.append("S12")
        if (
            self.query_one("#check_plot_s22", Checkbox).value
            and "S22" in filtered_sparams
        ):
            plot_params.append("S22")

        # Clear and rebuild results container
        results_container = self.query_one("#results_container", Container)
        await results_container.remove_children()

        # Update Results panel title with measurement info
        # Show filtered point count and original count if different
        if len(filtered_freqs) != len(freqs):
            point_info = f"{len(filtered_freqs)}/{len(freqs)} pts"
        else:
            point_info = f"{len(freqs)} pts"

        results_container.border_title = f"Results [{freq_range} | {point_info}]"

        # Plot S-parameters
        if plot_params:
            # Get plot settings from UI
            plot_type = self.query_one("#select_plot_type", Select).value
            plot_backend = self.settings.plot_backend

            # Determine plot title
            if plot_type == "magnitude":
                plot_title = "S-Parameter Magnitude"
                y_label = "Magnitude (dB)"
            elif plot_type == "phase":
                plot_title = "S-Parameter Phase (Unwrapped)"
                y_label = "Phase (degrees)"
            elif plot_type == "phase_raw":
                plot_title = "S-Parameter Phase (Raw)"
                y_label = "Phase (degrees)"
            elif plot_type == "smith":
                plot_title = "Smith Chart"
                y_label = ""
            else:
                plot_title = "S-Parameter"
                y_label = ""

            # Calculate Y-axis limits (used by both backends)
            y_min_str = self.query_one("#input_plot_y_min", Input).value.strip()
            y_max_str = self.query_one("#input_plot_y_max", Input).value.strip()
            user_y_min = None
            user_y_max = None

            if y_min_str:
                try:
                    user_y_min = float(y_min_str)
                except ValueError:
                    pass
            if y_max_str:
                try:
                    user_y_max = float(y_max_str)
                except ValueError:
                    pass

            # Calculate auto Y-axis limits for placeholders
            # Collect all data based on plot type (use filtered data)
            all_y_data = []
            for param in plot_params:
                if plot_type == "magnitude":
                    param_data = filtered_sparams[param][0]
                elif plot_type == "phase":
                    param_data = unwrap_phase(filtered_sparams[param][1])
                else:  # phase_raw
                    param_data = filtered_sparams[param][1]
                all_y_data.append(param_data)

            # Calculate auto limits
            auto_y_min = None
            auto_y_max = None
            if all_y_data and plot_type != "smith":
                combined_data = np.concatenate(all_y_data)
                auto_y_min, auto_y_max = calculate_plot_range_with_outlier_filtering(
                    combined_data, outlier_percentile=1.0, safety_margin=0.05
                )

                # Update input placeholders with auto-detected values
                if user_y_min is None:
                    self.query_one("#input_plot_y_min", Input).placeholder = (
                        f"Min: {auto_y_min:.1f} dB"
                        if plot_type == "magnitude"
                        else f"Min: {auto_y_min:.1f}°"
                    )
                if user_y_max is None:
                    self.query_one("#input_plot_y_max", Input).placeholder = (
                        f"Max: {auto_y_max:.1f} dB"
                        if plot_type == "magnitude"
                        else f"Max: {auto_y_max:.1f}°"
                    )
            else:
                # Smith chart or no data - set generic placeholders
                self.query_one("#input_plot_y_min", Input).placeholder = (
                    "Min (N/A for Smith)"
                )
                self.query_one("#input_plot_y_max", Input).placeholder = (
                    "Max (N/A for Smith)"
                )

            # Check if smith chart is selected
            if plot_type == "smith" and plot_backend == "terminal":
                # Smith chart not supported in terminal mode
                await results_container.mount(
                    Static(
                        "\n[bold yellow]Smith Chart not available in terminal mode[/bold yellow]\n"
                        "[dim]Please switch to Image backend to view Smith charts.[/dim]",
                        markup=True,
                    )
                )
            elif plot_backend == "terminal":
                # Use plotext for terminal-based plotting
                from textual_plotext import PlotextPlot

                plot_widget = PlotextPlot()
                await results_container.mount(plot_widget)

                # Configure the plot using the plt property
                plt_term = plot_widget.plt
                plt_term.clf()

                # Plot data as line with braille markers (use filtered data)
                freq_mhz = filtered_freqs / 1e6
                plot_colors = get_plot_colors(self.get_css_variables())

                # Calculate Y limits first (before plotting)
                if all_y_data and auto_y_min is not None and auto_y_max is not None:
                    y_min = user_y_min if user_y_min is not None else auto_y_min
                    y_max = user_y_max if user_y_max is not None else auto_y_max
                else:
                    y_min = None
                    y_max = None

                # Plot each parameter, filtering out traces with no visible data
                for param in plot_params:
                    # Select data based on plot type (use filtered data)
                    if plot_type == "magnitude":
                        param_data = filtered_sparams[param][0]
                    elif plot_type == "phase":
                        param_data = unwrap_phase(filtered_sparams[param][1])
                    else:  # phase_raw
                        param_data = filtered_sparams[param][1]

                    # Skip empty traces (can happen if all data filtered out)
                    if len(param_data) == 0:
                        continue

                    # If Y limits are set, check if trace has any visible data
                    # This prevents plotext from crashing when rendering legend
                    # for traces that are completely outside the plot range
                    if y_min is not None and y_max is not None:
                        # Check if any data points fall within Y range
                        if not np.any((param_data >= y_min) & (param_data <= y_max)):
                            # Skip this trace - it's completely outside Y range
                            continue

                    plt_term.plot(
                        freq_mhz.tolist(),
                        param_data.tolist(),
                        label=param,
                        marker="braille",
                        color=plot_colors["traces_rgb"].get(param, (255, 255, 255)),
                    )

                # Apply Y-axis limits after plotting
                if y_min is not None and y_max is not None:
                    plt_term.ylim(y_min, y_max)

                # Labels and formatting
                plt_term.title(plot_title)
                plt_term.xlabel("Frequency (MHz)")
                plt_term.ylabel(y_label)
                plt_term.theme("clear")

                # Refresh the plot widget to display
                plot_widget.refresh()

            else:  # image backend
                # Generate matplotlib plot at fixed high resolution
                # This avoids regenerating on resize and ensures quality
                plot_file = self.plot_temp_dir / "current_plot.png"

                # Log for debugging
                self.log_message(f"Generating plot at: {plot_file}", "debug")

                # Fixed high-resolution dimensions for quality
                # Target: 1080p (1920x1080) at high DPI
                # This gives good quality without excessive memory usage
                render_scale = 1
                dpi = 150 * render_scale  # 150 DPI

                # For Smith charts, use square dimensions
                if plot_type == "smith":
                    # Use 1920x1920 for high quality square Smith chart
                    fixed_width_px = 1920
                    fixed_height_px = 1920
                else:
                    # For other plots, use 16:9 aspect ratio
                    fixed_width_px = 1920  # Full HD width
                    fixed_height_px = 1080  # Full HD height (16:9 aspect)

                px_w = fixed_width_px
                px_h = fixed_height_px

                plot_colors = get_plot_colors(self.get_css_variables())

                # Use Smith chart plotter if smith type selected (use filtered data)
                if plot_type == "smith":
                    create_smith_chart(
                        filtered_freqs,
                        filtered_sparams,
                        plot_params,
                        plot_file,
                        dpi=dpi,
                        pixel_width=px_w,
                        pixel_height=px_h,
                        transparent=True,
                        render_scale=render_scale,
                        colors=plot_colors,
                    )
                else:
                    create_matplotlib_plot(
                        filtered_freqs,
                        filtered_sparams,
                        plot_params,
                        str(plot_type),
                        plot_file,
                        dpi=dpi,
                        pixel_width=px_w,
                        pixel_height=px_h,
                        transparent=True,
                        render_scale=render_scale,
                        colors=plot_colors,
                        y_min=user_y_min,
                        y_max=user_y_max,
                    )

                # Store plot path for export
                self.last_plot_path = plot_file

                # Verify file was created
                if not plot_file.exists():
                    self.log_message(
                        f"Error: Plot file not created at {plot_file}", "error"
                    )
                    await results_container.mount(
                        Static(
                            "[red]Failed to generate plot image[/red]",
                            markup=True,
                        )
                    )
                else:
                    self.log_message(
                        f"Plot file created: {plot_file.stat().st_size} bytes", "debug"
                    )

                    # Display image using textual-image widget
                    # Auto-detects Kitty/iTerm2/Sixel and falls back to Unicode
                    try:
                        if not TEXTUAL_IMAGE_AVAILABLE:
                            raise ImportError("textual-image not available")

                        # Force terminal graphics protocol detection
                        terminal = os.environ.get("TERM", "")
                        term_program = os.environ.get("TERM_PROGRAM", "")
                        kitty_window_id = os.environ.get("KITTY_WINDOW_ID", "")

                        self.log_message(
                            f"Terminal detection: TERM='{terminal}', TERM_PROGRAM='{term_program}', KITTY_WINDOW_ID='{kitty_window_id}'",
                            "debug",
                        )

                        # Set environment hints for better graphics detection
                        if (
                            "ghostty" in term_program.lower()
                            or "kitty" in terminal.lower()
                        ):
                            # Force Kitty graphics protocol detection
                            os.environ.setdefault("KITTY_GRAPHICS_PROTOCOL", "1")
                            self.log_message("Forcing Kitty graphics protocol", "debug")

                        # Create image widget - accepts Path or str
                        self.log_message(
                            f"Creating image widget for: {plot_file}", "debug"
                        )

                        img_widget = ImageWidget(str(plot_file))

                        # Calculate display size based on available container width
                        # and preserve the actual aspect ratio of the generated plot
                        container_w = results_container.content_size.width

                        # Debug the values
                        self.log_message(
                            f"Container width: {container_w}, px_w: {px_w}, px_h: {px_h}",
                            "debug",
                        )

                        if container_w and container_w > 10 and px_w and px_h:
                            # Use most of the width with small padding
                            display_w = max(40, container_w - 4)

                            # Calculate aspect ratio from pixel dimensions
                            # Terminal cells: ~8px wide, ~16px tall (2:1 ratio)
                            # For a square image (1920x1920), this gives aspect_ratio = 2.0
                            # which correctly displays as square in terminal (100w x 50h cells)
                            img_w_cells = px_w / 8
                            img_h_cells = px_h / 16
                            aspect_ratio = img_w_cells / img_h_cells

                            # Derive height from width to preserve aspect ratio
                            display_h = int(display_w / aspect_ratio)

                            img_widget.styles.width = display_w
                            img_widget.styles.height = display_h

                            self.log_message(
                                f"Using proper sizing: {display_w}x{display_h}", "debug"
                            )
                        else:
                            # Fallback if container size unknown - use better fallback
                            fallback_w = 120
                            fallback_h = 60
                            img_widget.styles.width = fallback_w
                            img_widget.styles.height = fallback_h

                            self.log_message(
                                f"Using fallback sizing: {fallback_w}x{fallback_h} (container_w={container_w}, px_w={px_w}, px_h={px_h})",
                                "debug",
                            )

                        self.log_message(
                            "Mounting image widget...",
                            "debug",
                        )
                        await results_container.mount(img_widget)
                        self.log_message("Image widget mounted successfully", "debug")
                    except Exception as e:
                        self.log_message(f"Failed to display image: {e}", "error")
                        # Fallback: show file location
                        await results_container.mount(
                            Static(
                                f"[yellow]Plot generated but display failed[/yellow]\n"
                                f"[cyan]File: {plot_file}[/cyan]\n"
                                f"[dim]Error: {e}[/dim]",
                                markup=True,
                            )
                        )
        else:
            await results_container.mount(
                Static(
                    "\n[bold yellow]No parameters selected for plotting[/bold yellow]",
                    markup=True,
                )
            )

        # S-Parameters statistics using DataTable (after plot)
        # Disabled for now - feels redundant with plot data
        # table = DataTable(zebra_stripes=True, show_header=True, show_cursor=False)
        # table.add_column("Param")
        # table.add_column("Min (dB)")
        # table.add_column("Max (dB)")
        # table.add_column("Avg (dB)")

        # for param in ["S11", "S21", "S12", "S22"]:
        #     if param in stats:
        #         table.add_row(
        #             param,
        #             f"{stats[param]['min']:.2f}",
        #             f"{stats[param]['max']:.2f}",
        #             f"{stats[param]['avg']:.2f}",
        #         )

        # table.styles.height = len(stats) + 1  # Rows + header only
        # table.styles.margin = (0, 0)
        # await results_container.mount(table)

        # Update output file panel with intelligent truncation
        self.last_output_path = output_path
        self._update_output_path_label()

        # Enable export buttons
        self.query_one("#btn_open_output", Button).disabled = False
        self.query_one("#check_minimal_export", Button).disabled = False
        self.query_one("#btn_export_touchstone", Button).disabled = False
        self.query_one("#btn_export_csv", Button).disabled = False
        self.query_one("#btn_export_png", Button).disabled = False
        self.query_one("#btn_export_svg", Button).disabled = False
        self._refresh_export_button_labels()


def run_gui(test_updates: bool = False, dev_mode: bool = False):
    """Run GUI mode with proper imports."""
    from .config.migration import migrate_legacy_config

    migration_message = migrate_legacy_config()
    app = VNAApp(
        test_updates=test_updates,
        dev_mode=dev_mode,
        migration_message=migration_message,
    )
    app.run()


def main():
    """Main entry point."""
    from .cli import create_cli_parser, run_cli_measurement

    parser = create_cli_parser()
    args = parser.parse_args()

    if args.now:
        # CLI mode - quick measurement
        return run_cli_measurement(args)
    else:
        # GUI mode
        run_gui(test_updates=args.test_updates, dev_mode=args.dev)
        return 0


if __name__ == "__main__":
    sys.exit(main())
