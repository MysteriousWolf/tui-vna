"""Utility helpers for GUI plotting and display formatting."""

from __future__ import annotations

from pathlib import Path

import numpy as np


def truncate_path_intelligently(path_str: str, max_width: int) -> str:
    """
    Intelligently truncate a file path to fit within a given width.

    Strategy:
    1. If path fits, return as-is
    2. Progressively drop folders from the left
    3. Try showing only first letter of remaining folders
    4. Try showing only filename
    5. Truncate filename with ellipsis

    Args:
        path_str: The full path string.
        max_width: Maximum character width.

    Returns:
        Truncated path string.
    """
    # Account for the 📁 emoji (2 chars) + space
    effective_width = max_width - 2

    if len(path_str) <= effective_width:
        return path_str

    path = Path(path_str)
    parts = list(path.parts)

    if len(parts) <= 1:
        filename = path.name
        if len(filename) > effective_width and effective_width > 3:
            return filename[: effective_width - 3] + "..."
        return filename[:effective_width]

    for i in range(1, len(parts) - 1):
        truncated = ".../" + "/".join(parts[i:])
        if len(truncated) <= effective_width:
            return truncated

    if len(parts) > 1:
        abbreviated = "/".join(p[0] for p in parts[:-1]) + "/" + parts[-1]
        if len(abbreviated) <= effective_width:
            return abbreviated

        abbreviated_with_ellipsis = (
            ".../"
            + "/".join(p[0] for p in parts[1:-1])
            + ("/" if len(parts) > 2 else "")
            + parts[-1]
        )
        if len(abbreviated_with_ellipsis) <= effective_width:
            return abbreviated_with_ellipsis

    filename = path.name
    if len(filename) <= effective_width:
        return filename

    if effective_width > 3:
        return filename[: effective_width - 3] + "..."
    return filename[:effective_width]


def calculate_plot_range_with_outlier_filtering(
    data: np.ndarray, outlier_percentile: float = 1.0, safety_margin: float = 0.05
) -> tuple[float, float]:
    """
    Calculate plot range while filtering outliers.

    This prevents extreme outliers from compressing the useful data range.

    Args:
        data: Array of values to analyze.
        outlier_percentile: Percentage of outliers to ignore on each end.
        safety_margin: Additional margin beyond filtered range.

    Returns:
        Tuple of (min_value, max_value) for plot range.
    """
    if len(data) == 0:
        return (0.0, 1.0)

    lower_percentile = outlier_percentile
    upper_percentile = 100.0 - outlier_percentile

    min_val = np.percentile(data, lower_percentile)
    max_val = np.percentile(data, upper_percentile)

    data_range = max_val - min_val
    if data_range == 0:
        data_range = abs(min_val) * 0.1 if min_val != 0 else 1.0

    margin = data_range * safety_margin
    min_val -= margin
    max_val += margin

    return (float(min_val), float(max_val))


def unwrap_phase(phase_deg: np.ndarray) -> np.ndarray:
    """
    Unwrap phase data to remove discontinuities.

    Converts phase from [-180, 180] range to continuous values by removing
    360-degree jumps.

    Args:
        phase_deg: Phase data in degrees.

    Returns:
        Unwrapped phase in degrees.
    """
    phase_rad = np.deg2rad(phase_deg)
    unwrapped_rad = np.unwrap(phase_rad)
    return np.rad2deg(unwrapped_rad)
