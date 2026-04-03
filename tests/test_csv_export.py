"""Tests for CSV measurement export functionality."""

from __future__ import annotations

import csv
from pathlib import Path

import numpy as np
import pytest

from src.tina.export import (
    DEFAULT_TEMPLATE_TAGS,
    build_export_template_context,
    render_template,
)
from src.tina.export.csv import CsvExporter


@pytest.fixture
def sample_export_context() -> dict[str, object]:
    """Provide a representative export template context."""
    return build_export_template_context(
        host="192.168.1.50",
        vendor="keysight",
        model="E5071B",
        start="1",
        stop="1100",
        span="1099",
        pts=3,
        avg=16,
        ifbw="10",
        cal=True,
    )


@pytest.fixture
def sample_frequencies() -> np.ndarray:
    """Provide a small frequency sweep in Hz."""
    return np.array([1.0e6, 2.0e6, 3.0e6], dtype=float)


@pytest.fixture
def sample_sparameters() -> dict[str, tuple[np.ndarray, np.ndarray]]:
    """Provide representative S-parameter magnitude/phase data."""
    return {
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


@pytest.mark.unit
class TestCsvExporter:
    """Tests for CSV export behavior."""

    def test_initialization_uses_default_frequency_unit(self) -> None:
        """Exporter should default to MHz output."""
        exporter = CsvExporter()

        assert exporter.freq_unit == "MHz"

    def test_initialization_accepts_custom_frequency_unit(self) -> None:
        """Exporter should preserve a custom frequency unit."""
        exporter = CsvExporter(freq_unit="GHz")

        assert exporter.freq_unit == "GHz"

    def test_export_writes_csv_file_with_expected_header(
        self,
        tmp_path: Path,
        sample_frequencies: np.ndarray,
        sample_sparameters: dict[str, tuple[np.ndarray, np.ndarray]],
    ) -> None:
        """Exporter should write a tabular CSV with frequency and trace columns."""
        exporter = CsvExporter(freq_unit="MHz")

        output_path = exporter.export(
            sample_frequencies,
            {
                "S11": sample_sparameters["S11"],
                "S21": sample_sparameters["S21"],
            },
            str(tmp_path),
            filename="measurement_run",
        )

        assert output_path.endswith(".csv")
        assert Path(output_path).exists()

        with open(output_path, newline="", encoding="utf-8") as csv_file:
            rows = list(csv.reader(csv_file))

        assert rows[0] == [
            "frequency_mhz",
            "S11_magnitude_db",
            "S11_phase_deg",
            "S21_magnitude_db",
            "S21_phase_deg",
        ]
        assert rows[1] == [
            "1.000000",
            "-10.000000",
            "5.000000",
            "-1.000000",
            "45.000000",
        ]
        assert rows[3] == [
            "3.000000",
            "-12.000000",
            "7.000000",
            "-2.000000",
            "47.000000",
        ]

    def test_export_creates_output_directory(
        self,
        tmp_path: Path,
        sample_frequencies: np.ndarray,
        sample_sparameters: dict[str, tuple[np.ndarray, np.ndarray]],
    ) -> None:
        """Exporter should create nested output directories automatically."""
        exporter = CsvExporter()
        output_dir = tmp_path / "nested" / "exports"

        output_path = exporter.export(
            sample_frequencies,
            {"S11": sample_sparameters["S11"]},
            str(output_dir),
            filename="trace.csv",
        )

        assert output_dir.exists()
        assert Path(output_path).exists()

    def test_export_adds_csv_extension_when_missing(
        self,
        tmp_path: Path,
        sample_frequencies: np.ndarray,
        sample_sparameters: dict[str, tuple[np.ndarray, np.ndarray]],
    ) -> None:
        """Exporter should append the CSV extension when needed."""
        exporter = CsvExporter()

        output_path = exporter.export(
            sample_frequencies,
            {"S11": sample_sparameters["S11"]},
            str(tmp_path),
            filename="trace_export",
        )

        assert output_path.endswith(".csv")

    def test_export_uses_prefix_for_auto_generated_filename(
        self,
        tmp_path: Path,
        sample_frequencies: np.ndarray,
        sample_sparameters: dict[str, tuple[np.ndarray, np.ndarray]],
    ) -> None:
        """Exporter should use the provided prefix for generated filenames."""
        exporter = CsvExporter()

        output_path = exporter.export(
            sample_frequencies,
            {"S11": sample_sparameters["S11"]},
            str(tmp_path),
            prefix="bundle_run",
        )

        assert Path(output_path).name.startswith("bundle_run_")
        assert output_path.endswith(".csv")

    def test_export_supports_partial_sparameter_selection(
        self,
        tmp_path: Path,
        sample_frequencies: np.ndarray,
        sample_sparameters: dict[str, tuple[np.ndarray, np.ndarray]],
    ) -> None:
        """Exporter should include only the selected traces in column order."""
        exporter = CsvExporter()

        output_path = exporter.export(
            sample_frequencies,
            {
                "S21": sample_sparameters["S21"],
                "S22": sample_sparameters["S22"],
            },
            str(tmp_path),
            filename="selected_only.csv",
        )

        with open(output_path, newline="", encoding="utf-8") as csv_file:
            rows = list(csv.reader(csv_file))

        assert rows[0] == [
            "frequency_mhz",
            "S21_magnitude_db",
            "S21_phase_deg",
            "S22_magnitude_db",
            "S22_phase_deg",
        ]
        assert rows[1] == [
            "1.000000",
            "-1.000000",
            "45.000000",
            "-20.000000",
            "15.000000",
        ]

    def test_export_rejects_length_mismatch(
        self,
        tmp_path: Path,
        sample_frequencies: np.ndarray,
    ) -> None:
        """Exporter should reject traces whose lengths do not match the sweep."""
        exporter = CsvExporter()
        bad_sparameters = {
            "S11": (
                np.array([-10.0, -11.0, -12.0], dtype=float),
                np.array([1.0, 2.0], dtype=float),
            )
        }

        with pytest.raises(ValueError, match="length mismatch"):
            exporter.export(sample_frequencies, bad_sparameters, str(tmp_path))

    def test_export_rejects_empty_sparameter_selection(
        self,
        tmp_path: Path,
        sample_frequencies: np.ndarray,
    ) -> None:
        """Exporter should fail when no traces are selected for export."""
        exporter = CsvExporter()

        with pytest.raises(ValueError, match="No valid S-parameters"):
            exporter.export(sample_frequencies, {}, str(tmp_path))

    def test_export_converts_frequency_to_selected_unit(
        self,
        tmp_path: Path,
        sample_frequencies: np.ndarray,
        sample_sparameters: dict[str, tuple[np.ndarray, np.ndarray]],
    ) -> None:
        """Exporter should convert frequency values to the configured unit."""
        exporter = CsvExporter(freq_unit="GHz")

        output_path = exporter.export(
            sample_frequencies,
            {"S11": sample_sparameters["S11"]},
            str(tmp_path),
            filename="ghz.csv",
        )

        with open(output_path, newline="", encoding="utf-8") as csv_file:
            rows = list(csv.reader(csv_file))

        assert rows[0][0] == "frequency_ghz"
        assert rows[1][0] == "0.001000"
        assert rows[3][0] == "0.003000"

    def test_rendered_template_filename_can_be_used_for_csv_export(
        self,
        tmp_path: Path,
        sample_export_context: dict[str, object],
        sample_frequencies: np.ndarray,
        sample_sparameters: dict[str, tuple[np.ndarray, np.ndarray]],
    ) -> None:
        """Rendered filename templates should feed directly into CSV export naming."""
        exporter = CsvExporter()

        rendered = render_template(
            "capture_{host}_{pts}",
            context=sample_export_context,
            allowed_tags=set(DEFAULT_TEMPLATE_TAGS),
        )

        output_path = exporter.export(
            sample_frequencies,
            {"S11": sample_sparameters["S11"]},
            str(tmp_path),
            filename=rendered.rendered,
        )

        assert Path(output_path).name == "capture_192.168.1.50_3.csv"

    def test_rendered_folder_template_can_be_used_for_csv_export(
        self,
        tmp_path: Path,
        sample_export_context: dict[str, object],
        sample_frequencies: np.ndarray,
        sample_sparameters: dict[str, tuple[np.ndarray, np.ndarray]],
    ) -> None:
        """Rendered folder templates should work as export destinations."""
        exporter = CsvExporter()

        rendered_folder = render_template(
            "exports/{host}",
            context=sample_export_context,
            allowed_tags=set(DEFAULT_TEMPLATE_TAGS),
        )

        output_path = exporter.export(
            sample_frequencies,
            {"S11": sample_sparameters["S11"]},
            str(tmp_path / rendered_folder.rendered),
            filename="templated.csv",
        )

        assert Path(output_path).parent == tmp_path / "exports" / "192.168.1.50"
        assert Path(output_path).exists()
