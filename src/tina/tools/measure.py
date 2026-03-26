"""Cursor/Measure tool — reads trace value at two cursor frequencies."""

from __future__ import annotations

import numpy as np

from ..utils.signal import unwrap_phase
from .base import BaseTool, ToolResult


class MeasureTool(BaseTool):
    """Read off the trace value at each cursor frequency and compute the difference."""

    def compute(
        self,
        freqs: np.ndarray,
        sparams: dict,
        trace: str,
        plot_type: str,
        cursor1_hz: float | None,
        cursor2_hz: float | None,
    ) -> ToolResult:
        unit_label = "dB" if plot_type == "magnitude" else "°"

        if trace not in sparams:
            return ToolResult(tool_name="measure", unit_label=unit_label)

        mag, phase = sparams[trace]
        if plot_type == "magnitude":
            data = mag
        elif plot_type == "phase":
            data = unwrap_phase(phase)
        else:
            data = phase

        def _interp(freq_hz: float) -> float:
            return float(np.interp(freq_hz, freqs, data))

        v1 = _interp(cursor1_hz) if cursor1_hz is not None else None
        v2 = _interp(cursor2_hz) if cursor2_hz is not None else None
        delta = (v2 - v1) if (v1 is not None and v2 is not None) else None

        return ToolResult(
            tool_name="measure",
            cursor1_freq_hz=cursor1_hz,
            cursor2_freq_hz=cursor2_hz,
            cursor1_value=v1,
            cursor2_value=v2,
            delta_value=delta,
            unit_label=unit_label,
        )
