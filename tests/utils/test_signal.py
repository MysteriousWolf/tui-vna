"""Tests for pure signal helpers."""

from __future__ import annotations

import numpy as np
import pytest

from tina.utils.signal import calculate_plot_range_with_outlier_filtering


def test_calculate_plot_range_handles_non_finite_inputs() -> None:
    """Non-finite inputs fall back to defaults instead of crashing."""
    data = np.array([10.0, 20.0, 30.0])

    result = calculate_plot_range_with_outlier_filtering(
        data, outlier_percentile=np.nan, safety_margin=np.inf
    )

    assert all(np.isfinite(value) for value in result)
    assert result[0] < result[1]


def test_calculate_plot_range_handles_nan_data() -> None:
    """NaN values in data should be ignored and return a valid range."""
    data = np.array([10.0, np.nan, 30.0])

    result = calculate_plot_range_with_outlier_filtering(data)

    assert all(np.isfinite(value) for value in result)
    assert result[0] < result[1]


@pytest.mark.parametrize("percentile", [-1.0, 50.0, 75.0])
def test_calculate_plot_range_rejects_out_of_range_percentiles(
    percentile: float,
) -> None:
    """Outlier percentiles outside [0, 50) should raise ValueError."""
    data = np.array([1.0, 2.0, 3.0, 100.0])

    with pytest.raises(ValueError, match="outlier_percentile"):
        calculate_plot_range_with_outlier_filtering(
            data, outlier_percentile=percentile, safety_margin=0.1
        )


def test_calculate_plot_range_ignores_mixed_non_finite_samples() -> None:
    """Finite samples should drive the range even when NaN and infinities are present."""
    data = np.array([10.0, np.nan, np.inf, -np.inf, 30.0])

    result = calculate_plot_range_with_outlier_filtering(data, outlier_percentile=0.0)

    assert result == (9.0, 31.0)


def test_calculate_plot_range_all_non_finite_uses_fallback() -> None:
    """All-non-finite data should use the default fallback range."""
    data = np.array([np.nan, np.inf, -np.inf])

    result = calculate_plot_range_with_outlier_filtering(data)

    assert result == (0.0, 1.0)


def test_calculate_plot_range_empty_data_uses_fallback() -> None:
    """Empty data array should return the documented fallback range."""
    data = np.array([], dtype=float)

    result = calculate_plot_range_with_outlier_filtering(data)

    assert result == (0.0, 1.0)
