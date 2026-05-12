"""
Measurement worker thread for non-blocking VNA operations.

This module provides a clean thread-based architecture for running VNA measurements
without blocking the UI thread. Uses standard library queue.Queue for thread-safe
communication.
"""

import queue
import threading
import traceback
from dataclasses import asdict, dataclass
from enum import Enum
from pathlib import Path
from typing import Any, cast

import matplotlib
import numpy as np

matplotlib.use("Agg")

from matplotlib import pyplot as plt

from .drivers import (
    StatusCapableDriver,
    TriggerStateDriver,
    VNABase,
    VNAConfig,
    detect_vna_driver,
)
from .export import (
    CsvExporter,
    build_image_export_metadata,
    embed_png_metadata,
    embed_svg_metadata,
    read_png_metadata,
    read_svg_metadata,
)
from .gui.plotting import (
    DISTORTION_OVERLAY_LABELS,
    DISTORTION_OVERLAY_STYLES,
    create_matplotlib_plot,
    create_smith_chart,
    unwrap_phase,
)
from .tools import DistortionTool, MeasureTool
from .utils import LoggingVNAWrapper
from .utils.touchstone import TouchstoneExporter


class MessageType(Enum):
    """Message types for worker communication."""

    # Commands (UI -> Worker)
    CONNECT = "connect"
    DISCONNECT = "disconnect"
    IMPORT = "import"
    READ_PARAMS = "read_params"
    MEASURE = "measure"
    STATUS_POLL = "status_poll"
    SHUTDOWN = "shutdown"
    SET_DEBUG_SCPI = "set_debug_scpi"
    EXPORT = "export"
    SAVE_BACK = "save_back"
    TOOLS_RENDER = "tools_render"
    TOOLS_COMPUTE = "tools_compute"

    # Responses (Worker -> UI)
    CONNECTED = "connected"
    DISCONNECTED = "disconnected"
    IMPORT_COMPLETE = "import_complete"
    IMPORT_PROGRESS = "import_progress"
    PARAMS_READ = "params_read"
    MEASUREMENT_COMPLETE = "measurement_complete"
    STATUS_UPDATE = "status_update"
    SCPI_ERROR_UPDATE = "scpi_error_update"
    ERROR = "error"
    PROGRESS = "progress"
    LOG = "log"  # Log message (TX/RX/info)


@dataclass
class Message:
    """Message structure for inter-thread communication."""

    type: MessageType
    data: Any = None
    error: str | None = None


@dataclass
class ProgressUpdate:
    """Progress update data."""

    message: str
    progress_pct: float
    job_id: int | None = None


@dataclass
class BackgroundJob:
    """Background job completion payload."""

    job_id: int
    operation: str
    progress: float
    result: Any = None


@dataclass
class ImportRequest:
    """Import request data."""

    file_path: str
    restore_measurement: bool


@dataclass
class ImportResult:
    """Imported setup/measurement state restored from a file."""

    setup: dict[str, object]
    measurement: dict[str, object]
    notes: str
    paths: dict[str, str | None]


@dataclass
class MeasurementResult:
    """Measurement result data."""

    frequencies: np.ndarray
    sparams: dict[str, tuple[np.ndarray, np.ndarray]]


@dataclass
class ParamsResult:
    """VNA parameters read result."""

    start_freq: float
    stop_freq: float
    points: int
    averaging_enabled: bool
    averaging_count: int


@dataclass
class StatusResult:
    """Live VNA status for the status bar."""

    cal_enabled: bool | None = None
    cal_type: str | None = None
    smoothing_enabled: bool | None = None
    smoothing_aperture: float | None = None
    if_bandwidth_hz: float | None = None
    port_power_dbm: float | None = None
    trigger_source: str | None = None


@dataclass
class LogMessage:
    """Log message data."""

    message: str
    level: str  # "tx", "rx", "info", "progress", etc.


class BackgroundJobCancelledError(RuntimeError):
    """Raised when a background job has been superseded or cancelled."""


def _render_plot_image_snapshot(
    freqs: np.ndarray,
    sparams: dict[str, tuple[np.ndarray, np.ndarray]],
    plot_params: tuple[str, ...],
    plot_type: str,
    output_path: Path,
    dpi: int,
    pixel_width: int,
    pixel_height: int,
    render_scale: int,
    colors: dict,
    y_min: float | None,
    y_max: float | None,
    plot_data: dict[str, np.ndarray] | None = None,
) -> None:
    """Render a measurement plot image snapshot from immutable inputs."""
    if plot_type == "smith":
        create_smith_chart(
            freqs,
            sparams,
            list(plot_params),
            output_path,
            dpi=dpi,
            pixel_width=pixel_width,
            pixel_height=pixel_height,
            transparent=True,
            render_scale=render_scale,
            colors=colors,
        )
    else:
        create_matplotlib_plot(
            freqs,
            sparams,
            list(plot_params),
            plot_type,
            output_path,
            dpi=dpi,
            pixel_width=pixel_width,
            pixel_height=pixel_height,
            transparent=True,
            render_scale=render_scale,
            colors=colors,
            y_min=y_min,
            y_max=y_max,
            plot_data=plot_data,
        )


