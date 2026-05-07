"""Shared type helpers for GUI mixins and :mod:`tina.gui.app`."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any, TypedDict

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
    touchstone_path: str | None
    csv_path: str | None
    png_path: str | None
    svg_path: str | None
    freq_unit: str
    notes: str
    metadata: dict[str, object] | None


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

    def query_one(self, selector: str, *args: object) -> Any: ...
    def notify(
        self,
        title: object = "",
        message: object = "",
        *,
        severity: object = "information",
        timeout: object = 3.0,
        markup: object = True,
    ) -> None: ...
    def call_after_refresh(
        self, callback: Callable[..., object], *args: object
    ) -> bool: ...
    def set_interval(self, interval: float, callback: Callable[..., object]) -> Any: ...
    def set_timer(self, delay: float, callback: Callable[..., object]) -> Any: ...
    def copy_to_clipboard(self, text: str) -> None: ...
    def get_css_variables(self) -> dict[str, str]: ...
    def log_message(self, message: str, level: str = "info") -> None: ...
    def set_progress(self, label: str, progress: float = 0) -> None: ...
    def reset_progress(self) -> None: ...
    def disable_all_buttons(self) -> None: ...
    def enable_buttons_for_state(self) -> None: ...

    def _write_image_export(
        self,
        *,
        file_path: str,
        plot_type: str,
        plot_params: list[str],
        dpi: int,
        metadata_writer: Callable[..., None],
        minimal_export: bool = False,
    ) -> None: ...
    def _notify_export_result(
        self, *, kind: str, path: str, exported_items: str
    ) -> None: ...
    def _minimal_export_suffix(self, minimal_export: bool) -> str: ...
    def _build_image_export_metadata(
        self, *, exported_traces: list[str], plot_type: str, output_path: str
    ) -> dict[str, object]: ...
    def _get_tools_trace(self) -> str: ...
    def _get_distortion_comp_enabled(self) -> list[bool]: ...
    def _run_tools_render_job(self) -> dict[str, object]: ...
    def _refresh_results_plot_if_needed(self, force: bool = False) -> None: ...

    def _complete_background_job(self, job_id: int) -> None: ...
    def _update_background_job_progress(
        self, job_id: int, message: str, progress: float
    ) -> None: ...
    def _apply_import_result(self, result: Any) -> None: ...
    def _update_title(self) -> None: ...
    def update_connect_button(self) -> None: ...
    def _start_status_polling(self, interval: float) -> None: ...
    def _stop_status_polling(self) -> None: ...
    def _update_params_ui(self, result: Any) -> None: ...
    def _handle_measurement_complete(self, result: Any) -> None: ...
    def _handle_tools_render_result(self, result: dict[str, object]) -> None: ...

    def _restore_setup_from_metadata(self, metadata: dict[str, object]) -> None: ...
    def _invalidate_tools_render_result_cache(self) -> None: ...
    def _load_measurement_notes_into_editor(self) -> None: ...
    def _refresh_measurement_notes_preview(self) -> None: ...
    def _restore_measurement_view_from_metadata(
        self, metadata: dict[str, object], sparams: Any
    ) -> None: ...
    def _update_results(self, freqs: Any, sparams: Any, file_path: str) -> None: ...
    async def _refresh_tools_plot(self) -> None: ...
    def _run_tools_computation(self) -> None: ...
    async def _rebuild_tools_params(self) -> None: ...
    def _notify_import_result(self, *, path: str, imported_items: str) -> None: ...

    def _current_tools_render_cache_key(self) -> tuple[object, ...] | None: ...
    def action_save_back(self) -> None: ...
