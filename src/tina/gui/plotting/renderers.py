"""Plot rendering helpers for the TINA GUI."""

from __future__ import annotations

import os
import platform
import re
import subprocess
from pathlib import Path

import matplotlib.font_manager as fm
import matplotlib.pyplot as plt
import numpy as np
import skrf as rf

from .colors import get_plot_colors
from .utils import calculate_plot_range_with_outlier_filtering, unwrap_phase


def get_terminal_font() -> tuple[str, float | None]:
    """Detect the terminal's font family and size by parsing its config file.

    Uses TERM_PROGRAM to identify the terminal emulator, then reads its
    configuration file to extract the font family and size.
    Falls back to ('monospace', None).

    Supported terminals: Ghostty, Kitty, Alacritty, WezTerm, iTerm2,
    Windows Terminal.
    """
    import json

    available_fonts = {f.name for f in fm.fontManager.ttflist}
    term = os.environ.get("TERM_PROGRAM", "").lower()
    home = Path.home()
    font_name = None
    font_size = None

    def _parse_ghostty_config() -> None:
        """Read font-family and font-size from the Ghostty config file if present."""
        nonlocal font_name, font_size
        cfg = home / ".config" / "ghostty" / "config"
        if cfg.exists():
            for line in cfg.read_text().splitlines():
                line = line.strip()
                if line.startswith("#"):
                    continue
                if line.startswith("font-family") and not font_name:
                    font_name = line.split("=", 1)[1].strip().strip("\"'")
                elif line.startswith("font-size") and not font_size:
                    try:
                        font_size = float(line.split("=", 1)[1].strip().strip("\"'"))
                    except ValueError:
                        pass
            if not font_size:
                font_size = 13.0

    try:
        if "ghostty" in term:
            _parse_ghostty_config()

        elif "kitty" in term:
            cfg = home / ".config" / "kitty" / "kitty.conf"
            if cfg.exists():
                for line in cfg.read_text().splitlines():
                    line = line.strip()
                    if line.startswith("font_family") and not font_name:
                        font_name = line.split(None, 1)[1].strip().strip("\"'")
                    elif line.startswith("font_size") and not font_size:
                        try:
                            font_size = float(line.split(None, 1)[1].strip())
                        except (ValueError, IndexError):
                            pass

        elif "alacritty" in term:
            for name in ("alacritty.toml", "alacritty.yml"):
                cfg = home / ".config" / "alacritty" / name
                if cfg.exists():
                    text = cfg.read_text()
                    if name.endswith(".toml"):
                        m = re.search(
                            r'\[font\.normal\]\s*\n\s*family\s*=\s*["\']([^"\']+)',
                            text,
                        )
                        if m:
                            font_name = m.group(1)
                        m = re.search(
                            r"\[font\]\s*\n(?:.*\n)*?\s*size\s*=\s*([\d.]+)", text
                        )
                        if m:
                            font_size = float(m.group(1))
                    else:
                        m = re.search(
                            r'font:\s*\n\s*normal:\s*\n\s*family:\s*["\']?([^\n"\']+)',
                            text,
                        )
                        if m:
                            font_name = m.group(1).strip()
                        m = re.search(r"font:\s*\n(?:.*\n)*?\s*size:\s*([\d.]+)", text)
                        if m:
                            font_size = float(m.group(1))
                    if font_name:
                        break

        elif "wezterm" in term:
            for cfg in (
                home / ".config" / "wezterm" / "wezterm.lua",
                home / ".wezterm.lua",
            ):
                if cfg.exists():
                    text = cfg.read_text()
                    m = re.search(
                        r'font\s*=\s*wezterm\.font\s*\(\s*["\']([^"\']+)', text
                    )
                    if m:
                        font_name = m.group(1)
                    m = re.search(r"font_size\s*=\s*([\d.]+)", text)
                    if m:
                        font_size = float(m.group(1))
                    if font_name:
                        break

        elif "iterm" in term:
            if platform.system() == "Darwin":
                result = subprocess.run(
                    ["defaults", "read", "com.googlecode.iterm2", "Normal Font"],
                    capture_output=True,
                    text=True,
                    timeout=2,
                )
                if result.returncode == 0:
                    raw = result.stdout.strip()
                    parts = raw.rsplit(" ", 1)
                    font_name = parts[0].replace("-Regular", "")
                    if len(parts) == 2:
                        try:
                            font_size = float(parts[1])
                        except ValueError:
                            pass

        elif platform.system() == "Windows":
            local_app = os.environ.get("LOCALAPPDATA", "")
            if local_app:
                wt_dir = Path(local_app) / "Packages"
                if wt_dir.exists():
                    for pkg in wt_dir.iterdir():
                        if "WindowsTerminal" in pkg.name:
                            settings = pkg / "LocalState" / "settings.json"
                            if settings.exists():
                                data = json.loads(settings.read_text())
                                profiles = data.get("profiles", {})
                                defaults = profiles.get("defaults", {})
                                font_cfg = defaults.get("font", {})
                                face = font_cfg.get("face")
                                if face:
                                    font_name = face
                                size = font_cfg.get("size")
                                if size:
                                    font_size = float(size)
                                break

        if not font_name:
            _parse_ghostty_config()

    except Exception:
        pass

    resolved_name = "monospace"
    if font_name:
        if font_name in available_fonts:
            resolved_name = font_name
        else:
            lower_name = font_name.lower()
            for available_font in available_fonts:
                if available_font.lower() == lower_name:
                    resolved_name = available_font
                    break
            else:
                candidates = [
                    available_font
                    for available_font in available_fonts
                    if lower_name in available_font.lower()
                    or available_font.lower() in lower_name
                ]
                if candidates:
                    resolved_name = min(candidates, key=len)

    return resolved_name, font_size