def _write_touchstone_save_back(
    target_path: str,
    measurement_notes: str,
    metadata: dict[str, object],
) -> str:
    """Rewrite notes and TINA metadata into an existing Touchstone file."""
    resolved = str(Path(target_path).resolve())

    with open(resolved, encoding="utf-8") as handle:
        original_text = handle.read()

    # Early validation: fail fast on malformed Touchstone files before modifying them.
    TouchstoneExporter.import_with_metadata(resolved)

    lines = original_text.splitlines()
    header_lines: list[str] = []
    option_and_data_lines: list[str] = []
    option_line_seen = False
    header_separator_seen = False
    tina_block_begins = frozenset({"TINA NOTES BEGIN", "TINA METADATA BEGIN"})
    tina_block_ends = frozenset({"TINA NOTES END", "TINA METADATA END"})
    in_tina_block = False

    for raw in lines:
        line = raw.rstrip("\n")
        stripped = line.strip()

        if not option_line_seen and stripped.startswith("#"):
            option_line_seen = True
            option_and_data_lines.append(line)
            continue

        if not option_line_seen:
            if stripped.startswith("!"):
                if not header_separator_seen:
                    header_lines.append(line)
                    if stripped == "!":
                        header_separator_seen = True
                continue

            if not stripped:
                if not header_separator_seen:
                    header_lines.append(line)
                    header_separator_seen = True
                continue

            option_line_seen = True
            option_and_data_lines.append(line)
            continue

        # After the option line: skip TINA-managed blocks but preserve other comments.
        if stripped.startswith("!"):
            inner = stripped[1:].lstrip(" ")
            if inner in tina_block_begins:
                in_tina_block = True
                continue
            if inner in tina_block_ends:
                in_tina_block = False
                continue
            if in_tina_block:
                continue

        option_and_data_lines.append(line)

    if not option_and_data_lines:
        raise ValueError("Touchstone file is missing option or data lines")

    notes_lines = TouchstoneExporter._build_notes_comment_lines(measurement_notes)
    metadata_lines = TouchstoneExporter._serialize_metadata_comment_lines(metadata)

    out_lines: list[str] = []
    if header_lines:
        out_lines.extend(header_lines)
    else:
        out_lines.append("! S-Parameter Data")
    out_lines.extend(notes_lines)
    out_lines.extend(option_and_data_lines)
    out_lines.extend(metadata_lines)

    destination = Path(resolved)
    temp_path = destination.with_name(destination.name + ".tmp")
    with open(temp_path, "w", encoding="utf-8") as handle:
        handle.write("\n".join(out_lines) + "\n")
    temp_path.replace(destination)
    return resolved


def _write_image_save_back(
    target_path: str,
    measurement_notes: str,
    metadata: dict[str, object],
    image_format: str,
) -> str:
    """Embed notes and machine metadata into an existing PNG or SVG export."""
    resolved = str(Path(target_path).resolve())
    image_meta = build_image_export_metadata(
        notes_markdown=measurement_notes,
        machine_settings=metadata,
    )
    if image_format == "png":
        embed_png_metadata(
            resolved,
            notes_markdown=image_meta.notes_markdown,
            machine_settings=image_meta.machine_settings,
        )
    else:
        embed_svg_metadata(
            resolved,
            notes_markdown=image_meta.notes_markdown,
            machine_settings=image_meta.machine_settings,
        )
    return resolved


def _compute_tools_data(
    freqs: np.ndarray,
    sparams: dict[str, tuple[np.ndarray, np.ndarray]],
    trace: str,
    plot_type: str,
) -> tuple[np.ndarray, str, str]:
    """Return the tools trace data and labels for the selected plot type."""
    if trace not in sparams:
        raise ValueError(f"Trace {trace} not available in current measurement")

    mag, phase = sparams[trace]
    if plot_type == "magnitude":
        return mag, "Magnitude (dB)", f"{trace} Magnitude"
    if plot_type == "phase":
        return unwrap_phase(phase), "Phase (°)", f"{trace} Phase (Unwrapped)"
    return phase, "Phase (°)", f"{trace} Phase (Raw)"


