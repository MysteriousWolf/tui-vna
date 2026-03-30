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
        """
        Compute interpolated trace values at up to two cursor frequencies and the difference between them.

        Interpolates the selected trace data at `cursor1_hz` and `cursor2_hz` (when provided and within the range of `freqs`) and returns those values and their difference. If `trace` is not present in `sparams`, returns a ToolResult containing only `tool_name="measure"` and `unit_label`. Cursors outside the frequency range or set to `None` produce `None` for the corresponding value.

        Parameters:
            freqs (np.ndarray): 1D array of frequency points used for interpolation; first and last elements define the valid interpolation range.
            sparams (dict): Mapping from trace name to a tuple `(mag, phase)` where `mag` and `phase` are arrays aligned with `freqs`.
            trace (str): Key selecting which entry from `sparams` to use.
            plot_type (str): Selects which data to interpolate: `"magnitude"` uses `mag`, `"phase"` uses unwrapped `phase`, any other value uses raw `phase`.
            cursor1_hz (float | None): Frequency for cursor 1; when `None` or outside `freqs` range, cursor1 value is `None`.
            cursor2_hz (float | None): Frequency for cursor 2; when `None` or outside `freqs` range, cursor2 value is `None`.

        Returns:
            ToolResult: Contains `tool_name="measure"`, `unit_label` (`"dB"` for magnitude, otherwise `"°"`), `cursor1_freq_hz`, `cursor2_freq_hz`, `cursor1_value`, `cursor2_value`, and `delta_value` (`cursor2 - cursor1` or `None` if either value is `None`).
        """
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
            """
            Interpolate the selected data at the specified frequency.

            Parameters:
                freq_hz (float): Frequency in hertz at which to interpolate.

            Returns:
                interpolated_value (float): Value obtained by linear interpolation of the surrounding `freqs` and `data` arrays at `freq_hz`.
            """
            return float(np.interp(freq_hz, freqs, data))

        freq_min, freq_max = freqs[0], freqs[-1]
        v1 = (
            _interp(cursor1_hz)
            if cursor1_hz is not None and freq_min <= cursor1_hz <= freq_max
            else None
        )
        v2 = (
            _interp(cursor2_hz)
            if cursor2_hz is not None and freq_min <= cursor2_hz <= freq_max
            else None
        )
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
