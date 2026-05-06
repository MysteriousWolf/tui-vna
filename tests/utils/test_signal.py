"""Tests for pure signal helpers."""

from __future__ import annotations

import numpy as np

from src.tina.utils.signal import calculate_plot_range_with_outlier_filtering


def test_calculate_plot_range_clamps_invalid_percentile_and_margin() -> None:
    """Invalid inputs should be clamped before percentile calculations run."""
    data = np.array([1.0, 2.0, 3.0, 100.0])

    result = calculate_plot_range_with_outlier_filtering(
        data, outlier_percentile=120.0, safety_margin=-5.0
    )

    assert result == (2.5, 2.5)


def test_calculate_plot_range_handles_non_finite_inputs() -> None:
    """Non-finite inputs fall back to defaults instead of crashing."""
    data = np.array([10.0, 20.0, 30.0])

    result = calculate_plot_range_with_outlier_filtering(
        data, outlier_percentile=np.nan, safety_margin=np.inf
    )

    assert all(np.isfinite(value) for value in result)
    assert result[0] < result[1]
