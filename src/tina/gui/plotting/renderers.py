"""Plot rendering helpers for the TINA GUI."""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import skrf as rf
from matplotlib import rc_context

from tina.utils.plotting import (
    create_matplotlib_plot,
    get_plot_colors,
    get_terminal_font,
)

__all__ = [
    "create_matplotlib_plot",
    "create_smith_chart",
    "get_terminal_font",
]


def create_smith_chart(
    freqs: np.ndarray,
    sparams: dict,
    plot_params: list,
    output_path: Path,
    dpi: int = 150,
    pixel_width: int | None = None,
    pixel_height: int | None = None,
    transparent: bool = False,
    render_scale: int = 1,
    colors: dict | None = None,
    font_family: str | None = None,
    font_size: float | None = None,
) -> None:
    """Create a Smith chart using scikit-rf with dark theme matching terminal UI."""
    if font_family is None or font_size is None:
        detected_family, detected_size = get_terminal_font()
        font_family = font_family or detected_family
        font_size = font_size or detected_size

    if colors is None:
        colors = get_plot_colors()
    fg_color = colors["fg"]
    grid_color = colors["grid"]

    if (pixel_width is None) != (pixel_height is None):
        raise ValueError("pixel_width and pixel_height must both be provided or both omitted")
    if pixel_width is not None and pixel_height is not None:
        square_size_px = min(pixel_width, pixel_height)
        fig_width = square_size_px / dpi
        fig_height = square_size_px / dpi
    else:
        fig_width = 10
        fig_height = 10

    if len(freqs) == 0:
        raise ValueError("Empty sweep data")
    for param in plot_params:
        mag_db, phase_deg = sparams[param]
        if len(mag_db) != len(freqs) or len(phase_deg) != len(freqs):
            raise ValueError(
                f"Mismatched sweep array lengths for {param}: "
                f"freqs={len(freqs)}, mag_db={len(mag_db)}, phase_deg={len(phase_deg)}"
            )

    with rc_context({"font.family": font_family}):
        base_size = (font_size if font_size else 10.0) / render_scale

        fig, ax = plt.subplots(figsize=(fig_width, fig_height))
        fig.patch.set_alpha(0.0 if transparent else 1.0)
        if not transparent:
            fig.patch.set_facecolor(colors["bg"])
        ax.set_facecolor("none" if transparent else colors["bg"])
        ax.set_aspect("equal")

        freq_start_mhz = freqs[0] / 1e6
        freq_end_mhz = freqs[-1] / 1e6
        label_box_style = {
            "boxstyle": "round,pad=0.3",
            "facecolor": colors["bg"],
            "alpha": 0.8,
        }

        rf.plotting.smith(
            ax=ax,
            chart_type="z",
            draw_labels=True,
            ref_imm=50.0,
            draw_vswr=None,
        )

        # Capture grid artists before adding any user markers/annotations so the
        # post-styling loops below only restyle the Smith-chart grid, not traces.
        grid_collections = list(ax.collections)
        grid_texts = list(ax.texts)

        ax.scatter(
            [1.0],
            [0.0],
            marker="o",
            s=50,
            color=grid_color,
            edgecolor=fg_color,
            linewidth=1.5,
            zorder=10,
            label="Open",
        )
        ax.scatter(
            [-1.0],
            [0.0],
            marker="s",
            s=50,
            color=grid_color,
            edgecolor=fg_color,
            linewidth=1.5,
            zorder=10,
            label="Short",
        )
        ax.scatter(
            [0.0],
            [0.0],
            marker="*",
            s=100,
            color=colors.get("warning", fg_color),
            edgecolor=fg_color,
            linewidth=1.5,
            zorder=10,
            label="Match (50Ω)",
        )

        for param in plot_params:
            mag_db = sparams[param][0]
            phase_deg = sparams[param][1]

            mag_linear = 10 ** (mag_db / 20)
            phase_rad = np.deg2rad(phase_deg)
            s_complex = mag_linear * np.exp(1j * phase_rad)

            network = rf.Network(
                frequency=rf.Frequency.from_f(freqs, unit="Hz"),
                s=s_complex.reshape(-1, 1, 1),
                name=param,
            )

            trace_color = colors["traces"].get(param, colors["default_trace"])
            network.plot_s_smith(
                m=0,
                n=0,
                ax=ax,
                label=param,
                color=trace_color,
                linewidth=1.5,
                draw_labels=False,
                show_legend=False,
            )

            ax.scatter(
                s_complex[0].real,
                s_complex[0].imag,
                marker=">",
                s=80,
                color=trace_color,
                edgecolor=fg_color,
                linewidth=1,
                zorder=15,
            )
            ax.scatter(
                s_complex[-1].real,
                s_complex[-1].imag,
                marker="s",
                s=60,
                color=trace_color,
                edgecolor=fg_color,
                linewidth=1,
                zorder=15,
            )

            ax.annotate(
                f"{freq_start_mhz:.0f} MHz",
                (s_complex[0].real, s_complex[0].imag),
                xytext=(10, 10),
                textcoords="offset points",
                color=trace_color,
                fontsize=base_size * 0.7,
                bbox={**label_box_style, "edgecolor": trace_color},
            )
            ax.annotate(
                f"{freq_end_mhz:.0f} MHz",
                (s_complex[-1].real, s_complex[-1].imag),
                xytext=(-10, -10),
                textcoords="offset points",
                color=trace_color,
                fontsize=base_size * 0.7,
                bbox={**label_box_style, "edgecolor": trace_color},
            )

        ax.set_title("Smith Chart", color=fg_color, fontsize=base_size * 1.2, pad=15)

        for collection in grid_collections:
            collection.set_edgecolor(grid_color)
            collection.set_alpha(0.3)

        for text in grid_texts:
            text.set_color(fg_color)
            text.set_fontsize(base_size * 0.7)

        if len(plot_params) > 0:
            legend = ax.legend(
                edgecolor=grid_color,
                labelcolor=fg_color,
                fontsize=base_size * 0.9,
                loc="upper right",
            )
            legend.get_frame().set_alpha(0.5 if transparent else 1.0)
            if not transparent:
                legend.get_frame().set_facecolor(colors["bg"])
            else:
                legend.get_frame().set_facecolor("none")

        plt.tight_layout()
        plt.savefig(
            output_path,
            dpi=dpi,
            facecolor=fig.get_facecolor(),
            edgecolor="none",
            bbox_inches="tight",
            transparent=transparent,
        )
        plt.close(fig)
