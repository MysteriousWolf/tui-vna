"""CLI plotting utilities for tina."""

import os
from pathlib import Path

import numpy as np

from ..config.settings import AppSettings

# Import plotting functions from main module (will be refactored to gui.plotting later)
from ..main import _create_matplotlib_plot, _get_plot_colors


def export_plots_cli(
    frequencies: np.ndarray,
    s_parameters: dict[str, tuple[np.ndarray, np.ndarray]],
    settings: AppSettings,
    output_path: str,
    base_filename: str,
) -> None:
    """Generate and export plots in CLI mode using same scaling as GUI."""
    # Create plots for magnitude and phase
    plot_params = []
    if settings.plot_s11 and "S11" in s_parameters:
        plot_params.append("S11")
    if settings.plot_s21 and "S21" in s_parameters:
        plot_params.append("S21")
    if settings.plot_s12 and "S12" in s_parameters:
        plot_params.append("S12")
    if settings.plot_s22 and "S22" in s_parameters:
        plot_params.append("S22")

    if not plot_params:
        print("No S-parameters selected for plotting")
        return

    # Use the same plot settings as GUI for consistency
    # Match the GUI's high-quality rendering parameters
    render_scale = 2
    dpi = 150 * render_scale  # 300 DPI for high quality

    # Get proper themed colors (use fallback colors which are already well-themed)
    plot_colors = _get_plot_colors(None)  # This will use the nice fallback colors

    # Create magnitude plot using the same method as GUI
    plot_filename = f"{base_filename}_magnitude.png"
    plot_path = os.path.join(output_path, plot_filename)

    # Use the same matplotlib plotting function as the GUI
    _create_matplotlib_plot(
        frequencies,
        s_parameters,
        plot_params,
        plot_type="magnitude",
        output_path=Path(plot_path),
        dpi=dpi,
        pixel_width=1920,
        pixel_height=1080,
        transparent=False,
        render_scale=render_scale,
        colors=plot_colors,
        y_min=None,  # Auto-detect with outlier filtering
        y_max=None,  # Auto-detect with outlier filtering
    )
    print(f"Magnitude plot saved: {plot_path}")

    # Create phase plot using the same method as GUI
    phase_plot_filename = f"{base_filename}_phase.png"
    phase_plot_path = os.path.join(output_path, phase_plot_filename)

    _create_matplotlib_plot(
        frequencies,
        s_parameters,
        plot_params,
        plot_type="phase",  # Unwrapped phase
        output_path=Path(phase_plot_path),
        dpi=dpi,
        pixel_width=1920,
        pixel_height=1080,
        transparent=False,
        render_scale=render_scale,
        colors=plot_colors,
        y_min=None,  # Auto-detect with outlier filtering
        y_max=None,  # Auto-detect with outlier filtering
    )
    print(f"Phase plot saved: {phase_plot_path}")
