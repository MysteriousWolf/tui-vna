"""Tests for direct Measurement tab export helpers."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from src.tina.export import CsvExporter
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
        self.settings = SimpleNamespace(output_folder=output_folder)
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
        self._notify_export_result = MagicMock()
        self._notify_import_result = MagicMock()
        self._load_measurement_notes_into_editor = MagicMock()
        self._refresh_measurement_notes_preview = MagicMock()
        self._refresh_tools_plot = MagicMock(return_value=None)
        self._run_tools_computation = MagicMock()
        self._rebuild_tools_params = MagicMock()
        self.call_after_refresh = MagicMock()
        self._update_results = MagicMock(return_value=None)

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
            patch("src.tina.main.create_matplotlib_plot") as create_plot,
            patch("src.tina.main.get_plot_colors", return_value={"fg": "#fff"}),
        ):
            VNAApp.handle_export_png(cast(Any, app))

        create_plot.assert_called_once()
        args = create_plot.call_args.args
        assert np.array_equal(args[0], sample_measurement["freqs"])
        assert args[1] is sample_measurement["sparams"]
        assert args[2] == ["S11", "S22"]
        assert args[3] == "magnitude"
        assert args[4] == chosen_path
        app.log_message.assert_called_once_with(
            f"Exported PNG: {chosen_path}", "success"
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
            patch("src.tina.main.create_smith_chart") as create_smith,
            patch("src.tina.main.get_plot_colors", return_value={"fg": "#fff"}),
        ):
            VNAApp.handle_export_svg(cast(Any, app))

        create_smith.assert_called_once()
        args = create_smith.call_args.args
        assert np.array_equal(args[0], sample_measurement["freqs"])
        assert args[1] is sample_measurement["sparams"]
        assert args[2] == ["S21"]
        assert args[3] == chosen_path
        app.log_message.assert_called_once_with(
            f"Exported SVG: {chosen_path}", "success"
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

        with patch.object(
            TouchstoneExporter, "export", return_value=str(chosen_path)
        ) as export_mock:
            VNAApp.handle_export_touchstone(cast(Any, app))

        export_mock.assert_called_once()
        args = export_mock.call_args.args
        kwargs = export_mock.call_args.kwargs
        assert np.array_equal(args[0], sample_measurement["freqs"])
        assert set(args[1]) == {"S11", "S21"}
        assert args[2] == str(tmp_path)
        assert kwargs["filename"] == "manual_touchstone.s2p"
        assert kwargs["notes_markdown"] == sample_measurement["notes"]
        assert kwargs["metadata"] == {
            "setup": {"host": "lab-vna", "freq_unit": "MHz"},
            "measurement": {"exported_traces": ["S11", "S21"]},
        }
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
            patch("src.tina.main.filedialog.askopenfilename", return_value=chosen_path),
            patch(
                "src.tina.main.TouchstoneExporter.import_with_metadata",
                return_value=import_result,
            ),
            patch("src.tina.main.asyncio.create_task"),
        ):
            VNAApp.handle_import_results(cast(Any, app))

        assert app.last_measurement is not None
        assert app.last_measurement["touchstone_path"] == chosen_path
        assert app.last_measurement["notes"] == "## Imported notes"
        app._notify_import_result.assert_called_once_with(
            path=chosen_path,
            imported_items="2 traces, 3 points",
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
            patch("src.tina.main.filedialog.askopenfilename", return_value=chosen_path),
            patch(
                "src.tina.main.TouchstoneExporter.import_with_metadata",
                return_value=import_result,
            ),
            patch("src.tina.main.asyncio.create_task"),
        ):
            VNAApp.handle_import_results(cast(Any, app))

        app._notify_import_result.assert_called_once_with(
            path=chosen_path,
            imported_items="1 traces, 2 points",
        )
