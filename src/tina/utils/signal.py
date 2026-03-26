"""Pure signal-processing helpers shared across tina."""

import numpy as np


def unwrap_phase(phase_deg: np.ndarray) -> np.ndarray:
    """Unwrap phase data to remove discontinuities.

    Converts phase from [-180, 180] range to continuous values by removing
    360-degree jumps.

    Args:
        phase_deg: Phase data in degrees

    Returns:
        Unwrapped phase in degrees
    """
    phase_rad = np.deg2rad(phase_deg)
    unwrapped_rad = np.unwrap(phase_rad)
    return np.rad2deg(unwrapped_rad)


def calculate_plot_range_with_outlier_filtering(
    data: np.ndarray, outlier_percentile: float = 1.0, safety_margin: float = 0.05
) -> tuple[float, float]:
    """Calculate plot range while filtering out outliers.

    This prevents extreme outliers from compressing the useful data range.

    Args:
        data: Array of values to analyze
        outlier_percentile: Percentage of outliers to ignore on each end (default 1%)
        safety_margin: Additional margin beyond filtered range (default 5%)

    Returns:
        Tuple of (min_value, max_value) for plot range
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


def hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    """Convert a hex color string to an (R, G, B) tuple."""
    h = hex_color.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
