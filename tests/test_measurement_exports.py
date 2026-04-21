"""Tests for direct Measurement tab export helpers."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import MagicMock, patch

import numpy as np
import pytest
from PIL import Image
from textual.widgets import TabbedContent

from src.tina.export import (
    CsvExporter,
    embed_png_metadata,
    embed_svg_metadata,
)
from src.tina.main import VNAApp
from src.tina.utils.touchstone import TouchstoneExporter


@pytest.fixture
def sample_measurement() -> dict[str, Any]:
    """Provide representative cached measurement data."""
    freqs = np.array([1.0e6, 2.0e6, 3.0e6], dtype=float)
    sparams = {
        "S11": (
            np.array([-10.0, -11.0, -12.0], dtype=float),
            np.array([5.0, 6.0, 7.0], dtype=float),
        ),
        "S21": (
            np.array([-1.0, -1.5, -2.0], dtype=float),
            np.array([45.0, 46.0, 47.0], dtype=float),
        ),
        "S12": (
            np.array([-30.0, -31.0, -32.0], dtype=float),
            np.array([-10.0, -11.0, -12.0], dtype=float),
        ),
        "S22": (
            np.array([-20.0, -21.0, -22.0], dtype=float),
            np.array([15.0, 16.0, 17.0], dtype=float),
        ),
    }
    return {
        "freqs": freqs,
        "sparams": sparams,
        "output_path": "measurement/example_run.s2p",
        "freq_unit": "MHz",
        "notes": "## Export notes\nMeasured after warm-up.",
    }


class _FakeCheckbox:
    """Minimal checkbox-like object exposing a value attribute."""

    def __init__(self, value: bool) -> None:
        self.value = value


class _FakeButton:
    """Minimal button-like object exposing label, variant, state, and CSS classes."""

    def __init__(
        self,
        label: str = "",
        *,
        variant: str = "default",
        classes: set[str] | None = None,
        data: object = False,
    ) -> None:
        self.label = label
        self.variant = variant
        self.data = data
        self._classes = set(classes or ())

    def has_class(self, class_name: str) -> bool:
        """Return whether the button currently has the given CSS class."""
        return class_name in self._classes

    def set_class(self, enabled: bool, class_name: str) -> None:
        """Add or remove one CSS class based on *enabled*."""
        if enabled:
            self._classes.add(class_name)
        else:
            self._classes.discard(class_name)


class _FakeSelect:
    """Minimal select-like object exposing a value attribute."""

    def __init__(self, value: str) -> None:
        self.value = value


class _FakeApp:
    """Minimal app stub for exercising direct export handlers."""

    def __init__(
        self,
        measurement: dict[str, Any] | None,
        *,
        plot_type: str = "magnitude",
        selected_params: tuple[str, ...] = ("S11", "S21"),
        output_folder: str = "measurement",
        last_output_path: str | None = "measurement/example_run.s2p",
        freq_unit: str = "MHz",
    ) -> None:
        self.last_measurement = measurement
        self.last_output_path = last_output_path
        self.measurement_notes = (
            str(measurement.get("notes", "")) if measurement is not None else ""
        )
        self.settings = SimpleNamespace(output_folder=output_folder)
        self._minimal_export_button = _FakeButton(
            "▢\nMin",
            variant="default",
            data=False,
        )
        self._minimal_export_mode = False
        self.settings_manager = SimpleNamespace(
            touch_template_history=MagicMock(),
            save=MagicMock(),
            add_host_to_history=MagicMock(),
            add_port_to_history=MagicMock(),
        )
        self._plot_type = plot_type
        self._selected_params = set(selected_params)
        self._freq_unit = freq_unit
        self.log_message = MagicMock()
        self.notify = MagicMock()
        self.get_css_variables = MagicMock(return_value={"primary": "#ffffff"})
        self._choose_measurement_export_path = cast(Any, lambda **kwargs: "")
        self._get_selected_export_params = cast(Any, lambda: {})
        self._build_touchstone_export_metadata = cast(
            Any,
            lambda **kwargs: {
                "setup": {"host": "lab-vna", "freq_unit": self._freq_unit},
                "measurement": {"exported_traces": list(kwargs["exported_traces"])},
            },
        )
        self._build_image_export_metadata = cast(
            Any,
            lambda **kwargs: {
                "metadata_version": 1,
                "setup": {"host": "lab-vna", "freq_unit": self._freq_unit},
                "measurement": {
                    "exported_traces": list(kwargs["exported_traces"]),
                    "plot_type": kwargs["plot_type"],
                    "raw_data": {
                        "freqs_hz": (
                            self.last_measurement["freqs"].tolist()
                            if self.last_measurement is not None
                            else []
                        ),
                        "sparams": {},
                    },
                },
            },
        )
        self._notify_export_result = MagicMock()
        self._notify_import_result = MagicMock()
        self._load_measurement_notes_into_editor = MagicMock()
        self._refresh_measurement_notes_preview = MagicMock()
        self._refresh_tools_plot = MagicMock(return_value=None)
        self._run_tools_computation = MagicMock()
        self._rebuild_tools_params = MagicMock()
        self.call_after_refresh = MagicMock()
        self._update_results = MagicMock(return_value=None)
        self._write_image_export = MagicMock()
        self._import_measurement_output = MagicMock()
        self._restore_setup_from_metadata = cast(
            Any,
            lambda metadata: VNAApp._restore_setup_from_metadata(
                cast(Any, self), metadata
            ),
        )
        self._restore_measurement_view_from_metadata = cast(
            Any,
            lambda metadata, *, sparams=None: (
                VNAApp._restore_measurement_view_from_metadata(
                    cast(Any, self), metadata, sparams=sparams
                )
            ),
        )
        self._activate_measurement_tab = cast(
            Any,
            lambda: VNAApp._activate_measurement_tab(cast(Any, self)),
        )
        self._is_minimal_export_enabled = cast(
            Any,
            lambda: VNAApp._is_minimal_export_enabled(cast(Any, self)),
        )
        self._refresh_export_button_labels = cast(
            Any,
            lambda: VNAApp._refresh_export_button_labels(cast(Any, self)),
        )
        self._minimal_export_suffix = cast(
            Any,
            lambda minimal_export: VNAApp._minimal_export_suffix(minimal_export),
        )
        self.set_progress = MagicMock()
        self.enable_buttons_for_state = MagicMock()
        self.reset_progress = MagicMock()
        self._filename_template_validation = None
        self._folder_template_validation = None
        self.sub_title = ""
        self.measuring = False
        self._tabbed_content = SimpleNamespace(active="tab_measure")

    def query_one(self, selector: str, _widget_type=None):
        """Return minimal widget stubs for selectors used by export handlers."""
        if selector == "#select_plot_type":
            return _FakeSelect(self._plot_type)
        if selector == "#select_freq_unit":
            return _FakeSelect(self._freq_unit)
        if selector == "#check_plot_s11":
            return _FakeCheckbox("S11" in self._selected_params)
        if selector == "#check_plot_s21":
            return _FakeCheckbox("S21" in self._selected_params)
        if selector == "#check_plot_s12":
            return _FakeCheckbox("S12" in self._selected_params)
        if selector == "#check_plot_s22":
            return _FakeCheckbox("S22" in self._selected_params)
        if selector == "#check_export_s11":
            return _FakeCheckbox("S11" in self._selected_params)
        if selector == "#check_export_s21":
            return _FakeCheckbox("S21" in self._selected_params)
        if selector == "#check_export_s12":
            return _FakeCheckbox("S12" in self._selected_params)
        if selector == "#check_export_s22":
            return _FakeCheckbox("S22" in self._selected_params)
        if selector == "#check_minimal_export":
            return self._minimal_export_button
        if selector == "#btn_export_touchstone":
            return _FakeButton("⇩\nSxP", variant="success")
        if selector == "#btn_export_csv":
            return _FakeButton("≣\nCSV", variant="success")
        if selector == "#btn_export_png":
            return _FakeButton("◐\nPNG", variant="success")
        if selector == "#btn_export_svg":
            return _FakeButton("◇\nSVG", variant="success")
        if selector == "#check_export_bundle_csv":
            return _FakeCheckbox(False)
        if selector == "#check_export_bundle_png":
            return _FakeCheckbox(False)
        if selector == "#check_export_bundle_svg":
            return _FakeCheckbox(False)
        if selector == TabbedContent:
            return self._tabbed_content
        raise AssertionError(f"Unexpected selector: {selector}")


@pytest.mark.unit
class TestDirectMeasurementPlotExports:
    """Tests for direct PNG and SVG export handlers on the Measurement tab."""

    def test_export_png_logs_error_without_measurement(self) -> None:
        """PNG export should fail fast when no cached measurement exists."""
        app = _FakeApp(None)

        VNAApp.handle_export_png(cast(Any, app))

        app.log_message.assert_called_once_with(
            "No measurement data to export", "error"
        )

    def test_export_svg_logs_error_without_measurement(self) -> None:
        """SVG export should fail fast when no cached measurement exists."""
        app = _FakeApp(None)

        VNAApp.handle_export_svg(cast(Any, app))

        app.log_message.assert_called_once_with(
            "No measurement data to export", "error"
        )

    def test_export_png_uses_current_plot_selection(
        self, sample_measurement: dict[str, Any], tmp_path: Path
    ) -> None:
        """PNG export should pass the selected traces and chosen path to plotting."""
        app = _FakeApp(
            sample_measurement,
            plot_type="magnitude",
            selected_params=("S11", "S22"),
            output_folder=str(tmp_path),
        )
        chosen_path = tmp_path / "manual_plot.png"

        fake_root = MagicMock()
        fake_dialog = MagicMock(return_value=str(chosen_path))

        with (
            patch("src.tina.main.tk.Tk", return_value=fake_root),
            patch("src.tina.main.filedialog.asksaveasfilename", fake_dialog),
        ):
            VNAApp.handle_export_png(cast(Any, app))

        app._write_image_export.assert_called_once_with(
            file_path=str(chosen_path),
            plot_type="magnitude",
            plot_params=["S11", "S22"],
            dpi=300,
            metadata_writer=embed_png_metadata,
            minimal_export=False,
        )
        app.log_message.assert_called_once_with(
            f"Exported PNG: {chosen_path}", "success"
        )
        app._notify_export_result.assert_called_once_with(
            kind="PNG",
            path=str(chosen_path),
            exported_items="S11, S22",
        )

    def test_export_png_minimal_mode_skips_metadata_embedding(self) -> None:
        """Checkbox-enabled PNG export should skip metadata embedding."""
        app = _FakeApp(
            {
                "freqs": np.array([1.0e6], dtype=float),
                "sparams": {
                    "S11": (
                        np.array([-10.0], dtype=float),
                        np.array([5.0], dtype=float),
                    )
                },
                "output_path": "measurement/example_run.s2p",
                "freq_unit": "MHz",
                "notes": "notes",
            },
            plot_type="magnitude",
            selected_params=("S11",),
        )
        chosen_path = Path("/tmp/minimal_plot.png")

        fake_root = MagicMock()
        fake_dialog = MagicMock(return_value=str(chosen_path))
        write_image_export = MagicMock()
        app._write_image_export = write_image_export
        app._minimal_export_mode = True
        app._minimal_export_button.set_class(True, "-minimal-export")

        with (
            patch("src.tina.main.tk.Tk", return_value=fake_root),
            patch("src.tina.main.filedialog.asksaveasfilename", fake_dialog),
        ):
            VNAApp.handle_export_png(cast(Any, app))

        app._write_image_export.assert_called_once_with(
            file_path=str(chosen_path),
            plot_type="magnitude",
            plot_params=["S11"],
            dpi=300,
            metadata_writer=embed_png_metadata,
            minimal_export=True,
        )
        app.log_message.assert_called_once_with(
            f"Exported PNG (minimal): {chosen_path}", "success"
        )
        app._notify_export_result.assert_called_once_with(
            kind="PNG (minimal)",
            path=str(chosen_path),
            exported_items="S11",
        )

    def test_export_svg_uses_smith_chart_renderer_for_smith_plot(
        self, sample_measurement: dict[str, Any], tmp_path: Path
    ) -> None:
        """SVG export should route smith plots through the smith chart renderer."""
        app = _FakeApp(
            sample_measurement,
            plot_type="smith",
            selected_params=("S21",),
            output_folder=str(tmp_path),
        )
        chosen_path = tmp_path / "manual_plot.svg"

        fake_root = MagicMock()
        fake_dialog = MagicMock(return_value=str(chosen_path))

        with (
            patch("src.tina.main.tk.Tk", return_value=fake_root),
            patch("src.tina.main.filedialog.asksaveasfilename", fake_dialog),
        ):
            VNAApp.handle_export_svg(cast(Any, app))

        app._write_image_export.assert_called_once_with(
            file_path=str(chosen_path),
            plot_type="smith",
            plot_params=["S21"],
            dpi=150,
            metadata_writer=embed_svg_metadata,
            minimal_export=False,
        )
        app.log_message.assert_called_once_with(
            f"Exported SVG: {chosen_path}", "success"
        )
        app._notify_export_result.assert_called_once_with(
            kind="SVG",
            path=str(chosen_path),
            exported_items="S21",
        )

    def test_export_svg_minimal_mode_skips_metadata_embedding(self) -> None:
        """Checkbox-enabled SVG export should skip metadata embedding."""
        app = _FakeApp(
            {
                "freqs": np.array([1.0e6], dtype=float),
                "sparams": {
                    "S21": (
                        np.array([-1.0], dtype=float),
                        np.array([45.0], dtype=float),
                    )
                },
                "output_path": "measurement/example_run.s2p",
                "freq_unit": "MHz",
                "notes": "notes",
            },
            plot_type="smith",
            selected_params=("S21",),
        )
        chosen_path = Path("/tmp/minimal_plot.svg")

        fake_root = MagicMock()
        fake_dialog = MagicMock(return_value=str(chosen_path))
        write_image_export = MagicMock()
        app._write_image_export = write_image_export
        app._minimal_export_mode = True
        app._minimal_export_button.set_class(True, "-minimal-export")

        with (
            patch("src.tina.main.tk.Tk", return_value=fake_root),
            patch("src.tina.main.filedialog.asksaveasfilename", fake_dialog),
        ):
            VNAApp.handle_export_svg(cast(Any, app))

        app._write_image_export.assert_called_once_with(
            file_path=str(chosen_path),
            plot_type="smith",
            plot_params=["S21"],
            dpi=150,
            metadata_writer=embed_svg_metadata,
            minimal_export=True,
        )
        app.log_message.assert_called_once_with(
            f"Exported SVG (minimal): {chosen_path}", "success"
        )
        app._notify_export_result.assert_called_once_with(
            kind="SVG (minimal)",
            path=str(chosen_path),
            exported_items="S21",
        )

    def test_export_png_returns_quietly_when_dialog_is_cancelled(
        self, sample_measurement: dict[str, Any], tmp_path: Path
    ) -> None:
        """PNG export should do nothing when the save dialog is cancelled."""
        app = _FakeApp(sample_measurement, output_folder=str(tmp_path))
        fake_root = MagicMock()

        with (
            patch("src.tina.main.tk.Tk", return_value=fake_root),
            patch("src.tina.main.filedialog.asksaveasfilename", return_value=""),
            patch("src.tina.main.create_matplotlib_plot") as create_plot,
        ):
            VNAApp.handle_export_png(cast(Any, app))

        create_plot.assert_not_called()
        app.log_message.assert_not_called()

    def test_export_png_embeds_metadata_after_plot_render(
        self, sample_measurement: dict[str, Any], tmp_path: Path
    ) -> None:
        """PNG export should embed notes and recovery metadata after rendering."""
        app = _FakeApp(
            sample_measurement,
            plot_type="magnitude",
            selected_params=("S11", "S22"),
            output_folder=str(tmp_path),
        )
        chosen_path = tmp_path / "manual_plot.png"

        fake_root = MagicMock()
        fake_dialog = MagicMock(return_value=str(chosen_path))

        with (
            patch("src.tina.main.tk.Tk", return_value=fake_root),
            patch("src.tina.main.filedialog.asksaveasfilename", fake_dialog),
        ):
            VNAApp.handle_export_png(cast(Any, app))

        app._write_image_export.assert_called_once_with(
            file_path=str(chosen_path),
            plot_type="magnitude",
            plot_params=["S11", "S22"],
            dpi=300,
            metadata_writer=embed_png_metadata,
            minimal_export=False,
        )
        app._notify_export_result.assert_called_once_with(
            kind="PNG",
            path=str(chosen_path),
            exported_items="S11, S22",
        )

    def test_export_svg_embeds_metadata_after_plot_render(
        self, sample_measurement: dict[str, Any], tmp_path: Path
    ) -> None:
        """SVG export should embed notes and recovery metadata after rendering."""
        app = _FakeApp(
            sample_measurement,
            plot_type="smith",
            selected_params=("S21",),
            output_folder=str(tmp_path),
        )
        chosen_path = tmp_path / "manual_plot.svg"

        fake_root = MagicMock()
        fake_dialog = MagicMock(return_value=str(chosen_path))

        with (
            patch("src.tina.main.tk.Tk", return_value=fake_root),
            patch("src.tina.main.filedialog.asksaveasfilename", fake_dialog),
        ):
            VNAApp.handle_export_svg(cast(Any, app))

        app._write_image_export.assert_called_once_with(
            file_path=str(chosen_path),
            plot_type="smith",
            plot_params=["S21"],
            dpi=150,
            metadata_writer=embed_svg_metadata,
            minimal_export=False,
        )
        app._notify_export_result.assert_called_once_with(
            kind="SVG",
            path=str(chosen_path),
            exported_items="S21",
        )


@pytest.mark.unit
class TestMeasurementCompletionBundleExports:
    """Tests for bundle image exports during measurement completion."""

    @pytest.mark.asyncio
    async def test_measurement_complete_exports_bundle_png_with_metadata(
        self, sample_measurement: dict[str, Any], tmp_path: Path
    ) -> None:
        """Measurement completion should write bundled PNG exports with metadata."""
        app = _FakeApp(
            None,
            selected_params=("S11", "S21"),
            output_folder=str(tmp_path),
        )
        app.measurement_notes = sample_measurement["notes"]
        app.settings = SimpleNamespace(
            filename_template="measurement_{date}_{time}",
            folder_template="measurement",
            freq_unit="MHz",
            plot_type="magnitude",
        )
        app.settings_manager = SimpleNamespace(
            touch_template_history=MagicMock(),
            save=MagicMock(),
        )
        app._build_touchstone_export_metadata = cast(
            Any,
            lambda **kwargs: {
                "setup": {"host": "lab-vna", "freq_unit": "MHz"},
                "measurement": {"exported_traces": list(kwargs["exported_traces"])},
            },
        )
        app._build_image_export_metadata = cast(
            Any,
            lambda **kwargs: {
                "metadata_version": 1,
                "setup": {"host": "lab-vna", "freq_unit": "MHz"},
                "measurement": {
                    "exported_traces": list(kwargs["exported_traces"]),
                    "plot_type": kwargs["plot_type"],
                    "raw_data": {
                        "freqs_hz": sample_measurement["freqs"].tolist(),
                        "sparams": {},
                    },
                },
            },
        )
        app.notify = MagicMock()
        app._write_image_export = MagicMock()
        app._refresh_tools_plot = MagicMock()
        app._run_tools_computation = MagicMock()
        app._rebuild_tools_params = MagicMock()
        app._update_results = MagicMock()
        app.log_message = MagicMock()
        app.query_one = cast(
            Any,
            lambda selector, _widget_type=None: {
                "#check_export_s11": _FakeCheckbox(True),
                "#check_export_s21": _FakeCheckbox(True),
                "#check_export_s12": _FakeCheckbox(False),
                "#check_export_s22": _FakeCheckbox(False),
                "#check_export_bundle_csv": _FakeCheckbox(False),
                "#check_export_bundle_png": _FakeCheckbox(True),
                "#check_export_bundle_svg": _FakeCheckbox(False),
                "#check_minimal_export": app._minimal_export_button,
                "#check_plot_s11": _FakeCheckbox(True),
                "#check_plot_s21": _FakeCheckbox(True),
                "#check_plot_s12": _FakeCheckbox(False),
                "#check_plot_s22": _FakeCheckbox(False),
                "#select_freq_unit": _FakeSelect("MHz"),
                "#input_filename_prefix": SimpleNamespace(value="bundle_run"),
                "#input_output_folder": SimpleNamespace(value=str(tmp_path)),
            }[selector],
        )

        result = SimpleNamespace(
            frequencies=sample_measurement["freqs"],
            sparams=sample_measurement["sparams"],
        )

        with (
            patch(
                "src.tina.main.setup_logic.validate_export_template_for_app",
                side_effect=lambda *args, **kwargs: SimpleNamespace(
                    has_errors=False,
                    has_warnings=False,
                    unknown_tags=(),
                ),
            ),
            patch("src.tina.main.setup_logic.apply_template_input_state"),
            patch(
                "src.tina.main.setup_logic.build_export_template_context_for_app",
                return_value={},
            ),
            patch(
                "src.tina.main.render_template",
                side_effect=[
                    SimpleNamespace(
                        rendered="bundle_run",
                        validation=SimpleNamespace(
                            has_warnings=False,
                            unknown_tags=(),
                        ),
                    ),
                    SimpleNamespace(
                        rendered=str(tmp_path),
                        validation=SimpleNamespace(
                            has_warnings=False,
                            unknown_tags=(),
                        ),
                    ),
                ],
            ),
            patch.object(
                TouchstoneExporter,
                "export",
                return_value=str(tmp_path / "bundle_run.s2p"),
            ),
            patch("src.tina.main.asyncio.get_event_loop") as get_loop,
        ):
            loop = MagicMock()

            async def run_in_executor(_executor, func, *args):
                if callable(func):
                    return func(*args)
                return None

            loop.run_in_executor.side_effect = run_in_executor
            get_loop.return_value = loop

            await VNAApp._handle_measurement_complete(cast(Any, app), cast(Any, result))

        assert app.last_measurement is not None
        assert app.last_measurement["png_path"] == str(tmp_path / "bundle_run.png")
        assert app.last_measurement["touchstone_path"] == str(
            tmp_path / "bundle_run.s2p"
        )
        assert app.last_measurement["png_path"] == str(tmp_path / "bundle_run.png")
        app._notify_export_result.assert_any_call(
            kind="PNG",
            path=str(tmp_path / "bundle_run.png"),
            exported_items="S11, S21",
        )

    @pytest.mark.asyncio
    async def test_measurement_complete_bundle_png_minimal_mode_skips_metadata(
        self, sample_measurement: dict[str, Any], tmp_path: Path
    ) -> None:
        """Minimal bundle PNG export should follow the checkbox state."""
        app = _FakeApp(
            None,
            selected_params=("S11", "S21"),
            output_folder=str(tmp_path),
        )
        app.measurement_notes = sample_measurement["notes"]
        app.settings = SimpleNamespace(
            filename_template="measurement_{date}_{time}",
            folder_template="measurement",
            freq_unit="MHz",
            plot_type="magnitude",
        )
        app.settings_manager = SimpleNamespace(
            touch_template_history=MagicMock(),
            save=MagicMock(),
        )
        app._build_touchstone_export_metadata = cast(
            Any,
            lambda **kwargs: {
                "setup": {"host": "lab-vna", "freq_unit": "MHz"},
                "measurement": {"exported_traces": list(kwargs["exported_traces"])},
            },
        )
        app._build_image_export_metadata = cast(
            Any,
            lambda **kwargs: {
                "metadata_version": 1,
                "setup": {"host": "lab-vna", "freq_unit": "MHz"},
                "measurement": {
                    "exported_traces": list(kwargs["exported_traces"]),
                    "plot_type": kwargs["plot_type"],
                    "raw_data": {
                        "freqs_hz": sample_measurement["freqs"].tolist(),
                        "sparams": {},
                    },
                },
            },
        )
        app.notify = MagicMock()
        app._write_image_export = MagicMock()
        app._refresh_tools_plot = MagicMock()
        app._run_tools_computation = MagicMock()
        app._rebuild_tools_params = MagicMock()
        app._update_results = MagicMock()
        app.log_message = MagicMock()
        app.query_one = cast(
            Any,
            lambda selector, _widget_type=None: {
                "#check_export_s11": _FakeCheckbox(True),
                "#check_export_s21": _FakeCheckbox(True),
                "#check_export_s12": _FakeCheckbox(False),
                "#check_export_s22": _FakeCheckbox(False),
                "#check_export_bundle_csv": _FakeCheckbox(False),
                "#check_export_bundle_png": _FakeCheckbox(True),
                "#check_export_bundle_svg": _FakeCheckbox(False),
                "#check_minimal_export": app._minimal_export_button,
                "#check_plot_s11": _FakeCheckbox(True),
                "#check_plot_s21": _FakeCheckbox(True),
                "#check_plot_s12": _FakeCheckbox(False),
                "#check_plot_s22": _FakeCheckbox(False),
                "#select_freq_unit": _FakeSelect("MHz"),
                "#input_filename_prefix": SimpleNamespace(value="bundle_run"),
                "#input_output_folder": SimpleNamespace(value=str(tmp_path)),
            }[selector],
        )

        result = SimpleNamespace(
            frequencies=sample_measurement["freqs"],
            sparams=sample_measurement["sparams"],
        )
        app._minimal_export_mode = True
        app._minimal_export_button.set_class(True, "-minimal-export")

        with (
            patch(
                "src.tina.main.setup_logic.validate_export_template_for_app",
                side_effect=lambda *args, **kwargs: SimpleNamespace(
                    has_errors=False,
                    has_warnings=False,
                    unknown_tags=(),
                ),
            ),
            patch("src.tina.main.setup_logic.apply_template_input_state"),
            patch(
                "src.tina.main.setup_logic.build_export_template_context_for_app",
                return_value={},
            ),
            patch(
                "src.tina.main.render_template",
                side_effect=[
                    SimpleNamespace(
                        rendered="bundle_run",
                        validation=SimpleNamespace(
                            has_warnings=False,
                            unknown_tags=(),
                        ),
                    ),
                    SimpleNamespace(
                        rendered=str(tmp_path),
                        validation=SimpleNamespace(
                            has_warnings=False,
                            unknown_tags=(),
                        ),
                    ),
                ],
            ),
            patch.object(
                TouchstoneExporter,
                "export",
                return_value=str(tmp_path / "bundle_run.s2p"),
            ),
            patch("src.tina.main.asyncio.get_event_loop") as get_loop,
        ):
            loop = MagicMock()

            async def run_in_executor(_executor, func, *args):
                if callable(func):
                    return func(*args)
                return None

            loop.run_in_executor.side_effect = run_in_executor
            get_loop.return_value = loop

            await VNAApp._handle_measurement_complete(cast(Any, app), cast(Any, result))

        assert app.last_measurement is not None
        assert app.last_measurement["png_path"] == str(tmp_path / "bundle_run.png")

    @pytest.mark.asyncio
    async def test_measurement_complete_exports_bundle_svg_with_metadata(
        self, sample_measurement: dict[str, Any], tmp_path: Path
    ) -> None:
        """Measurement completion should write bundled SVG exports with metadata."""
        app = _FakeApp(
            None,
            selected_params=("S21",),
            output_folder=str(tmp_path),
        )
        app.measurement_notes = sample_measurement["notes"]
        app.settings = SimpleNamespace(
            filename_template="measurement_{date}_{time}",
            folder_template="measurement",
            freq_unit="MHz",
            plot_type="smith",
        )
        app.settings_manager = SimpleNamespace(
            touch_template_history=MagicMock(),
            save=MagicMock(),
        )
        app._build_touchstone_export_metadata = cast(
            Any,
            lambda **kwargs: {
                "setup": {"host": "lab-vna", "freq_unit": "MHz"},
                "measurement": {"exported_traces": list(kwargs["exported_traces"])},
            },
        )
        app._build_image_export_metadata = cast(
            Any,
            lambda **kwargs: {
                "metadata_version": 1,
                "setup": {"host": "lab-vna", "freq_unit": "MHz"},
                "measurement": {
                    "exported_traces": list(kwargs["exported_traces"]),
                    "plot_type": kwargs["plot_type"],
                    "raw_data": {
                        "freqs_hz": sample_measurement["freqs"].tolist(),
                        "sparams": {},
                    },
                },
            },
        )
        app.notify = MagicMock()
        app._write_image_export = MagicMock()
        app._refresh_tools_plot = MagicMock()
        app._run_tools_computation = MagicMock()
        app._rebuild_tools_params = MagicMock()
        app._update_results = MagicMock()
        app.log_message = MagicMock()
        app.query_one = cast(
            Any,
            lambda selector, _widget_type=None: {
                "#check_export_s11": _FakeCheckbox(False),
                "#check_export_s21": _FakeCheckbox(True),
                "#check_export_s12": _FakeCheckbox(False),
                "#check_export_s22": _FakeCheckbox(False),
                "#check_export_bundle_csv": _FakeCheckbox(False),
                "#check_export_bundle_png": _FakeCheckbox(False),
                "#check_export_bundle_svg": _FakeCheckbox(True),
                "#check_minimal_export": app._minimal_export_button,
                "#check_plot_s11": _FakeCheckbox(False),
                "#check_plot_s21": _FakeCheckbox(True),
                "#check_plot_s12": _FakeCheckbox(False),
                "#check_plot_s22": _FakeCheckbox(False),
                "#select_freq_unit": _FakeSelect("MHz"),
                "#input_filename_prefix": SimpleNamespace(value="bundle_run"),
                "#input_output_folder": SimpleNamespace(value=str(tmp_path)),
            }[selector],
        )

        result = SimpleNamespace(
            frequencies=sample_measurement["freqs"],
            sparams=sample_measurement["sparams"],
        )

        with (
            patch(
                "src.tina.main.setup_logic.validate_export_template_for_app",
                side_effect=lambda *args, **kwargs: SimpleNamespace(
                    has_errors=False,
                    has_warnings=False,
                    unknown_tags=(),
                ),
            ),
            patch("src.tina.main.setup_logic.apply_template_input_state"),
            patch(
                "src.tina.main.setup_logic.build_export_template_context_for_app",
                return_value={},
            ),
            patch(
                "src.tina.main.render_template",
                side_effect=[
                    SimpleNamespace(
                        rendered="bundle_run",
                        validation=SimpleNamespace(
                            has_warnings=False,
                            unknown_tags=(),
                        ),
                    ),
                    SimpleNamespace(
                        rendered=str(tmp_path),
                        validation=SimpleNamespace(
                            has_warnings=False,
                            unknown_tags=(),
                        ),
                    ),
                ],
            ),
            patch.object(
                TouchstoneExporter,
                "export",
                return_value=str(tmp_path / "bundle_run.s2p"),
            ),
            patch("src.tina.main.asyncio.get_event_loop") as get_loop,
        ):
            loop = MagicMock()

            async def run_in_executor(_executor, func, *args):
                if callable(func):
                    return func(*args)
                return None

            loop.run_in_executor.side_effect = run_in_executor
            get_loop.return_value = loop

            await VNAApp._handle_measurement_complete(cast(Any, app), cast(Any, result))

        assert app.last_measurement is not None
        assert app.last_measurement["svg_path"] == str(tmp_path / "bundle_run.svg")
        assert app.last_measurement["touchstone_path"] == str(
            tmp_path / "bundle_run.s2p"
        )
        assert app.last_measurement["svg_path"] == str(tmp_path / "bundle_run.svg")
        app._notify_export_result.assert_any_call(
            kind="SVG",
            path=str(tmp_path / "bundle_run.svg"),
            exported_items="S21",
        )

    @pytest.mark.asyncio
    async def test_measurement_complete_bundle_svg_minimal_mode_skips_metadata(
        self, sample_measurement: dict[str, Any], tmp_path: Path
    ) -> None:
        """Minimal bundle SVG export should follow the checkbox state."""
        app = _FakeApp(
            None,
            selected_params=("S21",),
            output_folder=str(tmp_path),
        )
        app.measurement_notes = sample_measurement["notes"]
        app.settings = SimpleNamespace(
            filename_template="measurement_{date}_{time}",
            folder_template="measurement",
            freq_unit="MHz",
            plot_type="smith",
        )
        app.settings_manager = SimpleNamespace(
            touch_template_history=MagicMock(),
            save=MagicMock(),
        )
        app._build_touchstone_export_metadata = cast(
            Any,
            lambda **kwargs: {
                "setup": {"host": "lab-vna", "freq_unit": "MHz"},
                "measurement": {"exported_traces": list(kwargs["exported_traces"])},
            },
        )
        app._build_image_export_metadata = cast(
            Any,
            lambda **kwargs: {
                "metadata_version": 1,
                "setup": {"host": "lab-vna", "freq_unit": "MHz"},
                "measurement": {
                    "exported_traces": list(kwargs["exported_traces"]),
                    "plot_type": kwargs["plot_type"],
                    "raw_data": {
                        "freqs_hz": sample_measurement["freqs"].tolist(),
                        "sparams": {},
                    },
                },
            },
        )
        app.notify = MagicMock()
        app._write_image_export = MagicMock()
        app._refresh_tools_plot = MagicMock()
        app._run_tools_computation = MagicMock()
        app._rebuild_tools_params = MagicMock()
        app._update_results = MagicMock()
        app.log_message = MagicMock()
        app.query_one = cast(
            Any,
            lambda selector, _widget_type=None: {
                "#check_export_s11": _FakeCheckbox(False),
                "#check_export_s21": _FakeCheckbox(True),
                "#check_export_s12": _FakeCheckbox(False),
                "#check_export_s22": _FakeCheckbox(False),
                "#check_export_bundle_csv": _FakeCheckbox(False),
                "#check_export_bundle_png": _FakeCheckbox(False),
                "#check_export_bundle_svg": _FakeCheckbox(True),
                "#check_minimal_export": app._minimal_export_button,
                "#check_plot_s11": _FakeCheckbox(False),
                "#check_plot_s21": _FakeCheckbox(True),
                "#check_plot_s12": _FakeCheckbox(False),
                "#check_plot_s22": _FakeCheckbox(False),
                "#select_freq_unit": _FakeSelect("MHz"),
                "#input_filename_prefix": SimpleNamespace(value="bundle_run"),
                "#input_output_folder": SimpleNamespace(value=str(tmp_path)),
            }[selector],
        )

        result = SimpleNamespace(
            frequencies=sample_measurement["freqs"],
            sparams=sample_measurement["sparams"],
        )
        app._minimal_export_mode = True
        app._minimal_export_button.set_class(True, "-minimal-export")

        with (
            patch(
                "src.tina.main.setup_logic.validate_export_template_for_app",
                side_effect=lambda *args, **kwargs: SimpleNamespace(
                    has_errors=False,
                    has_warnings=False,
                    unknown_tags=(),
                ),
            ),
            patch("src.tina.main.setup_logic.apply_template_input_state"),
            patch(
                "src.tina.main.setup_logic.build_export_template_context_for_app",
                return_value={},
            ),
            patch(
                "src.tina.main.render_template",
                side_effect=[
                    SimpleNamespace(
                        rendered="bundle_run",
                        validation=SimpleNamespace(
                            has_warnings=False,
                            unknown_tags=(),
                        ),
                    ),
                    SimpleNamespace(
                        rendered=str(tmp_path),
                        validation=SimpleNamespace(
                            has_warnings=False,
                            unknown_tags=(),
                        ),
                    ),
                ],
            ),
            patch.object(
                TouchstoneExporter,
                "export",
                return_value=str(tmp_path / "bundle_run.s2p"),
            ),
            patch("src.tina.main.asyncio.get_event_loop") as get_loop,
        ):
            loop = MagicMock()

            async def run_in_executor(_executor, func, *args):
                if callable(func):
                    return func(*args)
                return None

            loop.run_in_executor.side_effect = run_in_executor
            get_loop.return_value = loop

            await VNAApp._handle_measurement_complete(cast(Any, app), cast(Any, result))

        assert app.last_measurement is not None
        assert app.last_measurement["svg_path"] == str(tmp_path / "bundle_run.svg")


@pytest.mark.unit
class TestDirectMeasurementDataExports:
    """Tests for direct Touchstone and CSV export handlers on the Measurement tab."""

    def test_export_touchstone_logs_error_without_measurement(self) -> None:
        """Touchstone export should fail fast when no cached measurement exists."""
        app = _FakeApp(None)

        VNAApp.handle_export_touchstone(cast(Any, app))

        app.log_message.assert_called_once_with(
            "No measurement data to export", "error"
        )

    def test_export_csv_logs_error_without_measurement(self) -> None:
        """CSV export should fail fast when no cached measurement exists."""
        app = _FakeApp(None)

        VNAApp.handle_export_csv(cast(Any, app))

        app.log_message.assert_called_once_with(
            "No measurement data to export", "error"
        )

    def test_export_touchstone_uses_selected_export_traces(
        self, sample_measurement: dict[str, Any], tmp_path: Path
    ) -> None:
        """Touchstone export should pass selected traces to the exporter."""
        app = _FakeApp(
            sample_measurement,
            selected_params=("S11", "S21"),
            output_folder=str(tmp_path),
        )
        chosen_path = tmp_path / "manual_touchstone.s2p"

        app._choose_measurement_export_path = cast(
            Any, lambda **kwargs: str(chosen_path)
        )
        app._get_selected_export_params = cast(
            Any,
            lambda: {
                "S11": sample_measurement["sparams"]["S11"],
                "S21": sample_measurement["sparams"]["S21"],
            },
        )

        with patch.object(TouchstoneExporter, "export", return_value=str(chosen_path)):
            VNAApp.handle_export_touchstone(cast(Any, app))

        assert app.last_measurement is not None
        assert app.last_measurement["touchstone_path"] == str(chosen_path)
        assert app.last_measurement is not None
        assert app.last_measurement["touchstone_path"] == str(chosen_path)
        app.log_message.assert_called_once_with(
            f"Exported Touchstone (SxP): {chosen_path}", "success"
        )
        app._notify_export_result.assert_called_once_with(
            kind="Touchstone",
            path=str(chosen_path),
            exported_items="S11, S21",
        )

    def test_export_touchstone_minimal_mode_omits_notes_and_metadata(self) -> None:
        """Checkbox-enabled Touchstone export should omit notes and metadata payloads."""
        app = _FakeApp(
            {
                "freqs": np.array([1.0e6, 2.0e6], dtype=float),
                "sparams": {
                    "S11": (
                        np.array([-10.0, -11.0], dtype=float),
                        np.array([5.0, 6.0], dtype=float),
                    ),
                    "S21": (
                        np.array([-1.0, -2.0], dtype=float),
                        np.array([45.0, 46.0], dtype=float),
                    ),
                },
                "output_path": "measurement/example_run.s2p",
                "freq_unit": "MHz",
                "notes": "## Export notes",
            },
            selected_params=("S11", "S21"),
        )
        chosen_path = Path("/tmp/minimal_measurement.s2p")
        app._choose_measurement_export_path = cast(
            Any, lambda **kwargs: str(chosen_path)
        )
        app._get_selected_export_params = cast(
            Any,
            lambda: {
                "S11": cast(Any, app.last_measurement)["sparams"]["S11"],
                "S21": cast(Any, app.last_measurement)["sparams"]["S21"],
            },
        )

        app._minimal_export_mode = True
        app._minimal_export_button.set_class(True, "-minimal-export")

        with patch.object(TouchstoneExporter, "export", return_value=str(chosen_path)):
            VNAApp.handle_export_touchstone(cast(Any, app))

        assert app.last_measurement is not None
        assert app.last_measurement["touchstone_path"] == str(chosen_path)
        app.log_message.assert_called_once_with(
            f"Exported Touchstone (SxP) (minimal): {chosen_path}", "success"
        )
        app._notify_export_result.assert_called_once_with(
            kind="Touchstone (minimal)",
            path=str(chosen_path),
            exported_items="S11, S21",
        )

    def test_export_csv_uses_selected_export_traces(
        self, sample_measurement: dict[str, Any], tmp_path: Path
    ) -> None:
        """CSV export should pass selected traces to the exporter."""
        app = _FakeApp(
            sample_measurement,
            selected_params=("S21", "S22"),
            output_folder=str(tmp_path),
        )
        chosen_path = tmp_path / "manual_csv.csv"

        app._choose_measurement_export_path = cast(
            Any, lambda **kwargs: str(chosen_path)
        )
        app._get_selected_export_params = cast(
            Any,
            lambda: {
                "S21": sample_measurement["sparams"]["S21"],
                "S22": sample_measurement["sparams"]["S22"],
            },
        )

        with patch.object(
            CsvExporter, "export", return_value=str(chosen_path)
        ) as export_mock:
            VNAApp.handle_export_csv(cast(Any, app))

        export_mock.assert_called_once()
        args = export_mock.call_args.args
        kwargs = export_mock.call_args.kwargs
        assert np.array_equal(args[0], sample_measurement["freqs"])
        assert set(args[1]) == {"S21", "S22"}
        assert args[2] == str(tmp_path)
        assert kwargs["filename"] == "manual_csv.csv"
        assert app.last_measurement is not None
        assert app.last_measurement["csv_path"] == str(chosen_path)
        app.log_message.assert_called_once_with(
            f"Exported CSV: {chosen_path}", "success"
        )
        app._notify_export_result.assert_called_once_with(
            kind="CSV",
            path=str(chosen_path),
            exported_items="S21, S22",
        )

    def test_export_touchstone_rejects_empty_trace_selection(
        self, sample_measurement: dict[str, Any], tmp_path: Path
    ) -> None:
        """Touchstone export should report an error when no traces are selected."""
        app = _FakeApp(
            sample_measurement, selected_params=(), output_folder=str(tmp_path)
        )
        chosen_path = tmp_path / "manual_touchstone.s2p"

        app._choose_measurement_export_path = cast(
            Any, lambda **kwargs: str(chosen_path)
        )
        app._get_selected_export_params = cast(Any, lambda: {})

        with patch.object(TouchstoneExporter, "export") as export_mock:
            VNAApp.handle_export_touchstone(cast(Any, app))

        export_mock.assert_not_called()
        app.log_message.assert_called_once_with(
            "No S-parameters selected for Touchstone export", "error"
        )

    def test_export_csv_rejects_empty_trace_selection(
        self, sample_measurement: dict[str, Any], tmp_path: Path
    ) -> None:
        """CSV export should report an error when no traces are selected."""
        app = _FakeApp(
            sample_measurement, selected_params=(), output_folder=str(tmp_path)
        )
        chosen_path = tmp_path / "manual_csv.csv"

        app._choose_measurement_export_path = cast(
            Any, lambda **kwargs: str(chosen_path)
        )
        app._get_selected_export_params = cast(Any, lambda: {})

        with patch.object(CsvExporter, "export") as export_mock:
            VNAApp.handle_export_csv(cast(Any, app))

        export_mock.assert_not_called()
        app.log_message.assert_called_once_with(
            "No S-parameters selected for CSV export", "error"
        )


@pytest.mark.unit
class TestMeasurementImportNotifications:
    """Tests for metadata-aware measurement import notifications."""

    def test_import_notification_reports_loaded_file_summary(self) -> None:
        """Import should show a toaster with the loaded file summary."""
        app = _FakeApp(None)
        chosen_path = "/tmp/imported_measurement.s2p"
        freqs = np.array([1.0e6, 2.0e6, 3.0e6], dtype=float)
        sparams = {
            "S11": (
                np.array([-10.0, -11.0, -12.0], dtype=float),
                np.array([5.0, 6.0, 7.0], dtype=float),
            ),
            "S21": (
                np.array([-1.0, -1.5, -2.0], dtype=float),
                np.array([45.0, 46.0, 47.0], dtype=float),
            ),
        }

        fake_root = MagicMock()

        import_result = SimpleNamespace(
            frequencies_hz=freqs,
            s_parameters=sparams,
            metadata=SimpleNamespace(
                notes_markdown="## Imported notes",
                machine_settings={
                    "setup": {"freq_unit": "MHz"},
                    "measurement": {
                        "plot_s11": True,
                        "plot_s21": True,
                        "plot_s12": False,
                        "plot_s22": False,
                    },
                },
            ),
        )

        with (
            patch("src.tina.main.tk.Tk", return_value=fake_root),
            patch(
                "src.tina.main.filedialog.askopenfilename",
                return_value=chosen_path,
            ),
            patch(
                "src.tina.main.TouchstoneExporter.import_with_metadata",
                return_value=import_result,
            ),
            patch("src.tina.main.asyncio.create_task"),
            patch("src.tina.main.setup_logic.refresh_export_template_validation"),
        ):
            VNAApp._import_measurement_output(
                cast(Any, app),
                restore_measurement=True,
            )

        assert app.last_measurement is not None
        assert app.last_measurement["touchstone_path"] == chosen_path
        assert app.last_measurement["notes"] == "## Imported notes"
        app._notify_import_result.assert_called_once_with(
            path=chosen_path,
            imported_items="2 traces, 3 points; restored Setup, Measurement",
        )
        app.log_message.assert_any_call("Imported 3 points, 2 S-parameters", "success")

    def test_import_notification_uses_trace_count_from_imported_data(self) -> None:
        """Import summary should reflect the imported trace and point counts."""
        app = _FakeApp(None)
        chosen_path = "/tmp/single_trace.s2p"
        freqs = np.array([1.0e6, 2.0e6], dtype=float)
        sparams = {
            "S22": (
                np.array([-20.0, -21.0], dtype=float),
                np.array([15.0, 16.0], dtype=float),
            ),
        }

        fake_root = MagicMock()

        import_result = SimpleNamespace(
            frequencies_hz=freqs,
            s_parameters=sparams,
            metadata=SimpleNamespace(
                notes_markdown="",
                machine_settings={},
            ),
        )

        with (
            patch("src.tina.main.tk.Tk", return_value=fake_root),
            patch(
                "src.tina.main.filedialog.askopenfilename",
                return_value=chosen_path,
            ),
            patch(
                "src.tina.main.TouchstoneExporter.import_with_metadata",
                return_value=import_result,
            ),
            patch("src.tina.main.asyncio.create_task"),
            patch("src.tina.main.setup_logic.refresh_export_template_validation"),
        ):
            VNAApp._import_measurement_output(
                cast(Any, app),
                restore_measurement=True,
            )

        app._notify_import_result.assert_called_once_with(
            path=chosen_path,
            imported_items="1 traces, 2 points; restored Setup, Measurement",
        )

    def test_import_restores_setup_fields_from_metadata(self) -> None:
        """Normal import should restore Setup tab widgets from metadata."""
        app = _FakeApp(None)
        chosen_path = "/tmp/restored_setup.s2p"
        freqs = np.array([1.0e6, 2.0e6], dtype=float)
        sparams = {
            "S11": (
                np.array([-10.0, -11.0], dtype=float),
                np.array([5.0, 6.0], dtype=float),
            ),
        }

        host_input = SimpleNamespace(value="")
        port_input = SimpleNamespace(value="")
        start_input = SimpleNamespace(value="")
        stop_input = SimpleNamespace(value="")
        points_input = SimpleNamespace(value="")
        avg_input = SimpleNamespace(value="")
        filename_input = SimpleNamespace(value="")
        folder_input = SimpleNamespace(value="")
        freq_unit_select = _FakeSelect("MHz")
        plot_type_select = _FakeSelect("magnitude")
        set_freq = _FakeCheckbox(False)
        set_points = _FakeCheckbox(False)
        averaging = _FakeCheckbox(False)
        set_avg = _FakeCheckbox(False)
        export_s11 = _FakeCheckbox(False)
        export_s21 = _FakeCheckbox(False)
        export_s12 = _FakeCheckbox(False)
        export_s22 = _FakeCheckbox(False)
        bundle_s2p = _FakeCheckbox(False)
        bundle_csv = _FakeCheckbox(False)
        bundle_png = _FakeCheckbox(False)
        bundle_svg = _FakeCheckbox(False)
        plot_s11 = _FakeCheckbox(False)
        plot_s21 = _FakeCheckbox(False)
        plot_s12 = _FakeCheckbox(False)
        plot_s22 = _FakeCheckbox(False)

        app.query_one = cast(
            Any,
            lambda selector, _widget_type=None: {
                "#input_host": host_input,
                "#input_port": port_input,
                "#input_start_freq": start_input,
                "#input_stop_freq": stop_input,
                "#input_points": points_input,
                "#input_avg_count": avg_input,
                "#input_filename_prefix": filename_input,
                "#input_output_folder": folder_input,
                "#select_freq_unit": freq_unit_select,
                "#select_plot_type": plot_type_select,
                "#check_set_freq": set_freq,
                "#check_set_points": set_points,
                "#check_averaging": averaging,
                "#check_set_avg_count": set_avg,
                "#check_export_s11": export_s11,
                "#check_export_s21": export_s21,
                "#check_export_s12": export_s12,
                "#check_export_s22": export_s22,
                "#check_export_bundle_s2p": bundle_s2p,
                "#check_export_bundle_csv": bundle_csv,
                "#check_export_bundle_png": bundle_png,
                "#check_export_bundle_svg": bundle_svg,
                "#check_plot_s11": plot_s11,
                "#check_plot_s21": plot_s21,
                "#check_plot_s12": plot_s12,
                "#check_plot_s22": plot_s22,
                TabbedContent: app._tabbed_content,
            }[selector],
        )

        import_result = SimpleNamespace(
            frequencies_hz=freqs,
            s_parameters=sparams,
            metadata=SimpleNamespace(
                notes_markdown="## Imported notes",
                machine_settings={
                    "setup": {
                        "host": "192.168.1.50",
                        "port": "inst0",
                        "freq_unit": "GHz",
                        "start_freq_mhz": 100.0,
                        "stop_freq_mhz": 200.0,
                        "sweep_points": 401,
                        "averaging_count": 8,
                        "set_freq_range": True,
                        "set_sweep_points": True,
                        "enable_averaging": True,
                        "set_averaging_count": True,
                        "output_folder": "exports/run42",
                        "folder_template": "exports/by_host/{host}",
                        "filename_template": "run42_{date}",
                        "export_s11": True,
                        "export_s21": False,
                        "export_s12": False,
                        "export_s22": True,
                        "export_bundle_s2p": True,
                        "export_bundle_csv": True,
                        "export_bundle_png": True,
                        "export_bundle_svg": False,
                    },
                    "measurement": {
                        "plot_type": "phase",
                        "plot_s11": True,
                        "plot_s21": False,
                        "plot_s12": False,
                        "plot_s22": True,
                    },
                },
            ),
        )

        fake_root = MagicMock()

        with (
            patch("src.tina.main.tk.Tk", return_value=fake_root),
            patch(
                "src.tina.main.filedialog.askopenfilename",
                return_value=chosen_path,
            ),
            patch(
                "src.tina.main.TouchstoneExporter.import_with_metadata",
                return_value=import_result,
            ),
            patch("src.tina.main.asyncio.create_task"),
            patch("src.tina.main.setup_logic.refresh_export_template_validation"),
        ):
            VNAApp._import_measurement_output(
                cast(Any, app),
                restore_measurement=True,
            )

        assert host_input.value == "192.168.1.50"
        assert port_input.value == "inst0"
        assert freq_unit_select.value == "GHz"
        assert start_input.value == "100.0"
        assert stop_input.value == "200.0"
        assert points_input.value == "401"
        assert avg_input.value == "8"
        assert filename_input.value == "run42_{date}"
        assert folder_input.value == "exports/by_host/{host}"
        assert set_freq.value is True
        assert set_points.value is True
        assert averaging.value is True
        assert set_avg.value is True
        assert export_s11.value is True
        assert export_s21.value is False
        assert export_s22.value is True
        assert bundle_s2p.value is True
        assert bundle_csv.value is True
        assert bundle_png.value is True
        assert bundle_svg.value is False
        assert plot_type_select.value == "phase"
        assert plot_s11.value is True
        assert plot_s21.value is False
        assert plot_s22.value is True
        assert app._tabbed_content.active == "tab_measure"

    def test_setup_only_import_restores_setup_without_measurement_state(self) -> None:
        """Setup-only import should restore Setup widgets without replacing measurement data."""
        existing_measurement = {
            "freqs": np.array([9.0e6], dtype=float),
            "sparams": {},
            "output_path": "measurement/existing.s2p",
            "notes": "keep me",
        }
        app = _FakeApp(existing_measurement)
        chosen_path = "/tmp/setup_only.s2p"

        host_input = SimpleNamespace(value="")
        port_input = SimpleNamespace(value="")
        start_input = SimpleNamespace(value="")
        stop_input = SimpleNamespace(value="")
        points_input = SimpleNamespace(value="")
        avg_input = SimpleNamespace(value="")
        filename_input = SimpleNamespace(value="")
        folder_input = SimpleNamespace(value="")
        freq_unit_select = _FakeSelect("MHz")
        plot_type_select = _FakeSelect("magnitude")
        set_freq = _FakeCheckbox(False)
        set_points = _FakeCheckbox(False)
        averaging = _FakeCheckbox(False)
        set_avg = _FakeCheckbox(False)
        export_s11 = _FakeCheckbox(False)
        export_s21 = _FakeCheckbox(False)
        export_s12 = _FakeCheckbox(False)
        export_s22 = _FakeCheckbox(False)
        bundle_s2p = _FakeCheckbox(False)
        bundle_csv = _FakeCheckbox(False)
        bundle_png = _FakeCheckbox(False)
        bundle_svg = _FakeCheckbox(False)

        app.query_one = cast(
            Any,
            lambda selector, _widget_type=None: {
                "#input_host": host_input,
                "#input_port": port_input,
                "#input_start_freq": start_input,
                "#input_stop_freq": stop_input,
                "#input_points": points_input,
                "#input_avg_count": avg_input,
                "#input_filename_prefix": filename_input,
                "#input_output_folder": folder_input,
                "#select_freq_unit": freq_unit_select,
                "#select_plot_type": plot_type_select,
                "#check_set_freq": set_freq,
                "#check_set_points": set_points,
                "#check_averaging": averaging,
                "#check_set_avg_count": set_avg,
                "#check_export_s11": export_s11,
                "#check_export_s21": export_s21,
                "#check_export_s12": export_s12,
                "#check_export_s22": export_s22,
                "#check_export_bundle_s2p": bundle_s2p,
                "#check_export_bundle_csv": bundle_csv,
                "#check_export_bundle_png": bundle_png,
                "#check_export_bundle_svg": bundle_svg,
                TabbedContent: app._tabbed_content,
            }[selector],
        )

        import_result = SimpleNamespace(
            frequencies_hz=np.array([1.0e6, 2.0e6], dtype=float),
            s_parameters={
                "S21": (
                    np.array([-1.0, -2.0], dtype=float),
                    np.array([45.0, 46.0], dtype=float),
                )
            },
            metadata=SimpleNamespace(
                notes_markdown="ignored",
                machine_settings={
                    "setup": {
                        "host": "10.0.0.5",
                        "port": "hislip0",
                        "freq_unit": "kHz",
                        "start_freq_mhz": 1.5,
                        "stop_freq_mhz": 2.5,
                        "sweep_points": 201,
                        "averaging_count": 4,
                        "set_freq_range": True,
                        "set_sweep_points": False,
                        "enable_averaging": True,
                        "set_averaging_count": False,
                        "output_folder": "restored/setup",
                        "folder_template": "restored/templates/{date}",
                        "filename_template": "setup_only_{time}",
                        "export_s11": False,
                        "export_s21": True,
                        "export_s12": False,
                        "export_s22": False,
                        "export_bundle_s2p": True,
                        "export_bundle_csv": False,
                        "export_bundle_png": False,
                        "export_bundle_svg": True,
                    }
                },
            ),
        )

        fake_root = MagicMock()

        with (
            patch("src.tina.main.tk.Tk", return_value=fake_root),
            patch(
                "src.tina.main.filedialog.askopenfilename",
                return_value=chosen_path,
            ),
            patch(
                "src.tina.main.TouchstoneExporter.import_with_metadata",
                return_value=import_result,
            ),
            patch("src.tina.main.setup_logic.refresh_export_template_validation"),
        ):
            VNAApp._import_measurement_output(
                cast(Any, app),
                restore_measurement=False,
            )

        assert host_input.value == "10.0.0.5"
        assert port_input.value == "hislip0"
        assert freq_unit_select.value == "kHz"
        assert start_input.value == "1.5"
        assert stop_input.value == "2.5"
        assert points_input.value == "201"
        assert avg_input.value == "4"
        assert filename_input.value == "setup_only_{time}"
        assert folder_input.value == "restored/templates/{date}"
        assert export_s21.value is True
        assert bundle_s2p.value is True
        assert bundle_svg.value is True
        assert app.last_measurement is existing_measurement
        app._notify_import_result.assert_not_called()
        app.notify.assert_called_once_with(
            "Loaded setup from setup_only.s2p — restored Setup",
            severity="information",
            timeout=4,
        )


@pytest.mark.integration
class TestMeasurementOutputRoundTrips:
    """End-to-end roundtrip tests for exported measurement outputs."""

    def test_touchstone_export_then_import_restores_measurement_state(
        self, sample_measurement: dict[str, Any], tmp_path: Path
    ) -> None:
        """Touchstone export should roundtrip through app import with metadata."""
        export_path = TouchstoneExporter().export(
            sample_measurement["freqs"],
            {
                "S11": sample_measurement["sparams"]["S11"],
                "S21": sample_measurement["sparams"]["S21"],
            },
            str(tmp_path),
            filename="roundtrip.s2p",
            notes_markdown=sample_measurement["notes"],
            metadata={
                "setup": {
                    "host": "192.168.1.50",
                    "port": "inst0",
                    "freq_unit": "MHz",
                    "start_freq_mhz": 1.0,
                    "stop_freq_mhz": 3.0,
                    "sweep_points": 3,
                    "averaging_count": 4,
                    "set_freq_range": True,
                    "set_sweep_points": True,
                    "enable_averaging": True,
                    "set_averaging_count": True,
                    "output_folder": "exports/from_touchstone",
                    "folder_template": "exports/{host}",
                    "filename_template": "roundtrip_{date}",
                    "export_s11": True,
                    "export_s21": True,
                    "export_s12": False,
                    "export_s22": False,
                    "export_bundle_s2p": True,
                    "export_bundle_csv": False,
                    "export_bundle_png": True,
                    "export_bundle_svg": True,
                },
                "measurement": {
                    "plot_type": "phase",
                    "plot_s11": True,
                    "plot_s21": True,
                    "plot_s12": False,
                    "plot_s22": False,
                },
            },
        )

        app = _FakeApp(None)

        host_input = SimpleNamespace(value="")
        port_input = SimpleNamespace(value="")
        start_input = SimpleNamespace(value="")
        stop_input = SimpleNamespace(value="")
        points_input = SimpleNamespace(value="")
        avg_input = SimpleNamespace(value="")
        filename_input = SimpleNamespace(value="")
        folder_input = SimpleNamespace(value="")
        freq_unit_select = _FakeSelect("GHz")
        plot_type_select = _FakeSelect("magnitude")
        set_freq = _FakeCheckbox(False)
        set_points = _FakeCheckbox(False)
        averaging = _FakeCheckbox(False)
        set_avg = _FakeCheckbox(False)
        export_s11 = _FakeCheckbox(False)
        export_s21 = _FakeCheckbox(False)
        export_s12 = _FakeCheckbox(False)
        export_s22 = _FakeCheckbox(False)
        bundle_s2p = _FakeCheckbox(False)
        bundle_csv = _FakeCheckbox(False)
        bundle_png = _FakeCheckbox(False)
        bundle_svg = _FakeCheckbox(False)
        plot_s11 = _FakeCheckbox(False)
        plot_s21 = _FakeCheckbox(False)
        plot_s12 = _FakeCheckbox(False)
        plot_s22 = _FakeCheckbox(False)

        app.query_one = cast(
            Any,
            lambda selector, _widget_type=None: {
                "#input_host": host_input,
                "#input_port": port_input,
                "#input_start_freq": start_input,
                "#input_stop_freq": stop_input,
                "#input_points": points_input,
                "#input_avg_count": avg_input,
                "#input_filename_prefix": filename_input,
                "#input_output_folder": folder_input,
                "#select_freq_unit": freq_unit_select,
                "#select_plot_type": plot_type_select,
                "#check_set_freq": set_freq,
                "#check_set_points": set_points,
                "#check_averaging": averaging,
                "#check_set_avg_count": set_avg,
                "#check_export_s11": export_s11,
                "#check_export_s21": export_s21,
                "#check_export_s12": export_s12,
                "#check_export_s22": export_s22,
                "#check_export_bundle_s2p": bundle_s2p,
                "#check_export_bundle_csv": bundle_csv,
                "#check_export_bundle_png": bundle_png,
                "#check_export_bundle_svg": bundle_svg,
                "#check_plot_s11": plot_s11,
                "#check_plot_s21": plot_s21,
                "#check_plot_s12": plot_s12,
                "#check_plot_s22": plot_s22,
                TabbedContent: app._tabbed_content,
            }[selector],
        )

        fake_root = MagicMock()

        with (
            patch("src.tina.main.tk.Tk", return_value=fake_root),
            patch(
                "src.tina.main.filedialog.askopenfilename",
                return_value=export_path,
            ),
            patch("src.tina.main.asyncio.create_task"),
            patch("src.tina.main.setup_logic.refresh_export_template_validation"),
        ):
            VNAApp._import_measurement_output(
                cast(Any, app),
                restore_measurement=True,
            )

        assert app.last_measurement is not None
        np.testing.assert_allclose(
            app.last_measurement["freqs"], sample_measurement["freqs"]
        )
        assert set(app.last_measurement["sparams"]) == {"S11", "S21"}
        assert app.last_measurement["notes"] == sample_measurement["notes"]
        assert app.last_measurement["touchstone_path"] == export_path
        assert host_input.value == "192.168.1.50"
        assert folder_input.value == "exports/{host}"
        assert filename_input.value == "roundtrip_{date}"
        assert plot_type_select.value == "phase"
        assert plot_s11.value is True
        assert plot_s21.value is True
        assert app._tabbed_content.active == "tab_measure"

    def test_png_export_then_import_restores_measurement_state(
        self, sample_measurement: dict[str, Any], tmp_path: Path
    ) -> None:
        """PNG export metadata should roundtrip through app import."""
        export_path = tmp_path / "roundtrip.png"
        Image.new("RGB", (16, 16), color="black").save(export_path)

        embed_png_metadata(
            export_path,
            notes_markdown=sample_measurement["notes"],
            machine_settings={
                "setup": {
                    "host": "10.0.0.5",
                    "port": "hislip0",
                    "freq_unit": "MHz",
                    "start_freq_mhz": 1.0,
                    "stop_freq_mhz": 3.0,
                    "sweep_points": 3,
                    "averaging_count": 2,
                    "set_freq_range": True,
                    "set_sweep_points": True,
                    "enable_averaging": False,
                    "set_averaging_count": False,
                    "output_folder": "exports/from_png",
                    "folder_template": "exports/png/{date}",
                    "filename_template": "png_roundtrip_{time}",
                    "export_s11": True,
                    "export_s21": True,
                    "export_s12": False,
                    "export_s22": False,
                    "export_bundle_s2p": True,
                    "export_bundle_csv": False,
                    "export_bundle_png": True,
                    "export_bundle_svg": False,
                },
                "measurement": {
                    "plot_type": "magnitude",
                    "plot_s11": True,
                    "plot_s21": True,
                    "plot_s12": False,
                    "plot_s22": False,
                    "raw_data": {
                        "freqs_hz": sample_measurement["freqs"].tolist(),
                        "sparams": {
                            name: {
                                "magnitude_db": values[0].tolist(),
                                "phase_deg": values[1].tolist(),
                            }
                            for name, values in sample_measurement["sparams"].items()
                        },
                    },
                },
            },
        )

        app = _FakeApp(None)

        host_input = SimpleNamespace(value="")
        port_input = SimpleNamespace(value="")
        start_input = SimpleNamespace(value="")
        stop_input = SimpleNamespace(value="")
        points_input = SimpleNamespace(value="")
        avg_input = SimpleNamespace(value="")
        filename_input = SimpleNamespace(value="")
        folder_input = SimpleNamespace(value="")
        freq_unit_select = _FakeSelect("GHz")
        plot_type_select = _FakeSelect("phase")
        set_freq = _FakeCheckbox(False)
        set_points = _FakeCheckbox(False)
        averaging = _FakeCheckbox(False)
        set_avg = _FakeCheckbox(False)
        export_s11 = _FakeCheckbox(False)
        export_s21 = _FakeCheckbox(False)
        export_s12 = _FakeCheckbox(False)
        export_s22 = _FakeCheckbox(False)
        bundle_s2p = _FakeCheckbox(False)
        bundle_csv = _FakeCheckbox(False)
        bundle_png = _FakeCheckbox(False)
        bundle_svg = _FakeCheckbox(False)
        plot_s11 = _FakeCheckbox(False)
        plot_s21 = _FakeCheckbox(False)
        plot_s12 = _FakeCheckbox(False)
        plot_s22 = _FakeCheckbox(False)

        app.query_one = cast(
            Any,
            lambda selector, _widget_type=None: {
                "#input_host": host_input,
                "#input_port": port_input,
                "#input_start_freq": start_input,
                "#input_stop_freq": stop_input,
                "#input_points": points_input,
                "#input_avg_count": avg_input,
                "#input_filename_prefix": filename_input,
                "#input_output_folder": folder_input,
                "#select_freq_unit": freq_unit_select,
                "#select_plot_type": plot_type_select,
                "#check_set_freq": set_freq,
                "#check_set_points": set_points,
                "#check_averaging": averaging,
                "#check_set_avg_count": set_avg,
                "#check_export_s11": export_s11,
                "#check_export_s21": export_s21,
                "#check_export_s12": export_s12,
                "#check_export_s22": export_s22,
                "#check_export_bundle_s2p": bundle_s2p,
                "#check_export_bundle_csv": bundle_csv,
                "#check_export_bundle_png": bundle_png,
                "#check_export_bundle_svg": bundle_svg,
                "#check_plot_s11": plot_s11,
                "#check_plot_s21": plot_s21,
                "#check_plot_s12": plot_s12,
                "#check_plot_s22": plot_s22,
                TabbedContent: app._tabbed_content,
            }[selector],
        )

        fake_root = MagicMock()

        with (
            patch("src.tina.main.tk.Tk", return_value=fake_root),
            patch(
                "src.tina.main.filedialog.askopenfilename",
                return_value=str(export_path),
            ),
            patch("src.tina.main.asyncio.create_task"),
            patch("src.tina.main.setup_logic.refresh_export_template_validation"),
        ):
            VNAApp._import_measurement_output(
                cast(Any, app),
                restore_measurement=True,
            )

        assert app.last_measurement is not None
        np.testing.assert_allclose(
            app.last_measurement["freqs"], sample_measurement["freqs"]
        )
        assert set(app.last_measurement["sparams"]) == {"S11", "S21", "S12", "S22"}
        assert app.last_measurement["png_path"] == str(export_path)
        assert app.last_measurement["notes"] == sample_measurement["notes"]
        assert host_input.value == "10.0.0.5"
        assert folder_input.value == "exports/png/{date}"
        assert filename_input.value == "png_roundtrip_{time}"
        assert plot_type_select.value == "magnitude"
        assert plot_s11.value is True
        assert plot_s21.value is True
        assert app._tabbed_content.active == "tab_measure"

    def test_svg_export_then_import_restores_measurement_state(
        self, sample_measurement: dict[str, Any], tmp_path: Path
    ) -> None:
        """SVG export metadata should roundtrip through app import."""
        export_path = tmp_path / "roundtrip.svg"
        export_path.write_text("<svg></svg>", encoding="utf-8")

        embed_svg_metadata(
            export_path,
            notes_markdown=sample_measurement["notes"],
            machine_settings={
                "setup": {
                    "host": "172.16.0.10",
                    "port": "inst0",
                    "freq_unit": "MHz",
                    "start_freq_mhz": 1.0,
                    "stop_freq_mhz": 3.0,
                    "sweep_points": 3,
                    "averaging_count": 1,
                    "set_freq_range": True,
                    "set_sweep_points": True,
                    "enable_averaging": True,
                    "set_averaging_count": False,
                    "output_folder": "exports/from_svg",
                    "folder_template": "exports/svg/{model}",
                    "filename_template": "svg_roundtrip_{date}",
                    "export_s11": False,
                    "export_s21": True,
                    "export_s12": False,
                    "export_s22": True,
                    "export_bundle_s2p": True,
                    "export_bundle_csv": False,
                    "export_bundle_png": False,
                    "export_bundle_svg": True,
                },
                "measurement": {
                    "plot_type": "phase",
                    "plot_s11": False,
                    "plot_s21": True,
                    "plot_s12": False,
                    "plot_s22": True,
                    "raw_data": {
                        "freqs_hz": sample_measurement["freqs"].tolist(),
                        "sparams": {
                            name: {
                                "magnitude_db": values[0].tolist(),
                                "phase_deg": values[1].tolist(),
                            }
                            for name, values in sample_measurement["sparams"].items()
                        },
                    },
                },
            },
        )

        app = _FakeApp(None)

        host_input = SimpleNamespace(value="")
        port_input = SimpleNamespace(value="")
        start_input = SimpleNamespace(value="")
        stop_input = SimpleNamespace(value="")
        points_input = SimpleNamespace(value="")
        avg_input = SimpleNamespace(value="")
        filename_input = SimpleNamespace(value="")
        folder_input = SimpleNamespace(value="")
        freq_unit_select = _FakeSelect("GHz")
        plot_type_select = _FakeSelect("magnitude")
        set_freq = _FakeCheckbox(False)
        set_points = _FakeCheckbox(False)
        averaging = _FakeCheckbox(False)
        set_avg = _FakeCheckbox(False)
        export_s11 = _FakeCheckbox(False)
        export_s21 = _FakeCheckbox(False)
        export_s12 = _FakeCheckbox(False)
        export_s22 = _FakeCheckbox(False)
        bundle_s2p = _FakeCheckbox(False)
        bundle_csv = _FakeCheckbox(False)
        bundle_png = _FakeCheckbox(False)
        bundle_svg = _FakeCheckbox(False)
        plot_s11 = _FakeCheckbox(False)
        plot_s21 = _FakeCheckbox(False)
        plot_s12 = _FakeCheckbox(False)
        plot_s22 = _FakeCheckbox(False)

        app.query_one = cast(
            Any,
            lambda selector, _widget_type=None: {
                "#input_host": host_input,
                "#input_port": port_input,
                "#input_start_freq": start_input,
                "#input_stop_freq": stop_input,
                "#input_points": points_input,
                "#input_avg_count": avg_input,
                "#input_filename_prefix": filename_input,
                "#input_output_folder": folder_input,
                "#select_freq_unit": freq_unit_select,
                "#select_plot_type": plot_type_select,
                "#check_set_freq": set_freq,
                "#check_set_points": set_points,
                "#check_averaging": averaging,
                "#check_set_avg_count": set_avg,
                "#check_export_s11": export_s11,
                "#check_export_s21": export_s21,
                "#check_export_s12": export_s12,
                "#check_export_s22": export_s22,
                "#check_export_bundle_s2p": bundle_s2p,
                "#check_export_bundle_csv": bundle_csv,
                "#check_export_bundle_png": bundle_png,
                "#check_export_bundle_svg": bundle_svg,
                "#check_plot_s11": plot_s11,
                "#check_plot_s21": plot_s21,
                "#check_plot_s12": plot_s12,
                "#check_plot_s22": plot_s22,
                TabbedContent: app._tabbed_content,
            }[selector],
        )

        fake_root = MagicMock()

        with (
            patch("src.tina.main.tk.Tk", return_value=fake_root),
            patch(
                "src.tina.main.filedialog.askopenfilename",
                return_value=str(export_path),
            ),
            patch("src.tina.main.asyncio.create_task"),
            patch("src.tina.main.setup_logic.refresh_export_template_validation"),
        ):
            VNAApp._import_measurement_output(
                cast(Any, app),
                restore_measurement=True,
            )

        assert app.last_measurement is not None
        np.testing.assert_allclose(
            app.last_measurement["freqs"], sample_measurement["freqs"]
        )
        assert set(app.last_measurement["sparams"]) == {"S11", "S21", "S12", "S22"}
        assert app.last_measurement["svg_path"] == str(export_path)
        assert app.last_measurement["notes"] == sample_measurement["notes"]
        assert host_input.value == "172.16.0.10"
        assert folder_input.value == "exports/svg/{model}"
        assert filename_input.value == "svg_roundtrip_{date}"
        assert plot_type_select.value == "phase"
        assert plot_s11.value is False
        assert plot_s21.value is True
        assert plot_s22.value is True
        assert app._tabbed_content.active == "tab_measure"
