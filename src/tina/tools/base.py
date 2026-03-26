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
        """Run the tool and return a ToolResult.

        Args:
            freqs:      Frequency array in Hz.
            sparams:    {param: (mag_db, phase_deg)} dict.
            trace:      S-parameter name, e.g. "S11".
            plot_type:  "magnitude" | "phase" | "phase_raw".
            cursor1_hz: Cursor-1 frequency in Hz (None = not set).
            cursor2_hz: Cursor-2 frequency in Hz (None = not set).
        """