def _render_tools_plot_snapshot(
    freqs: np.ndarray,
    sparams: dict[str, tuple[np.ndarray, np.ndarray]],
    trace: str,
    plot_type: str,
    freq_unit: str,
    cursor1_hz: float | None,
    cursor2_hz: float | None,
    active_tool: str | None,
    marker_symbol: str,
    colors: dict[str, Any],
    distortion_components: list[bool],
    tool_result: dict[str, Any] | None,
    output_path: str,
) -> dict[str, Any]:
    """Render the tools image plot from a pure snapshot payload."""
    unit_multipliers = {"Hz": 1, "kHz": 1e3, "MHz": 1e6, "GHz": 1e9}
    multiplier = unit_multipliers.get(freq_unit, 1e6)
    data, y_label, plot_title = _compute_tools_data(freqs, sparams, trace, plot_type)
    freq_axis = freqs / multiplier

    fig, ax = plt.subplots(figsize=(1920 / 150, 1080 / 150))
    try:
        fg = str(colors["fg"])
        grid = str(colors["grid"])
        trace_color = str(colors["trace"])
        cursor1_color = str(colors["cursor1"])
        cursor2_color = str(colors["cursor2"])
        overlay_colors = list(colors.get("distortion_overlays", []))
        marker_map = {"▼": "v", "✕": "x", "○": "o"}
        marker = marker_map.get(marker_symbol, "v")

        fig.patch.set_alpha(0.0)
        ax.set_facecolor("none")
        ax.plot(freq_axis, data, color=trace_color, linewidth=1.5, label=trace)

        if cursor1_hz is not None:
            x1 = cursor1_hz / multiplier
            y1 = float(np.interp(cursor1_hz, freqs, data))
            ax.axvline(x1, color=cursor1_color, linewidth=1.2, zorder=3)
            if active_tool in ("cursor", "distortion"):
                ax.scatter(
                    [x1], [y1], color=cursor1_color, marker=marker, s=80, zorder=5
                )

        if cursor2_hz is not None:
            x2 = cursor2_hz / multiplier
            y2 = float(np.interp(cursor2_hz, freqs, data))
            ax.axvline(x2, color=cursor2_color, linewidth=1.2, zorder=3)
            if active_tool in ("cursor", "distortion"):
                ax.scatter(
                    [x2], [y2], color=cursor2_color, marker=marker, s=80, zorder=5
                )

        if (
            active_tool == "distortion"
            and cursor1_hz is not None
            and cursor2_hz is not None
            and cursor1_hz != cursor2_hz
        ):
            distortion_result = (
                tool_result
                if isinstance(tool_result, dict)
                and str(tool_result.get("tool_name", "")) == "distortion"
                else None
            )
            extra = (
                dict(distortion_result.get("extra", {}))
                if distortion_result is not None
                else {}
            )
            coeffs = extra.get("coeffs")
            x_norm = extra.get("x_norm")
            f_band_hz = extra.get("f_band_hz")
            if (
                isinstance(coeffs, list)
                and isinstance(x_norm, list)
                and isinstance(f_band_hz, list)
            ):
                band_axis = np.array(f_band_hz, dtype=float) / multiplier
                ax.axvspan(
                    min(cursor1_hz, cursor2_hz) / multiplier,
                    max(cursor1_hz, cursor2_hz) / multiplier,
                    alpha=0.08,
                    color=fg,
                    zorder=0,
                )
                x_values = np.array(x_norm, dtype=float)
                for idx in range(min(6, len(coeffs), len(distortion_components))):
                    if not distortion_components[idx]:
                        continue
                    cumulative = np.zeros(idx + 1)
                    cumulative[:] = np.array(coeffs[: idx + 1], dtype=float)
                    cumulative_y = np.polynomial.legendre.legval(x_values, cumulative)
                    color = (
                        overlay_colors[idx]
                        if idx < len(overlay_colors)
                        else trace_color
                    )
                    linestyle = DISTORTION_OVERLAY_STYLES[idx]
                    label = DISTORTION_OVERLAY_LABELS[idx]
                    ax.plot(
                        band_axis,
                        cumulative_y,
                        color=color,
                        linestyle=linestyle,
                        linewidth=1.5,
                        label=label,
                        zorder=4,
                    )

        ax.set_xlabel(f"Frequency ({freq_unit})", color=fg)
        ax.set_ylabel(y_label, color=fg)
        ax.set_title(plot_title, color=fg)
        ax.tick_params(colors=fg)
        ax.grid(True, alpha=0.2, color=grid, linestyle="-", linewidth=0.5)
        for spine in ax.spines.values():
            spine.set_edgecolor(grid)
            spine.set_linewidth(1)

        legend = ax.get_legend()
        if legend is not None:
            legend.remove()
        handles, labels = ax.get_legend_handles_labels()
        if handles:
            legend = ax.legend(edgecolor=grid, labelcolor=fg, fontsize=9)
            legend.get_frame().set_alpha(0.5)
            legend.get_frame().set_facecolor("none")

        fig.tight_layout()
        fig.savefig(
            output_path,
            dpi=150,
            facecolor=fig.get_facecolor(),
            edgecolor="none",
            bbox_inches="tight",
            transparent=True,
        )
    finally:
        plt.close(fig)

    return {"path": output_path, "pixel_width": 1920, "pixel_height": 1080}


