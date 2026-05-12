"""Shared type helpers for GUI mixins and :mod:`tina.gui.app`.

The sibling modules ``background_jobs``, ``import_export``, ``notes``,
``results_plot``, ``setup_state``, ``tools_tab``, and ``worker_messages``
each contain a single thin subclass of :class:`GUIAppTypingMixin` that exists
solely to preserve legacy import paths.  All real type declarations live here.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any, TypedDict

try:
    from typing import NotRequired
except ImportError:  # Python < 3.11
    from typing_extensions import NotRequired  # type: ignore[assignment]

import numpy as np

from ...config.settings import AppSettings, SettingsManager
from ...drivers import VNAConfig
from ...worker import MeasurementWorker

SParamArrayPair = tuple[np.ndarray, np.ndarray]
SParamMap = dict[str, SParamArrayPair]
BackgroundJobState = dict[str, object]


class LogEntry(TypedDict):
    """Stored log entry used by the Log tab."""

    timestamp: str
    level: str
    message: str


class MeasurementRecord(TypedDict):
    """Cached measurement payload shared across tabs and export helpers."""

    freqs: np.ndarray
    sparams: SParamMap
    output_path: str
    freq_unit: str
    touchstone_path: NotRequired[str | None]
    csv_path: NotRequired[str | None]
    png_path: NotRequired[str | None]
    svg_path: NotRequired[str | None]
    notes: NotRequired[str]
    metadata: NotRequired[dict[str, object] | None]


class GUIAppTypingMixin:
    """Static-only app contract used by extracted GUI mixins.

    All cross-mixin method stubs are declared here so pyright can resolve
    calls between mixins without runtime coupling.
    """

    settings: AppSettings
    settings_manager: SettingsManager
    worker: MeasurementWorker
    config: VNAConfig
    connected: bool
    measuring: bool
    _import_in_flight: bool
    _status_poll_in_flight: bool
    _debug_scpi: bool
    _minimal_export_mode: bool
    last_measurement: MeasurementRecord | None
    _measurement_plot_cache: dict[tuple[object, ...], object]
    _measurement_plot_cache_measurement_id: int | None
    _plot_render_generation: int
    _results_plot_generation: int
    _results_plot_cache_key: tuple[object, ...] | None
    _results_plot_display_key: tuple[int, int] | None
    _results_plot_pixel_size: tuple[int, int] | None
    _current_background_job_id: int
    _background_jobs: dict[int, BackgroundJobState]
    _manual_export_jobs_in_flight: int
    measurement_notes: str
    last_output_path: str | None
    last_plot_path: Path | None
    log_messages: list[LogEntry]
    _message_check_timer: Any | None
    _resize_timer: Any | None
    _path_update_timer: Any | None
    _plot_refresh_timer: Any | None
    _poll_timer: Any | None
    _filename_template_validation: object | None
    _folder_template_validation: object | None
    _tools_cursor1_hz: float | None
    _tools_cursor2_hz: float | None
    _tools_cursor1_minima: bool
    _tools_cursor1_smoothing: bool
    _tools_cursor2_minima: bool
    _tools_cursor2_smoothing: bool
    _tools_resize_timer: Any | None
    _tools_input_timer: Any | None
    _tools_plot_generation: int
    _tools_plot_cache_key: tuple[object, ...] | None
    _tools_plot_display_key: tuple[int, int] | None
    _latest_tools_render_result: dict[str, object] | None
    _latest_tools_render_cache_key: tuple[object, ...] | None
    _tools_distortion_comp_enabled: list[bool]
    _tools_distortion_cache: dict[tuple[object, ...], object]
    _tools_distortion_cache_last_data_key: tuple[int, int, int] | None
    _tools_extrema_cache: dict[tuple[object, ...], np.ndarray]
    _tools_extrema_cache_last_data_id: int | None
    _tools_desired_peaks: int
    _tools_prominence_factor: float
    _template_input_timer: Any | None
    _tools_mpl_plot_state: dict[str, object]
    plot_temp_dir: Path
    terminal_font: str
    terminal_font_size: float | None
    terminal_program: str
    title: str
    sub_title: str
    _cached_style_map: dict[str, tuple[str, str]] | None

    def query_one(self, selector: str, *args: object) -> Any:
        """Return the first widget matching ``selector``, optionally typed by ``args``."""
        ...

    def notify(
        self,
        title: object = "",
        message: object = "",
        *,
        severity: object = "information",
        timeout: object = 3.0,
        markup: object = True,
    ) -> None:
        """Display a transient notification toast in the TUI."""
        ...

    def call_after_refresh(
        self, callback: Callable[..., object], *args: object
    ) -> bool:
        """Schedule ``callback`` to run after the next screen refresh."""
        ...

    def set_interval(self, interval: float, callback: Callable[..., object]) -> Any:
        """Call ``callback`` repeatedly every ``interval`` seconds; returns a handle."""
        ...

    def set_timer(self, delay: float, callback: Callable[..., object]) -> Any:
        """Call ``callback`` once after ``delay`` seconds; returns a handle."""
        ...

    def copy_to_clipboard(self, text: str) -> None:
        """Copy ``text`` to the system clipboard."""
        ...

    def get_css_variables(self) -> dict[str, str]:
        """Return the active CSS custom-property map for the current theme."""
        ...

    def log_message(self, message: str, level: str = "info") -> None:
        """Append a message to the in-app log at the given severity ``level``."""
        ...

    def set_progress(self, label: str, progress: float = 0) -> None:
        """Update the status-bar progress indicator with ``label`` and ``progress`` (0–100)."""
        ...

    def reset_progress(self) -> None:
        """Clear the status-bar progress indicator."""
        ...

    def disable_all_buttons(self) -> None:
        """Disable every interactive button in the UI."""
        ...

    def enable_buttons_for_state(self) -> None:
        """Re-enable buttons appropriate for the current connection state."""
        ...

    def _write_image_export(
        self,
        *,
        file_path: str,
        plot_type: str,
        plot_params: list[str],
        dpi: int,
        metadata_writer: Callable[..., None],
        minimal_export: bool = False,
    ) -> None:
        """Render and save a matplotlib image; calls ``metadata_writer`` to embed metadata.

        Args:
            file_path: Destination file path.
            plot_type: ``"magnitude"``, ``"phase"``, or ``"phase_raw"``.
            plot_params: S-parameter names to include in the plot.
            dpi: Image resolution in dots per inch.
            metadata_writer: Callable that embeds export metadata into the saved file.
            minimal_export: When ``True``, omit decorative elements.

        Raises:
            RuntimeError: If no measurement data is available.
        """
        ...

    def _notify_export_result(
        self, *, kind: str, path: str, exported_items: str
    ) -> None:
        """Show a success notification for a completed export of ``kind`` to ``path``."""
        ...

    def _minimal_export_suffix(self, minimal_export: bool) -> str:
        """Return a filename suffix for minimal exports, or ``""`` otherwise."""
        ...

    def _build_image_export_metadata(
        self, *, exported_traces: list[str], plot_type: str, output_path: str
    ) -> dict[str, object]:
        """Build the metadata dict to embed in an exported image file."""
        ...

    def _get_tools_trace(self) -> str:
        """Return the currently selected S-parameter trace for the Tools tab."""
        ...

    def _get_distortion_comp_enabled(self) -> list[bool]:
        """Return the per-harmonic distortion-compensation enable flags."""
        ...

    def _run_tools_render_job(self) -> dict[str, object]:
        """Execute the active tools render job and return its result payload.

        Raises:
            RuntimeError: If no measurement data or tools configuration is available.
        """
        ...

    def _refresh_results_plot_if_needed(self, force: bool = False) -> None:
        """Re-render the results plot when data or settings have changed."""
        ...

    def _complete_background_job(self, job_id: int) -> None:
        """Mark background job ``job_id`` as complete and update UI state."""
        ...

    def _update_background_job_progress(
        self, job_id: int, message: str, progress: float
    ) -> None:
        """Update progress display for background job ``job_id`` with ``message`` and ``progress``."""
        ...

    def _apply_import_result(self, result: Any) -> None:
        """Apply a completed Touchstone import result to app state and refresh the UI."""
        ...

    def _update_title(self) -> None:
        """Refresh the window/tab title to reflect the current connection state."""
        ...

    def update_connect_button(self) -> None:
        """Sync the Connect/Disconnect button label and variant with connection state."""
        ...

    def _start_status_polling(self, interval: float) -> None:
        """Begin polling the instrument for status every ``interval`` seconds."""
        ...

    def _stop_status_polling(self) -> None:
        """Cancel the active status-polling timer."""
        ...

    def _update_params_ui(self, result: Any) -> None:
        """Populate measurement-parameter widgets from a sweep result."""
        ...

    def _handle_measurement_complete(self, result: Any) -> None:
        """Process a completed measurement result and refresh all dependent views."""
        ...

    def _handle_tools_render_result(self, result: dict[str, object]) -> None:
        """Apply a finished tools render result to the Tools-tab display."""
        ...

    def _restore_setup_from_metadata(self, metadata: dict[str, object]) -> None:
        """Restore Setup-tab fields from embedded Touchstone metadata."""
        ...

    def _invalidate_tools_render_result_cache(self) -> None:
        """Clear the cached tools render result so the next render re-runs."""
        ...

    def _load_measurement_notes_into_editor(self) -> None:
        """Populate the notes editor widget from the current measurement notes."""
        ...

    def _refresh_measurement_notes_preview(self) -> None:
        """Re-render the Markdown preview from the current notes editor content."""
        ...

    def _restore_measurement_view_from_metadata(
        self, metadata: dict[str, object], sparams: Any
    ) -> None:
        """Restore plot/view state for the Results tab from Touchstone metadata."""
        ...

    def _update_results(self, freqs: Any, sparams: Any, file_path: str) -> None:
        """Update the Results tab with new frequency and S-parameter data."""
        ...

    async def _refresh_tools_plot(self) -> None:
        """Asynchronously re-render the Tools-tab plot from current cursor and data state."""
        ...

    def _run_tools_computation(self) -> None:
        """Trigger a synchronous tools computation pass and update the display."""
        ...

    async def _run_tools_computation_async(self) -> None:
        """Compute tools output asynchronously and update the results display."""
        ...

    async def _rebuild_tools_params(self) -> None:
        """Asynchronously rebuild the dynamic Tools-parameter widgets."""
        ...

    def _notify_import_result(self, *, path: str, imported_items: str) -> None:
        """Show a success notification for a completed Touchstone import."""
        ...

    def _current_tools_render_cache_key(self) -> tuple[object, ...] | None:
        """Return a hashable key representing the current tools render inputs, or ``None``."""
        ...

    def action_save_back(self) -> None:
        """Save current notes and metadata back into the loaded Touchstone file."""
        ...
