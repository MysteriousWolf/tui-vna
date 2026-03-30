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
    """
    Compute a plotting range that ignores extreme low/high outliers and adds a safety margin.
    
    Filters the input data by removing the lowest and highest `outlier_percentile` percentiles, uses those percentile values as the core min/max, and expands the range by `safety_margin` fraction of the filtered span. If `data` is empty, returns (0.0, 1.0). If the filtered span is zero, a nonzero span is derived from `min_val` (10% of |min_val|) or set to 1.0 when `min_val` is zero.
    
    Parameters:
        data (np.ndarray): Values to compute the plot range from.
        outlier_percentile (float): Percentage removed from each tail when computing percentiles (e.g., 1.0 ignores the bottom and top 1%).
        safety_margin (float): Fraction of the filtered span to add to both ends of the range (e.g., 0.05 adds 5%).
    
    Returns:
        tuple[float, float]: (min_value, max_value) expanded by the safety margin.
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
    """
    Convert a 3- or 6-digit hexadecimal color string (optionally prefixed with '#') into an (R, G, B) integer tuple.
    
    Parameters:
        hex_color (str): Hex color in either "RRGGBB" or shorthand "RGB" form, with or without a leading '#'.
    
    Returns:
        tuple[int, int, int]: `(R, G, B)` where each component is an integer in the range 0–255.
    """
    h = hex_color.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