def create_matplotlib_plot(
    freqs: np.ndarray,
    sparams: dict,
    plot_params: list,
    plot_type: str,
    output_path: Path,
    dpi: int = 150,
    pixel_width: int | None = None,
    pixel_height: int | None = None,
    transparent: bool = False,
    render_scale: int = 1,
    colors: dict | None = None,
    y_min: float | None = None,
    y_max: float | None = None,
    font_family: str = "monospace",
    font_size: float | None = None,
) -> None:
    """Create a plot using matplotlib with dark theme matching terminal UI."""
    font_family, font_size = get_terminal_font()
    plt.rcParams["font.family"] = font_family
    base_size = (font_size if font_size else 10.0) / render_scale

    if colors is None:
        colors = get_plot_colors()
    fg_color = colors["fg"]
    grid_color = colors["grid"]

    if pixel_width and pixel_height:
        fig_width = pixel_width / dpi
        fig_height = pixel_height / dpi
    else:
        fig_width = 10
        fig_height = 5

    fig, ax = plt.subplots(figsize=(fig_width, fig_height))
    fig.patch.set_alpha(0.0 if transparent else 1.0)
    if not transparent:
        fig.patch.set_facecolor(colors["bg"])
    ax.set_facecolor("none" if transparent else colors["bg"])

    freq_mhz = freqs / 1e6

    all_y_data = []
    for param in plot_params:
        if plot_type == "magnitude":
            data = sparams[param][0]
            ylabel = "Magnitude (dB)"
            title = "S-Parameter Magnitude"
        elif plot_type == "phase":
            data = unwrap_phase(sparams[param][1])
            ylabel = "Phase (degrees)"
            title = "S-Parameter Phase (Unwrapped)"
        else:
            data = sparams[param][1]
            ylabel = "Phase (degrees)"
            title = "S-Parameter Phase (Raw)"

        all_y_data.append(data)
        ax.plot(
            freq_mhz,
            data,
            label=param,
            color=colors["traces"].get(param, colors["default_trace"]),
            linewidth=1.5,
        )

    if all_y_data:
        combined_data = np.concatenate(all_y_data)
        if y_min is None or y_max is None:
            auto_y_min, auto_y_max = calculate_plot_range_with_outlier_filtering(
                combined_data, outlier_percentile=1.0, safety_margin=0.05
            )
            final_y_min = y_min if y_min is not None else auto_y_min
            final_y_max = y_max if y_max is not None else auto_y_max
        else:
            final_y_min = y_min
            final_y_max = y_max
        ax.set_ylim(final_y_min, final_y_max)

    ax.set_xlabel("Frequency (MHz)", color=fg_color, fontsize=base_size)
    ax.set_ylabel(ylabel, color=fg_color, fontsize=base_size)
    ax.set_title(title, color=fg_color, fontsize=base_size * 1.2, pad=15)
    ax.tick_params(colors=fg_color, labelsize=base_size * 0.85)
    ax.grid(True, alpha=0.2, color=grid_color, linestyle="-", linewidth=0.5)
    legend = ax.legend(
        edgecolor=grid_color,
        labelcolor=fg_color,
        fontsize=base_size * 0.9,
    )
    legend.get_frame().set_alpha(0.5 if transparent else 1.0)
    if not transparent:
        legend.get_frame().set_facecolor(colors["bg"])
    else:
        legend.get_frame().set_facecolor("none")

    for spine in ax.spines.values():
        spine.set_edgecolor(grid_color)
        spine.set_linewidth(1)

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
) -> None:
    """Create a Smith chart using scikit-rf with dark theme matching terminal UI."""
    font_family, font_size = get_terminal_font()
    plt.rcParams["font.family"] = font_family
    base_size = (font_size if font_size else 10.0) / render_scale

    if colors is None:
        colors = get_plot_colors()
    fg_color = colors["fg"]
    grid_color = colors["grid"]

    if pixel_width and pixel_height:
        square_size_px = min(pixel_width, pixel_height)
        fig_width = square_size_px / dpi
        fig_height = square_size_px / dpi
    else:
        fig_width = 10
        fig_height = 10

    fig, ax = plt.subplots(figsize=(fig_width, fig_height))
    fig.patch.set_alpha(0.0 if transparent else 1.0)
    if not transparent:
        fig.patch.set_facecolor(colors["bg"])
    ax.set_facecolor("none" if transparent else colors["bg"])
    ax.set_aspect("equal")

    rf.plotting.smith(
        ax=ax,
        chart_type="z",
        draw_labels=True,
        ref_imm=50.0,
        draw_vswr=None,
    )

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
        color="gold",
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

        freq_start_mhz = freqs[0] / 1e6
        freq_end_mhz = freqs[-1] / 1e6
        ax.annotate(
            f"{freq_start_mhz:.0f} MHz",
            (s_complex[0].real, s_complex[0].imag),
            xytext=(10, 10),
            textcoords="offset points",
            color=trace_color,
            fontsize=base_size * 0.7,
            bbox=dict(
                boxstyle="round,pad=0.3",
                facecolor=colors["bg"],
                edgecolor=trace_color,
                alpha=0.8,
            ),
        )
        ax.annotate(
            f"{freq_end_mhz:.0f} MHz",
            (s_complex[-1].real, s_complex[-1].imag),
            xytext=(-10, -10),
            textcoords="offset points",
            color=trace_color,
            fontsize=base_size * 0.7,
            bbox=dict(
                boxstyle="round,pad=0.3",
                facecolor=colors["bg"],
                edgecolor=trace_color,
                alpha=0.8,
            ),
        )

    ax.set_title("Smith Chart", color=fg_color, fontsize=base_size * 1.2, pad=15)

    for collection in ax.collections:
        collection.set_edgecolor(grid_color)
        collection.set_alpha(0.3)

    for text in ax.texts:
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
