"""CLI plotting utilities for tina."""

import os
import sys
from pathlib import Path

import numpy as np

from ..config.settings import AppSettings
from ..gui.plotting import create_matplotlib_plot, get_plot_colors


def export_plots_cli(
    frequencies: np.ndarray,
    s_parameters: dict[str, tuple[np.ndarray, np.ndarray]],
    settings: AppSettings,
    output_path: str,
    base_filename: str,
) -> None:
    """Generate and export plots in CLI mode using same scaling as GUI."""
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

    render_scale = 2
    dpi = 150 * render_scale
    plot_colors = get_plot_colors(None)

    def _export_one(plot_type: str, file_path: str) -> None:
        try:
            create_matplotlib_plot(
                frequencies,
                s_parameters,
                plot_params,
                plot_type=plot_type,
                output_path=Path(file_path),
                dpi=dpi,
                pixel_width=1920,
                pixel_height=1080,
                transparent=False,
                render_scale=render_scale,
                colors=plot_colors,
                y_min=None,
                y_max=None,
            )
            print(f"{plot_type.capitalize()} plot saved: {file_path}")
        except Exception as exc:
            print(f"Warning: failed to save {plot_type} plot: {exc}", file=sys.stderr)

    _export_one(
        "magnitude", os.path.join(output_path, f"{base_filename}_magnitude.png")
    )
    _export_one("phase", os.path.join(output_path, f"{base_filename}_phase.png"))
