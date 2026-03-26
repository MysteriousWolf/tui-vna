"""Distortion tool — measures linear distortion between two cursor points."""

from __future__ import annotations

import numpy as np

from ..utils.signal import unwrap_phase
from .base import BaseTool, ToolResult


class DistortionTool(BaseTool):
    """Compute linear distortion as the absolute difference between cursor values."""

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

        if cursor1_hz is None or cursor2_hz is None or trace not in sparams:
            return ToolResult(tool_name="distortion", unit_label=unit_label)

        mag, phase = sparams[trace]
        if plot_type == "magnitude":
            data = mag
        elif plot_type == "phase":
            data = unwrap_phase(phase)
        else:
            data = phase

        v1 = float(np.interp(cursor1_hz, freqs, data))
        v2 = float(np.interp(cursor2_hz, freqs, data))
        linear_distortion = abs(v2 - v1)

        return ToolResult(
            tool_name="distortion",
            cursor1_freq_hz=cursor1_hz,
            cursor2_freq_hz=cursor2_hz,
            cursor1_value=v1,
            cursor2_value=v2,
            delta_value=linear_distortion,
            unit_label=unit_label,
        )
