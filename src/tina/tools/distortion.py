"""Distortion tool — Legendre polynomial decomposition of the in-band response.

Based on:
  Mathiopoulos, Ohnishi & Feher, IEE Proc. I, vol. 136, no. 2, 1989.
  DOI: 10.1049/ip-i-2.1989.0024
"""

from __future__ import annotations

import numpy as np

from ..utils.signal import unwrap_phase
from .base import BaseTool, ToolResult

#: Maximum Legendre order fitted by this tool.
MAX_ORDER: int = 5

#: Human-readable names for each Legendre order, indexed by n.
COMPONENT_NAMES: list[str] = [
    "Constant",
    "Linear",
    "Parabolic",
    "Cubic",
    "Quartic",
    "Quintic",
]

#: Minimum number of in-band data points required for a valid fit.
_MIN_BAND_POINTS: int = MAX_ORDER + 2


def _legendre_pp_range(n: int) -> float:
    """Return the peak-to-peak range of Pₙ(x) over x ∈ [−1, 1].

    Computed numerically on a dense grid so it works for any order without
    needing closed-form expressions.

    Args:
        n: Legendre order (0-based).

    Returns:
        max(Pₙ) − min(Pₙ) over [−1, 1].
    """
    basis = np.zeros(n + 1)
    basis[n] = 1.0
    vals = np.polynomial.legendre.legval(np.linspace(-1.0, 1.0, 2000), basis)
    return float(vals.max() - vals.min())


# Pre-compute peak-to-peak ranges for orders 0..MAX_ORDER once at import time.
_PP_RANGES: list[float] = [_legendre_pp_range(n) for n in range(MAX_ORDER + 1)]


class DistortionTool(BaseTool):
    """Decompose the in-band S-parameter response into Legendre polynomial components.

    The frequency axis between the two cursor points is normalised to x ∈ [−1, 1]
    and then fitted with Legendre polynomials P₀ … P₅ via least-squares.  For
    each order the peak-to-peak distortion contribution Δyₙ = |cₙ| × range(Pₙ)
    is computed and returned in ``extra``.

    ``extra`` keys
    --------------
    coeffs : list[float]
        Legendre coefficients [c₀, c₁, …, c₅].
    delta_y : list[float]
        Peak-to-peak distortion per component [Δy₀, Δy₁, …, Δy₅].
        Δy₀ is always 0 (constant has no peak-to-peak contribution).
    f0_hz : float
        Band centre frequency in Hz.
    bandwidth_hz : float
        Band width in Hz (|cursor2 − cursor1|).
    f_band_hz : list[float]
        Measured frequency points inside the band, in Hz.
    y_band : list[float]
        Trace values at those frequencies (unit depends on ``plot_type``).
    x_norm : list[float]
        Normalised frequencies corresponding to ``f_band_hz``, in [−1, 1].
    """

    def compute(
        self,
        freqs: np.ndarray,
        sparams: dict,
        trace: str,
        plot_type: str,
        cursor1_hz: float | None,
        cursor2_hz: float | None,
    ) -> ToolResult:
        """Fit Legendre polynomials to the in-band response and return distortion metrics.

        Args:
            freqs: Frequency array in Hz.
            sparams: ``{param: (mag_db, phase_deg)}`` dict.
            trace: S-parameter name, e.g. ``"S11"``.
            plot_type: ``"magnitude"`` | ``"phase"`` | ``"phase_raw"``.
            cursor1_hz: Lower (or upper) band edge in Hz.
            cursor2_hz: Upper (or lower) band edge in Hz.

        Returns:
            :class:`~tina.tools.base.ToolResult` with ``extra`` populated on
            success, or an empty result if the inputs are invalid or the band
            contains too few measurement points.
        """
        unit_label = "dB" if plot_type == "magnitude" else "°"

        if cursor1_hz is None or cursor2_hz is None or trace not in sparams:
            return ToolResult(tool_name="distortion", unit_label=unit_label)

        f_lo = min(cursor1_hz, cursor2_hz)
        f_hi = max(cursor1_hz, cursor2_hz)

        mag, phase = sparams[trace]
        if plot_type == "magnitude":
            data = mag
        elif plot_type == "phase":
            data = unwrap_phase(phase)
        else:
            data = phase

        # Extract in-band data points
        mask = (freqs >= f_lo) & (freqs <= f_hi)
        if mask.sum() < _MIN_BAND_POINTS:
            return ToolResult(tool_name="distortion", unit_label=unit_label)

        f_band = freqs[mask]
        y_band = data[mask]

        # Normalise frequency axis to [−1, 1]
        f0 = (f_lo + f_hi) / 2.0
        half_bw = (f_hi - f_lo) / 2.0
        x_norm = (f_band - f0) / half_bw

        # Legendre least-squares fit
        coeffs = np.polynomial.legendre.legfit(x_norm, y_band, MAX_ORDER)

        # Peak-to-peak distortion per component: Δyₙ = |cₙ| × range(Pₙ)
        delta_y = [abs(float(coeffs[n])) * _PP_RANGES[n] for n in range(MAX_ORDER + 1)]
        delta_y[0] = 0.0  # constant has no peak-to-peak contribution

        return ToolResult(
            tool_name="distortion",
            cursor1_freq_hz=cursor1_hz,
            cursor2_freq_hz=cursor2_hz,
            unit_label=unit_label,
            extra={
                "coeffs": [float(c) for c in coeffs],
                "delta_y": delta_y,
                "f0_hz": float(f0),
                "bandwidth_hz": float(f_hi - f_lo),
                "f_band_hz": f_band.tolist(),
                "y_band": y_band.tolist(),
                "x_norm": x_norm.tolist(),
            },
        )
