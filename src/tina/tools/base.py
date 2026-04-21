"""Abstract base for tina measurement tools."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

import numpy as np


@dataclass
class ToolResult:
    """Output produced by any tool computation."""

    tool_name: str
    cursor1_freq_hz: float | None = None
    cursor2_freq_hz: float | None = None
    cursor1_value: float | None = None
    cursor2_value: float | None = None
    delta_value: float | None = None
    unit_label: str = "dB"
    extra: dict = field(default_factory=dict)


class BaseTool(ABC):
    """Abstract base for all measurement tools."""

    @abstractmethod
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
        Compute the tool's measurement result for the provided frequency sweep.

        Compute the measurement output for the given frequencies and S-parameter
        data using the specified trace and plot type. The `sparams` mapping
        should provide tuples or arrays of (magnitude in dB, phase in degrees)
        keyed by S-parameter name (e.g., "S11").

        `plot_type` accepts "magnitude", "phase", or "phase_raw". If
        `cursor1_hz` and `cursor2_hz` are provided they are used to populate
        the corresponding cursor fields in the returned ToolResult.

        Parameters:
            freqs (np.ndarray): Frequency array in Hz.
            sparams (dict): Mapping from S-parameter name to (mag_db, phase_deg).
            trace (str): S-parameter identifier to evaluate (e.g., "S11").
            plot_type (str): One of "magnitude", "phase", or "phase_raw".
            cursor1_hz (float | None): Cursor-1 frequency in Hz, or None if unset.
            cursor2_hz (float | None): Cursor-2 frequency in Hz, or None if unset.

        Returns:
            ToolResult: Result containing computed cursor values, delta (if
                applicable), unit label, and any extra metadata.
        """
