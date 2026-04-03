"""Reusable CSV export utilities for measurement data."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import numpy as np

_TRACE_ORDER: tuple[str, ...] = ("S11", "S21", "S12", "S22")
_FREQ_UNIT_FACTORS: dict[str, float] = {
    "Hz": 1.0,
    "kHz": 1e3,
    "MHz": 1e6,
    "GHz": 1e9,
}


@dataclass(slots=True, frozen=True)
class CsvExportResult:
    """Result metadata for a completed CSV export."""

    path: str
    trace_names: tuple[str, ...]
    row_count: int


class CsvExporter:
    """Export measurement traces to a simple tabular CSV file."""

    def __init__(self, freq_unit: str = "MHz") -> None:
        """Initialize the exporter with the desired frequency unit."""
        self.freq_unit = freq_unit

    def _convert_frequency(self, freq_hz: float) -> float:
        """Convert one frequency value from Hz to the configured unit."""
        factor = _FREQ_UNIT_FACTORS.get(self.freq_unit, _FREQ_UNIT_FACTORS["MHz"])
        return freq_hz / factor

    def _normalize_trace_order(
        self,
        s_parameters: dict[str, tuple[np.ndarray, np.ndarray]],
    ) -> tuple[str, ...]:
        """Return exported trace names in stable UI-friendly order."""
        ordered = [name for name in _TRACE_ORDER if name in s_parameters]
        extras = sorted(name for name in s_parameters if name not in _TRACE_ORDER)
        trace_names = tuple(ordered + extras)
        if not trace_names:
            raise ValueError("No valid S-parameters provided for CSV export")
        return trace_names

    def _validate_inputs(
        self,
        frequencies_hz: np.ndarray,
        s_parameters: dict[str, tuple[np.ndarray, np.ndarray]],
        trace_names: tuple[str, ...],
    ) -> None:
        """Validate array lengths before writing the CSV file."""
        if len(frequencies_hz) == 0:
            raise ValueError("No frequency points provided for CSV export")

        for trace_name in trace_names:
            magnitude_db, phase_deg = s_parameters[trace_name]
            if len(magnitude_db) != len(frequencies_hz):
                raise ValueError(
                    f"Trace {trace_name} magnitude length mismatch with frequencies"
                )
            if len(phase_deg) != len(frequencies_hz):
                raise ValueError(
                    f"Trace {trace_name} phase length mismatch with frequencies"
                )

    def _build_header(self, trace_names: tuple[str, ...]) -> list[str]:
        """Build the CSV header row for the selected traces."""
        header = [f"frequency_{self.freq_unit.lower()}"]
        for trace_name in trace_names:
            header.append(f"{trace_name}_magnitude_db")
            header.append(f"{trace_name}_phase_deg")
        return header

    def _resolve_output_path(
        self,
        output_path: str,
        filename: str | None,
        prefix: str,
    ) -> Path:
        """Resolve and create the destination path for the CSV export."""
        output_dir = Path(output_path)
        output_dir.mkdir(parents=True, exist_ok=True)

        resolved_name = filename
        if resolved_name is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            resolved_name = f"{prefix}_{timestamp}"

        if not resolved_name.lower().endswith(".csv"):
            resolved_name += ".csv"

        return output_dir / resolved_name

    def export(
        self,
        frequencies_hz: np.ndarray,
        s_parameters: dict[str, tuple[np.ndarray, np.ndarray]],
        output_path: str,
        filename: str | None = None,
        prefix: str = "measurement",
    ) -> str:
        """Export measurement traces to CSV and return the created file path."""
        trace_names = self._normalize_trace_order(s_parameters)
        self._validate_inputs(frequencies_hz, s_parameters, trace_names)
        destination = self._resolve_output_path(output_path, filename, prefix)

        with destination.open("w", encoding="utf-8", newline="") as csv_file:
            writer = csv.writer(csv_file)
            writer.writerow(self._build_header(trace_names))

            for index, freq_hz in enumerate(frequencies_hz):
                row = [f"{self._convert_frequency(float(freq_hz)):.6f}"]
                for trace_name in trace_names:
                    magnitude_db, phase_deg = s_parameters[trace_name]
                    row.append(f"{float(magnitude_db[index]):.6f}")
                    row.append(f"{float(phase_deg[index]):.6f}")
                writer.writerow(row)

        return str(destination)

    def export_with_result(
        self,
        frequencies_hz: np.ndarray,
        s_parameters: dict[str, tuple[np.ndarray, np.ndarray]],
        output_path: str,
        filename: str | None = None,
        prefix: str = "measurement",
    ) -> CsvExportResult:
        """Export measurement traces to CSV and return structured result metadata."""
        trace_names = self._normalize_trace_order(s_parameters)
        path = self.export(
            frequencies_hz,
            s_parameters,
            output_path,
            filename=filename,
            prefix=prefix,
        )
        return CsvExportResult(
            path=path,
            trace_names=trace_names,
            row_count=len(frequencies_hz),
        )
