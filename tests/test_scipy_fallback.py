"""Tests for SciPy-unavailable smoothing fallback in tools_logic."""

from __future__ import annotations

from unittest.mock import patch

import numpy as np
import pytest

from tina.gui.tabs.tools_logic import _detect_candidates_with_smoothing


def _sample_waveform() -> tuple[np.ndarray, np.ndarray]:
    """Create a smooth waveform with clear extrema for candidate detection."""
    freqs = np.linspace(0.0, 10.0, 101)
    data = np.sin(freqs)
    return freqs, data


class TestScipyFallback:
    @pytest.mark.unit
    def test_detect_candidates_with_smoothing_falls_back_to_numpy_when_scipy_missing(
        self,
    ):
        freqs, data = _sample_waveform()

        with patch.dict("sys.modules", {"scipy.signal": None}):
            with patch(
                "tina.gui.tabs.tools_logic.np.convolve", wraps=np.convolve
            ) as convolve_mock:
                peaks = _detect_candidates_with_smoothing(
                    data,
                    freqs,
                    minima=False,
                    smoothing=True,
                )

        assert convolve_mock.called
        assert isinstance(peaks, np.ndarray)
        assert np.issubdtype(peaks.dtype, np.integer)
        assert peaks.size > 0
        assert np.all((0 <= peaks) & (peaks < data.size))
        assert np.max(data[peaks]) > 0.9

    @pytest.mark.unit
    def test_detect_candidates_with_smoothing_returns_meaningful_minima_without_scipy(
        self,
    ):
        freqs, data = _sample_waveform()

        with patch.dict("sys.modules", {"scipy.signal": None}):
            minima = _detect_candidates_with_smoothing(
                data,
                freqs,
                minima=True,
                smoothing=True,
            )

        assert isinstance(minima, np.ndarray)
        assert np.issubdtype(minima.dtype, np.integer)
        assert minima.size > 0
        assert np.all((0 <= minima) & (minima < data.size))
        assert np.min(data[minima]) < -0.9