class MeasurementWorker:
    """
    Worker thread for VNA measurements.

    Handles all blocking VNA operations in a separate thread, communicating
    with the UI thread via thread-safe queues.

    Usage:
        worker = MeasurementWorker()
        worker.start()

        # Send command
        worker.send_command(MessageType.CONNECT, config)

        # Check for responses
        try:
            msg = worker.get_response(timeout=0.1)
            if msg.type == MessageType.CONNECTED:
                print("Connected!")
        except queue.Empty:
            pass

        # Cleanup
        worker.stop()
    """

    def __init__(self):
        """Initialize worker thread."""
        self._command_queue: queue.Queue = queue.Queue()
        self._response_queue: queue.Queue = queue.Queue()
        self._thread: threading.Thread | None = None
        self._running = False
        self._vna: VNABase | None = None
        self._vna_wrapper: LoggingVNAWrapper | None = None
        self._config: VNAConfig | None = None
        self._measuring = False
        self._debug_scpi = False
        self._job_tokens: dict[int, int] = {}

    def start(self):
        """Start the worker thread."""
        if self._running:
            return

        self._running = True
        self._thread = threading.Thread(target=self._worker_loop, daemon=True)
        self._thread.start()

    def stop(self, timeout: float = 5.0):
        """
        Stop the worker thread gracefully.

        Args:
            timeout: Maximum time to wait for thread shutdown in seconds
        """
        if not self._running:
            return

        self.send_command(MessageType.SHUTDOWN)

        if self._thread:
            self._thread.join(timeout=timeout)
            self._thread = None

        self._running = False

    def send_command(self, msg_type: MessageType, data: Any = None):
        """
        Send command to worker thread.

        Args:
            msg_type: Type of message
            data: Optional data payload
        """
        if msg_type in {
            MessageType.EXPORT,
            MessageType.SAVE_BACK,
            MessageType.TOOLS_RENDER,
            MessageType.TOOLS_COMPUTE,
        } and isinstance(data, dict):
            job_id = data.get("job_id")
            if type(job_id) is int:
                payload = dict(data)
                payload["token"] = self._get_job_token(job_id)
                data = payload
        self._command_queue.put(Message(type=msg_type, data=data))

    def clear_commands(self) -> None:
        """Drain all pending commands from the queue (e.g. before disconnect)."""
        while True:
            try:
                self._command_queue.get_nowait()
            except queue.Empty:
                break

    def get_response(self, timeout: float = 0.1) -> Message:
        """
        Get response from worker thread (non-blocking with timeout).

        Args:
            timeout: Timeout in seconds

        Returns:
            Message from worker

        Raises:
            queue.Empty: If no message available within timeout
        """
        return self._response_queue.get(timeout=timeout)

    def _send_response(
        self, msg_type: MessageType, data: Any = None, error: str | None = None
    ):
        """Send response to UI thread."""
        self._response_queue.put(Message(type=msg_type, data=data, error=error))

    def _send_progress(
        self, message: str, progress_pct: float, job_id: int | None = None
    ):
        """Send progress update to UI thread."""
        self._send_response(
            MessageType.PROGRESS,
            ProgressUpdate(
                message=message,
                progress_pct=progress_pct,
                job_id=job_id,
            ),
        )

    def _send_import_progress(self, message: str, progress_pct: float) -> None:
        """Send import-specific progress updates to UI thread."""
        self._send_response(
            MessageType.IMPORT_PROGRESS,
            ProgressUpdate(message=message, progress_pct=progress_pct, job_id=None),
        )

    def cancel_job(self, job_id: int) -> int:
        """Invalidate the current generation token for a background job id."""
        next_token = self._job_tokens.get(job_id, 0) + 1
        self._job_tokens[job_id] = next_token
        return next_token

    def _get_job_token(self, job_id: int) -> int:
        """Return the current token for a background job id, creating one if needed."""
        token = self._job_tokens.get(job_id)
        if token is None:
            token = 1
            self._job_tokens[job_id] = token
        return token

    def _check_job_cancelled(self, job_id: int, token: int) -> None:
        """Raise if the job token no longer matches the active generation."""
        if self._job_tokens.get(job_id) != token:
            raise BackgroundJobCancelledError(f"Background job {job_id} cancelled")

    def _log(self, message: str, level: str = "info"):
        """Send log message to UI thread."""
        self._send_response(MessageType.LOG, LogMessage(message=message, level=level))

    def _worker_loop(self):
        """Main worker thread loop."""
        while self._running:
            try:
                # Wait for command with timeout to allow checking _running flag
                try:
                    msg = self._command_queue.get(timeout=0.1)
                except queue.Empty:
                    continue

                # Process command
                if msg.type == MessageType.SHUTDOWN:
                    self._handle_shutdown()
                    break
                elif msg.type == MessageType.CONNECT:
                    self._handle_connect(msg.data)
                elif msg.type == MessageType.DISCONNECT:
                    self._handle_disconnect()
                elif msg.type == MessageType.IMPORT:
                    self._handle_import(msg.data)
                elif msg.type == MessageType.READ_PARAMS:
                    self._handle_read_params()
                elif msg.type == MessageType.MEASURE:
                    self._handle_measure(msg.data)
                elif msg.type == MessageType.STATUS_POLL:
                    self._handle_status_poll()
                elif msg.type == MessageType.SET_DEBUG_SCPI:
                    self._handle_set_debug_scpi(msg.data)
                elif msg.type in {
                    MessageType.EXPORT,
                    MessageType.SAVE_BACK,
                    MessageType.TOOLS_RENDER,
                    MessageType.TOOLS_COMPUTE,
                }:
                    self._handle_background_job(msg.type, msg.data)

            except Exception as e:
                # Catch-all error handler
                self._send_response(
                    MessageType.ERROR,
                    error=f"Worker error: {str(e)}\n{traceback.format_exc()}",
                )

    def _handle_connect(self, config: VNAConfig):
        """Handle connection command with automatic driver detection."""
        try:
            self._config = config

            # First, try connecting with a generic driver to get IDN
            # We'll use HPE5071B as the default for now, but this could be
            # made more generic with a basic SCPI connection class
            from .drivers import HPE5071B

            temp_vna = HPE5071B(config)

            # Progress callback
            def on_progress(msg, pct):
                """Forward connection progress to the UI."""
                self._send_progress(msg, pct)

            # Connect to get IDN
            self._send_progress("Connecting...", 10)
            temp_vna.connect(progress_callback=on_progress)
            idn_string = temp_vna.idn

            # Detect the correct driver
            self._send_progress("Detecting VNA type...", 90)
            driver_class = detect_vna_driver(idn_string)

            if driver_class is None:
                # No specific driver found, use the temp connection
                self._log(f"No specific driver found for: {idn_string}", "info")
                self._log("Using default driver", "info")
                self._vna = temp_vna
            elif isinstance(temp_vna, driver_class):
                # Already using the right driver
                self._vna = temp_vna
            else:
                # Need to switch to a different driver
                temp_vna.disconnect()
                self._log(f"Detected: {driver_class.driver_name}", "info")
                self._vna = driver_class(config)
                self._vna.connect(progress_callback=on_progress)

            # Replace the driver reference with its logging wrapper so all calls
            # to self._vna (including higher-level methods like get_status) go
            # through the wrapper automatically via __getattr__.
            # _vna_wrapper is a typed alias to the same object for accessing
            # wrapper-specific attributes (debug, log_tag) without a cast.
            wrapped_vna = LoggingVNAWrapper(
                self._vna, self._log, on_scpi_error=self._on_scpi_error
            )
            self._vna = cast(VNABase, wrapped_vna)
            self._vna_wrapper = wrapped_vna
            self._vna_wrapper.debug = self._debug_scpi

            # Clear the instrument's error queue (logged via wrapper)
            self._vna_wrapper._send_command("*CLS")

            # Log the IDN (already queried during connection)
            self._log("*IDN?", "tx")
            self._log(self._vna.idn, "rx")

            # Send success response with human-readable driver info
            self._send_response(MessageType.CONNECTED, data=self._vna.display_name)

            # Log serial and firmware details not shown in the title
            info = self._vna.idn_info
            details = ", ".join(
                p
                for p in (
                    f"Serial number: {info.serial}" if info.serial else "",
                    f"Firmware: {info.firmware}" if info.firmware else "",
                )
                if p
            )
            if details:
                self._log(details, "info")

        except Exception as e:
            self._send_response(MessageType.ERROR, error=f"Connection failed: {str(e)}")
            self._vna = None
            self._vna_wrapper = None

    def _handle_disconnect(self) -> None:
        """Handle disconnection command."""
        try:
            if self._vna:
                self._vna.disconnect()
                self._vna = None
                self._vna_wrapper = None

            self._send_response(MessageType.DISCONNECTED)

        except Exception as e:
            self._send_response(MessageType.ERROR, error=f"Disconnect failed: {str(e)}")

    def _handle_import(self, data: ImportRequest | dict[str, object] | None) -> None:
        """Handle measurement import entirely in the worker thread."""
        try:
            if isinstance(data, ImportRequest):
                request = data
            elif isinstance(data, dict):
                file_path = data.get("file_path")
                request = ImportRequest(
                    file_path=str(file_path) if file_path is not None else "",
                    restore_measurement=bool(data.get("restore_measurement", False)),
                )
            else:
                raise ValueError("Invalid import request")

            if not request.file_path:
                raise ValueError("No measurement output path provided")

            file_path = Path(request.file_path)
            if not file_path.exists():
                raise FileNotFoundError(
                    f"Measurement output not found: {request.file_path}"
                )

            self._send_import_progress("Resolving import path...", 5)

            suffix = file_path.suffix.lower()
            freqs: np.ndarray | None = None
            sparams: dict[str, tuple[np.ndarray, np.ndarray]] | None = None
            notes_markdown = ""
            imported_metadata: dict[str, object] = {}

            self._send_import_progress("Parsing measurement output...", 20)
            if suffix == ".s2p":
                import_result = TouchstoneExporter.import_with_metadata(str(file_path))
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

            if not isinstance(imported_metadata, dict):
                imported_metadata = {}

            self._send_import_progress("Extracting setup metadata...", 45)
            setup_metadata = imported_metadata.get("setup", {})
            if not isinstance(setup_metadata, dict):
                setup_metadata = {}

            measurement_metadata = imported_metadata.get("measurement", {})
            if not isinstance(measurement_metadata, dict):
                measurement_metadata = {}

            imported_freq_unit = "MHz"
            imported_freq_unit_value = setup_metadata.get("freq_unit")
            if isinstance(imported_freq_unit_value, str):
                imported_freq_unit = imported_freq_unit_value

            if request.restore_measurement:
                self._send_import_progress("Restoring measurement data...", 70)
                if freqs is None or sparams is None:
                    raw_data = measurement_metadata.get("raw_data", {})
                    if not isinstance(raw_data, dict):
                        raise ValueError(
                            "Measurement output does not contain recoverable measurement data"
                        )

                    freqs_hz = raw_data.get("freqs_hz", [])
                    raw_sparams = raw_data.get("sparams", {})
                    if not isinstance(freqs_hz, list) or not isinstance(
                        raw_sparams, dict
                    ):
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
                        if not (
                            isinstance(magnitude_db, list)
                            and isinstance(phase_deg, list)
                        ):
                            continue
                        if len(magnitude_db) != len(freqs) or len(phase_deg) != len(
                            freqs
                        ):
                            raise ValueError(
                                f"Recovered trace {name!r} has inconsistent array "
                                f"lengths: magnitude={len(magnitude_db)}, "
                                f"phase={len(phase_deg)}, freqs={len(freqs)}"
                            )
                        sparams[name] = (
                            np.array(magnitude_db, dtype=float),
                            np.array(phase_deg, dtype=float),
                        )

                    if len(freqs) == 0 or not sparams:
                        raise ValueError(
                            "Measurement output does not contain recoverable measurement data"
                        )
            else:
                freqs = None
                sparams = None

            resolved_path = str(file_path.resolve())
            self._send_import_progress("Packaging imported state...", 90)
            result = ImportResult(
                setup=dict(setup_metadata),
                measurement={
                    "restore_measurement": request.restore_measurement,
                    "metadata": dict(measurement_metadata),
                    "freq_unit": imported_freq_unit,
                    "frequencies": freqs,
                    "sparams": sparams,
                },
                notes=notes_markdown,
                paths={
                    "selected_path": request.file_path,
                    "output_path": resolved_path,
                    "touchstone_path": resolved_path if suffix == ".s2p" else None,
                    "png_path": resolved_path if suffix == ".png" else None,
                    "svg_path": resolved_path if suffix == ".svg" else None,
                },
            )

            self._send_import_progress("Import complete", 100)
            self._send_response(MessageType.IMPORT_COMPLETE, data=result)

        except Exception as e:
            self._send_response(MessageType.ERROR, error=f"Import failed: {str(e)}")

    def _handle_read_params(self) -> None:
        """Handle read parameters command using driver abstraction."""
        try:
            if not self._vna or not self._vna.is_connected():
                raise RuntimeError("Not connected to VNA")

            self._send_progress("Reading VNA parameters...", 50)

            # Get all parameters from driver
            params = cast(StatusCapableDriver, self._vna).get_current_parameters()

            result = ParamsResult(
                start_freq=params.get("start_freq_hz", 0.0),
                stop_freq=params.get("stop_freq_hz", 0.0),
                points=params.get("sweep_points", 0),
                averaging_enabled=params.get("averaging_enabled", False),
                averaging_count=params.get("averaging_count", 0),
            )

            self._send_progress("Done reading parameters", 100)
            self._send_response(MessageType.PARAMS_READ, data=result)

        except Exception as e:
            self._send_response(
                MessageType.ERROR, error=f"Failed to read parameters: {str(e)}"
            )

    def _handle_status_poll(self) -> None:
        """Handle status poll command.

        Always emits STATUS_UPDATE so the UI's in-flight flag is cleared.
        When measuring or disconnected a default (all-None) result is sent
        instead of querying the VNA.
        """
        if self._measuring or not self._vna or not self._vna.is_connected():
            self._send_response(MessageType.STATUS_UPDATE, data=StatusResult())
            return

        raw = {}
        try:
            if self._vna_wrapper is not None:
                self._vna_wrapper.log_tag = "poll"
            raw = cast(StatusCapableDriver, self._vna).get_status()
        except Exception as e:
            self._log(f"Status poll failed: {e}", "debug")
        finally:
            if self._vna_wrapper is not None:
                self._vna_wrapper.log_tag = None

        result = StatusResult(
            cal_enabled=raw.get("cal_enabled"),
            cal_type=raw.get("cal_type"),
            smoothing_enabled=raw.get("smoothing_enabled"),
            smoothing_aperture=raw.get("smoothing_aperture"),
            if_bandwidth_hz=raw.get("if_bandwidth_hz"),
            port_power_dbm=raw.get("port_power_dbm"),
            trigger_source=raw.get("trigger_source"),
        )
        self._send_response(MessageType.STATUS_UPDATE, data=result)

    def _handle_set_debug_scpi(self, enabled: bool) -> None:
        """Enable/disable per-command SCPI error checking."""
        self._debug_scpi = enabled
        if self._vna_wrapper is not None:
            self._vna_wrapper.debug = enabled

    def _on_scpi_error(self, command: str, raw_error: str) -> None:
        """Callback fired by LoggingVNAWrapper after each SYST:ERR? check.

        Forwards the result to the UI as a SCPI_ERROR_UPDATE message so the
        footer debug chip can reflect the last command's error state.
        """
        self._send_response(
            MessageType.SCPI_ERROR_UPDATE,
            data={"command": command, "error": raw_error},
        )

    def _handle_background_job(
        self, msg_type: MessageType, data: dict[str, Any] | None
    ) -> None:
        """Execute a background job command and stream unified progress updates."""
        if not isinstance(data, dict):
            self._send_response(
                MessageType.ERROR,
                error="Background job failed: invalid job payload",
            )
            return

        job_id_raw = data.get("job_id")
        operation_raw = data.get("operation")
        if not isinstance(job_id_raw, int) or not isinstance(operation_raw, str):
            self._send_response(
                MessageType.ERROR,
                error="Background job failed: missing job_id or operation",
            )
            return

        token_raw = data.get("token")
        if type(token_raw) is not int or token_raw < 1:
            self._send_response(
                MessageType.ERROR,
                error="Background job failed: missing or invalid job token",
            )
            return

        job_id = job_id_raw
        operation = operation_raw
        token = token_raw

        def report(message: str, progress: float) -> None:
            self._check_job_cancelled(job_id, token)
            self._send_progress(message, progress, job_id=job_id)

        try:
            result: Any
            report(f"{operation} starting...", 0)

            if msg_type == MessageType.EXPORT:
                kind = str(data.get("kind", "export"))
                report(f"{kind}: preparing data...", 10)
                export_kind = str(data.get("export_kind", ""))
                if export_kind == "touchstone":
                    exporter = TouchstoneExporter(
                        freq_unit=str(data.get("freq_unit", "MHz"))
                    )
                    report(f"{kind}: writing Touchstone...", 45)
                    raw_filename = data.get("filename")
                    result = exporter.export(
                        np.array(data["freqs"], dtype=float),
                        {
                            str(name): (
                                np.array(values[0], dtype=float),
                                np.array(values[1], dtype=float),
                            )
                            for name, values in dict(data["sparams"]).items()
                        },
                        str(data["output_folder"]),
                        str(raw_filename) if raw_filename is not None else None,
                        # output_name is always str at call sites; absent/None both
                        # mean "use default prefix", matching the exporter's default.
                        str(data.get("output_name") or "measurement"),
                        notes_markdown=str(data.get("notes_markdown", "")),
                        metadata=data.get("metadata"),
                    )
                elif export_kind == "csv":
                    report(f"{kind}: writing CSV...", 40)
                    exporter = CsvExporter(freq_unit=str(data.get("freq_unit", "MHz")))
                    result = exporter.export(
                        np.array(data["freqs"], dtype=float),
                        {
                            str(name): (
                                np.array(values[0], dtype=float),
                                np.array(values[1], dtype=float),
                            )
                            for name, values in dict(data["sparams"]).items()
                        },
                        str(data["output_folder"]),
                        str(data.get("filename", "measurement")),
                        str(data.get("output_name", "measurement")),
                    )
                elif export_kind == "image":
                    report(f"{kind}: rendering image...", 35)
                    file_path = str(data["file_path"])
                    output = Path(file_path)
                    plot_type = str(data["plot_type"])
                    plot_params = tuple(str(item) for item in list(data["plot_params"]))
                    freqs = np.array(data["freqs"], dtype=float)
                    sparams = {
                        str(name): (
                            np.array(values[0], dtype=float),
                            np.array(values[1], dtype=float),
                        )
                        for name, values in dict(data["sparams"]).items()
                    }
                    colors = dict(data["colors"])
                    if plot_type == "smith":
                        create_smith_chart(
                            freqs,
                            sparams,
                            list(plot_params),
                            output,
                            dpi=int(data["dpi"]),
                            colors=colors,
                        )
                    else:
                        create_matplotlib_plot(
                            freqs,
                            sparams,
                            list(plot_params),
                            plot_type,
                            output,
                            dpi=int(data["dpi"]),
                            colors=colors,
                        )
                    if not bool(data.get("minimal_export", False)):
                        report(f"{kind}: embedding metadata...", 80)
                        image_meta = build_image_export_metadata(
                            notes_markdown=str(data.get("notes_markdown", "")),
                            machine_settings=data.get("metadata"),
                        )
                        if str(data["image_format"]) == "png":
                            embed_png_metadata(
                                file_path,
                                notes_markdown=image_meta.notes_markdown,
                                machine_settings=image_meta.machine_settings,
                            )
                        else:
                            embed_svg_metadata(
                                file_path,
                                notes_markdown=image_meta.notes_markdown,
                                machine_settings=image_meta.machine_settings,
                            )
                    result = file_path
                elif export_kind == "results_plot":
                    report(f"{kind}: rendering plot...", 40)
                    _render_plot_image_snapshot(
                        np.array(data["freqs"], dtype=float),
                        {
                            str(name): (
                                np.array(values[0], dtype=float),
                                np.array(values[1], dtype=float),
                            )
                            for name, values in dict(data["sparams"]).items()
                        },
                        tuple(str(item) for item in list(data["plot_params"])),
                        str(data["plot_type"]),
                        Path(str(data["output_path"])),
                        int(data["dpi"]),
                        int(data["pixel_width"]),
                        int(data["pixel_height"]),
                        int(data.get("render_scale", 1)),
                        dict(data["colors"]),
                        float(data["y_min"]) if data.get("y_min") is not None else None,
                        float(data["y_max"]) if data.get("y_max") is not None else None,
                        (
                            {
                                str(name): np.array(values, dtype=float)
                                for name, values in dict(
                                    data.get("plot_data", {})
                                ).items()
                            }
                            if data.get("plot_data") is not None
                            else None
                        ),
                    )
                    result = {
                        "path": str(data["output_path"]),
                        "pixel_width": int(data["pixel_width"]),
                        "pixel_height": int(data["pixel_height"]),
                    }
                else:
                    raise ValueError(f"Unsupported export kind: {export_kind}")

            elif msg_type == MessageType.SAVE_BACK:
                report("Save-back: preparing metadata...", 15)
                target_kind = str(data.get("target_kind", ""))
                if target_kind == "touchstone":
                    report("Save-back: rewriting Touchstone metadata...", 60)
                    result = _write_touchstone_save_back(
                        str(data["target_path"]),
                        str(data.get("measurement_notes", "")),
                        dict(data.get("metadata", {})),
                    )
                elif target_kind in {"png", "svg"}:
                    report(
                        f"Save-back: embedding {target_kind.upper()} metadata...", 60
                    )
                    result = _write_image_save_back(
                        str(data["target_path"]),
                        str(data.get("measurement_notes", "")),
                        dict(data.get("metadata", {})),
                        target_kind,
                    )
                else:
                    raise ValueError("No original file available to save")

            elif msg_type == MessageType.TOOLS_RENDER:
                result = self._handle_tools_render(data, report)

            elif msg_type == MessageType.TOOLS_COMPUTE:
                result = self._handle_tools_compute(data, report)

            else:
                raise ValueError(
                    f"Unsupported background job message: {msg_type.value}"
                )

            self._check_job_cancelled(job_id, token)
            self._send_response(
                MessageType.PROGRESS,
                data=BackgroundJob(
                    job_id=job_id,
                    operation=operation,
                    progress=100.0,
                    result=result,
                ),
            )

        except BackgroundJobCancelledError:
            return
        except Exception as e:
            self._send_response(
                MessageType.ERROR,
                data={"job_id": job_id, "operation": operation},
                error=f"{operation} failed: {str(e)}",
            )

    def _handle_tools_render(
        self,
        data: dict[str, Any],
        report,
    ) -> dict[str, Any]:
        """Render the Tools image plot from a worker-side snapshot payload."""
        report("Tools plot: preparing render...", 20)
        freqs = np.array(data["freqs"], dtype=float)
        report("Tools plot: loading traces...", 35)
        sparams = {
            str(name): (
                np.array(values[0], dtype=float),
                np.array(values[1], dtype=float),
            )
            for name, values in dict(data["sparams"]).items()
        }
        active_tool = str(data.get("active_tool") or "")
        trace = str(data["trace"])
        plot_type = str(data["plot_type"])
        cursor1_hz = (
            float(data["cursor1_hz"]) if data.get("cursor1_hz") is not None else None
        )
        cursor2_hz = (
            float(data["cursor2_hz"]) if data.get("cursor2_hz") is not None else None
        )
        # Reuse a pre-computed result when the caller already holds a fresh one
        # (e.g. from a preceding TOOLS_COMPUTE job) to avoid duplicate work.
        if data.get("tool_result") is not None:
            tool_result = dict(data["tool_result"])
            report("Tools plot: reusing cached computation...", 50)
        else:
            tool_result = self._compute_tools_result_payload(
                freqs,
                sparams,
                active_tool,
                trace,
                plot_type,
                cursor1_hz,
                cursor2_hz,
            )
        report("Tools plot: rendering image...", 65)
        result = _render_tools_plot_snapshot(
            freqs,
            sparams,
            trace,
            plot_type,
            str(data["freq_unit"]),
            cursor1_hz,
            cursor2_hz,
            active_tool or None,
            str(data.get("marker_symbol", "▼")),
            dict(data["colors"]),
            [bool(item) for item in list(data.get("distortion_components", []))],
            tool_result,
            str(data["output_path"]),
        )
        report("Tools plot: finalizing image...", 90)
        return {
            **result,
            "tool_result": tool_result,
            "render_cache_key": data.get("render_cache_key"),
        }

    def _compute_tools_result_payload(
        self,
        freqs: np.ndarray,
        sparams: dict[str, tuple[np.ndarray, np.ndarray]],
        active_tool: str,
        trace: str,
        plot_type: str,
        cursor1_hz: float | None,
        cursor2_hz: float | None,
    ) -> dict[str, Any]:
        """Compute the active Tools tab result as a serializable payload."""
        if active_tool == "cursor":
            return asdict(
                MeasureTool().compute(
                    freqs,
                    sparams,
                    trace,
                    plot_type,
                    cursor1_hz,
                    cursor2_hz,
                )
            )

        if active_tool == "distortion":
            return asdict(
                DistortionTool().compute(
                    freqs,
                    sparams,
                    trace,
                    plot_type,
                    cursor1_hz,
                    cursor2_hz,
                )
            )

        return {"tool_name": "", "unit_label": "dB", "extra": {}}

    def _handle_tools_compute(
        self,
        data: dict[str, Any],
        report,
    ) -> dict[str, Any]:
        """Compute Tools tab results from a worker-side snapshot payload."""
        report("Tools: preparing computation...", 15)
        freqs = np.array(data["freqs"], dtype=float)
        sparams = {
            str(name): (
                np.array(values[0], dtype=float),
                np.array(values[1], dtype=float),
            )
            for name, values in dict(data["sparams"]).items()
        }
        active_tool = str(data.get("active_tool") or "")
        trace = str(data.get("trace", "S21"))
        plot_type = str(data.get("plot_type", "magnitude"))
        cursor1_hz = (
            float(data["cursor1_hz"]) if data.get("cursor1_hz") is not None else None
        )
        cursor2_hz = (
            float(data["cursor2_hz"]) if data.get("cursor2_hz") is not None else None
        )

        if active_tool == "cursor":
            report("Tools: measuring cursor values...", 55)
            tool_result = self._compute_tools_result_payload(
                freqs,
                sparams,
                active_tool,
                trace,
                plot_type,
                cursor1_hz,
                cursor2_hz,
            )
        elif active_tool == "distortion":
            report("Tools: fitting distortion model...", 45)
            tool_result = self._compute_tools_result_payload(
                freqs,
                sparams,
                active_tool,
                trace,
                plot_type,
                cursor1_hz,
                cursor2_hz,
            )
            report("Tools: packaging distortion results...", 85)
        else:
            report("Tools: no active tool selected", 90)
            tool_result = {"tool_name": "", "unit_label": "dB", "extra": {}}

        return {
            "tool_result": tool_result,
            "compute_cache_key": data.get("compute_cache_key"),
        }

    def _handle_measure(self, config: VNAConfig) -> None:
        """Handle measurement command using driver abstraction."""
        self._measuring = True
        trigger_state: tuple[str, bool] | None = None
        measurement_error: Exception | None = None
        try:
            if not self._vna or not self._vna.is_connected():
                raise RuntimeError("Not connected to VNA")

            # Update config
            self._config = config
            self._vna.config = config

            # Configure frequency
            self._send_progress("Configuring frequency...", 5)
            self._vna.configure_frequency()

            # Configure measurements
            self._send_progress("Configuring measurement settings...", 10)
            self._vna.configure_measurements()

            # Setup S-parameters
            self._send_progress("Setting up S-parameters...", 20)
            self._vna.setup_s_parameters()

            # Save trigger state before sweep
            self._send_progress("Triggering sweep...", 30)
            trigger_driver = cast(TriggerStateDriver, self._vna)
            trigger_state = trigger_driver.save_trigger_state()

            # Trigger sweep (doesn't restore state)
            self._vna.trigger_sweep()

            # Get frequency axis
            self._send_progress("Reading frequency data...", 50)
            freqs = self._vna.get_frequency_axis()

            # Get S-parameters
            sparams = {}
            param_names = ["S11", "S21", "S12", "S22"]
            for idx, name in enumerate(param_names, start=1):
                progress = 50 + (idx * 10)
                self._send_progress(f"Reading {name}...", progress)
                sparams[name] = self._vna.get_sparam_data(idx)

            result = MeasurementResult(frequencies=freqs, sparams=sparams)

            self._send_progress("Measurement complete", 100)
            self._log(
                f"Sending measurement result: {len(freqs)} freqs, {len(sparams)} sparams",
                "debug",
            )
            self._send_response(MessageType.MEASUREMENT_COMPLETE, data=result)

        except Exception as e:
            measurement_error = e
            self._send_response(
                MessageType.ERROR, error=f"Measurement failed: {str(e)}"
            )
        finally:
            if trigger_state is not None:
                try:
                    cast(TriggerStateDriver, self._vna).restore_trigger_state(
                        trigger_state
                    )
                except Exception as restore_error:
                    if measurement_error is None:
                        self._send_response(
                            MessageType.ERROR,
                            error=(
                                "Measurement failed: "
                                f"failed to restore trigger state: {restore_error}"
                            ),
                        )
                    else:
                        self._log(
                            "Failed to restore trigger state after measurement error: "
                            f"{restore_error}",
                            "debug",
                        )
            self._measuring = False

    def _handle_shutdown(self) -> None:
        """Handle shutdown command."""
        if self._vna:
            try:
                self._vna.disconnect()
            except Exception:
                pass
        self._vna = None
        self._vna_wrapper = None
        self._running = False
