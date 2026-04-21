#!/usr/bin/env python3
"""Grid search for extrema detector prominence tuning.

Loads scripts/extrema_synthesis.make_traces to obtain synthetic traces, then
calls tina.gui.tabs.tools_logic._detect_candidates_with_smoothing across a
grid of desired_peaks and prominence_factor values. Emits CSV-like results to
stdout and saves summary PNGs per-trace into scripts/extrema_tune_outputs.

Exit 0 on success.
"""

from __future__ import annotations

import importlib.util
import os
import sys

import matplotlib.pyplot as plt


def ensure_outdir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def load_module_from_path(path: str, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    # Ensure the module is present in sys.modules while executing so decorators
    # like dataclass that inspect the module dict can find it.
    sys.modules[name] = mod
    try:
        spec.loader.exec_module(mod)  # type: ignore
    finally:
        # leave module in sys.modules for later imports
        pass
    return mod


def main() -> int:
    # Ensure imports from src work
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    src_path = os.path.join(repo_root, "src")
    if src_path not in sys.path:
        sys.path.insert(0, src_path)

    # Load extrema_synthesis dynamically and get traces
    synth_path = os.path.join(repo_root, "scripts", "extrema_synthesis.py")
    synth = load_module_from_path(synth_path, "extrema_synthesis")
    traces = synth.make_traces()

    # Import helper from the package path (now src is on sys.path)
    try:
        from tina.gui.tabs.tools_logic import _detect_candidates_with_smoothing
    except Exception as e:
        print(f"Failed importing helper: {e}", file=sys.stderr)
        return 2

    desired_peaks_list = [3, 5, 8, 10, 15, 20]
    prominence_factors = [0.001, 0.0025, 0.005, 0.01, 0.02]

    outdir = os.path.join(repo_root, "scripts", "extrema_tune_outputs")
    ensure_outdir(outdir)

    # Print CSV header
    print("trace,desired_peaks,prominence_factor,count_smoothed,count_unsmoothed")

    # For plotting, collect per-trace data: {trace_name: {desired_peaks: ([pf], [counts])}}
    for tr in traces:
        # For plotting matrix: rows desired_peaks, columns prominence_factors
        plot_data = {dp: [] for dp in desired_peaks_list}
        unsmoothed_counts = {}

        # Precompute unsmoothed counts for reference per desired_peaks (independent of prominence)
        for dp in desired_peaks_list:
            total_unsmoothed = len(
                _detect_candidates_with_smoothing(
                    tr.y, tr.x, minima=False, smoothing=False, desired_peaks=dp
                )
            )
            unsmoothed_counts[dp] = total_unsmoothed

        for pf in prominence_factors:
            for dp in desired_peaks_list:
                peaks_sm = _detect_candidates_with_smoothing(
                    tr.y,
                    tr.x,
                    minima=False,
                    smoothing=True,
                    desired_peaks=dp,
                    prominence_factor=pf,
                )
                count_sm = len(peaks_sm)
                count_unsm = unsmoothed_counts[dp]
                # Emit CSV row
                print(f"{tr.name},{dp},{pf},{count_sm},{count_unsm}")
                plot_data[dp].append(count_sm)

        # Make plot for this trace
        plt.figure(figsize=(8, 6))
        for dp in desired_peaks_list:
            plt.plot(prominence_factors, plot_data[dp], marker="o", label=f"dp={dp}")
        plt.xscale("log")
        plt.xlabel("prominence_factor")
        plt.ylabel("count_smoothed")
        plt.title(f"{tr.name} - counts vs prominence_factor")
        plt.grid(True, alpha=0.3)
        plt.legend()
        outpath = os.path.join(outdir, f"{tr.name}_grid.png")
        plt.tight_layout()
        plt.savefig(outpath)
        plt.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
