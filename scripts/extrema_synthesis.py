#!/usr/bin/env python3
"""Generate synthetic traces and evaluate simple extrema detector.

Creates several synthetic traces (multi-gaussian peaks, spikes, step+peaks),
adds Gaussian noise, runs detect_extrema with multiple smoothing windows and
saves summary plots to scripts/extrema_outputs.

Exit 0 on success.
"""

from __future__ import annotations

import os
from collections.abc import Iterable
from dataclasses import dataclass

import matplotlib.pyplot as plt
import numpy as np


def moving_average(data: np.ndarray, window: int) -> np.ndarray:
    """Return moving average with odd window using 'same' convolution.

    Window must be odd and >=3.
    """
    if window < 3:
        return data
    if window % 2 == 0:
        raise ValueError("window must be odd")
    kernel = np.ones(window, dtype=float) / float(window)
    return np.convolve(data, kernel, mode="same")


def detect_extrema(
    data: Iterable[float], smoothing_window: int | None = None, minima: bool = False
) -> np.ndarray:
    """Detect local extrema via sign changes of the first derivative.

    If smoothing_window is provided, it must be an odd integer >=3 and a
    moving-average is applied before detection.

    Returns array of indices of detected extrema.
    """
    arr = np.asarray(list(data), dtype=float)
    if arr.size < 3:
        return np.array([], dtype=int)

    if smoothing_window is not None:
        if smoothing_window < 3:
            smoothing_window = 3
        if smoothing_window % 2 == 0:
            smoothing_window += 1
        arr_s = moving_average(arr, smoothing_window)
    else:
        arr_s = arr

    d = np.diff(arr_s)
    if d.size < 2:
        return np.array([], dtype=int)

    if minima:
        cond = (d[:-1] < 0) & (d[1:] > 0)
    else:
        cond = (d[:-1] > 0) & (d[1:] < 0)

    idx = np.where(cond)[0] + 1
    return idx


@dataclass
class TraceSpec:
    name: str
    x: np.ndarray
    y: np.ndarray


def synth_multi_gaussian(
    xs: np.ndarray, peaks: Iterable[tuple[float, float, float]]
) -> np.ndarray:
    """Sum of Gaussians. peaks is iterable of (center, amp, width).
    width corresponds to stddev.
    """
    y = np.zeros_like(xs)
    for c, a, w in peaks:
        y += a * np.exp(-0.5 * ((xs - c) / w) ** 2)
    return y


def synth_spikes(
    xs: np.ndarray, positions: Iterable[float], height=1.0, width=0.001
) -> np.ndarray:
    y = np.zeros_like(xs)
    for p in positions:
        y += height * np.exp(-0.5 * ((xs - p) / width) ** 2)
    return y


def synth_step_peaks(xs: np.ndarray) -> np.ndarray:
    y = np.zeros_like(xs)
    y[xs > 0.3] += 0.5
    y[xs > 0.6] -= 0.3
    # add small peaks
    y += synth_multi_gaussian(
        xs, [(0.15, 0.6, 0.01), (0.45, 0.4, 0.02), (0.8, 0.7, 0.015)]
    )
    return y


def ensure_outdir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def make_traces(n: int = 2000, seed: int = 0) -> list[TraceSpec]:
    rng = np.random.default_rng(seed)
    xs = np.linspace(0.0, 1.0, n)

    # Multi Gaussian
    peaks = [(0.1, 1.0, 0.01), (0.25, 0.8, 0.02), (0.5, 1.3, 0.015), (0.75, 0.6, 0.02)]
    y1 = synth_multi_gaussian(xs, peaks)
    y1 += 0.05 * rng.normal(size=xs.size)

    # Dense small peaks
    small_peaks = [
        (p, 0.3 + 0.2 * rng.random(), 0.005 + 0.01 * rng.random())
        for p in np.linspace(0.05, 0.95, 12)
    ]
    y2 = synth_multi_gaussian(xs, small_peaks)
    y2 += 0.08 * rng.normal(size=xs.size)

    # Spikes
    spike_positions = rng.choice(xs, size=15, replace=False)
    y3 = synth_spikes(xs, spike_positions, height=1.0, width=0.002)
    y3 += 0.03 * rng.normal(size=xs.size)

    # Step + peaks
    y4 = synth_step_peaks(xs)
    y4 += 0.06 * rng.normal(size=xs.size)

    traces = [
        TraceSpec("multi_gaussian", xs, y1),
        TraceSpec("small_peaks", xs, y2),
        TraceSpec("spikes", xs, y3),
        TraceSpec("step_peaks", xs, y4),
    ]
    return traces


def summarize_and_plot(traces: Iterable[TraceSpec], outdir: str) -> None:
    ensure_outdir(outdir)
    windows = [None, 3, 5, 11, 21, 51, 101]

    for tr in traces:
        counts = []
        detections = {}
        for w in windows:
            idx = detect_extrema(tr.y, smoothing_window=w, minima=False)
            counts.append(len(idx))
            detections[w] = idx

        # Print table of counts
        row = f"{tr.name:15s}"
        for c in counts:
            row += f" {c:4d}"
        print(row)

        # Make a summary figure: top - raw data + detected extrema for subset windows
        sel_windows = [None, 5, 21, 101]
        fig, (ax1, ax2) = plt.subplots(
            2, 1, figsize=(10, 8), gridspec_kw={"height_ratios": [3, 1]}
        )
        ax1.plot(tr.x, tr.y, color="#1f77b4", linewidth=1)
        colors = ["#ff7f0e", "#2ca02c", "#d62728", "#9467bd"]
        for w, col in zip(sel_windows, colors):
            idx = detections.get(w, np.array([], dtype=int))
            ax1.scatter(tr.x[idx], tr.y[idx], color=col, label=f"w={w}", s=20)
        ax1.legend()
        ax1.set_title(f"{tr.name} - raw with detected maxima (subset of windows)")

        # bottom: counts vs window
        xs = [0 if w is None else w for w in windows]
        ax2.plot(xs, counts, marker="o")
        ax2.set_xscale("log")
        ax2.set_xlabel("smoothing window (None->0)")
        ax2.set_ylabel("# maxima")
        ax2.grid(True, alpha=0.3)

        plt.tight_layout()
        outpath = os.path.join(outdir, f"{tr.name}_summary.png")
        plt.savefig(outpath)
        plt.close(fig)


def main() -> int:
    traces = make_traces()
    header = "Trace           " + " ".join(
        [f"{w:4}" for w in ["None", 3, 5, 11, 21, 51, 101]]
    )
    print(header)
    print("-" * len(header))
    summarize_and_plot(traces, os.path.join("scripts", "extrema_outputs"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
