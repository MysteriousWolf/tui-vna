#!/usr/bin/env python3
"""Capture startup and feature screenshots of TINA for README documentation.

Generates:
  docs/screenshot.svg           — startup / disconnected state
  docs/screenshot-measurement.svg — Measurement tab with plotext plot
  docs/screenshot-tools.svg     — Tools tab with distortion analysis
  docs/screenshot-log.svg       — Log tab with sample entries
"""

import asyncio
from pathlib import Path
from unittest.mock import patch

import numpy as np

DOCS = Path("docs")

# ---------------------------------------------------------------------------
# Sample S-parameter data — 4th-order Butterworth bandpass, 1.5 GHz centre
# ---------------------------------------------------------------------------

_FREQS_HZ = np.linspace(300e6, 3e9, 401)
_F0_MHZ = 1500.0
_BW_MHZ = 600.0
_N = 4

_x = (_FREQS_HZ / 1e6 / _F0_MHZ - _F0_MHZ / (_FREQS_HZ / 1e6)) / _BW_MHZ * _F0_MHZ
_s21_lin = 1.0 / np.sqrt(1.0 + _x ** (2 * _N))
_s11_lin = np.sqrt(np.maximum(1.0 - _s21_lin**2, 0.0))
_s21_phase_deg = np.linspace(-10.0, -350.0, 401)
_s11_phase_deg = np.linspace(175.0, -175.0, 401)

# sparams format used internally: {param: (mag_dB_array, phase_deg_array)}
SAMPLE_SPARAMS = {
    "S11": (20.0 * np.log10(np.maximum(_s11_lin, 1e-12)), _s11_phase_deg),
    "S21": (20.0 * np.log10(np.maximum(_s21_lin, 1e-12)), _s21_phase_deg),
    "S12": (20.0 * np.log10(np.maximum(_s21_lin, 1e-12)), _s21_phase_deg),
    "S22": (20.0 * np.log10(np.maximum(_s11_lin, 1e-12)), _s11_phase_deg),
}

# Complex arrays used only for the .s2p export
_COMPLEX_SPARAMS = {
    "S11": _s11_lin * np.exp(1j * np.radians(_s11_phase_deg)),
    "S21": _s21_lin * np.exp(1j * np.radians(_s21_phase_deg)),
    "S12": _s21_lin * np.exp(1j * np.radians(_s21_phase_deg)),
    "S22": _s11_lin * np.exp(1j * np.radians(_s11_phase_deg)),
}

LAST_MEASUREMENT = {
    "freqs": _FREQS_HZ,
    "sparams": SAMPLE_SPARAMS,
    "output_path": "measurement/sample_bandpass_20250101_120000.s2p",
    "freq_unit": "MHz",
}

# Distortion tool cursors — span the passband
CURSOR1_HZ = 900e6
CURSOR2_HZ = 2100e6

# ---------------------------------------------------------------------------
# Sample log messages
# ---------------------------------------------------------------------------

LOG_ENTRIES = [
    ("Connected: HP E5071B Network Analyzer — SN/00123456", "success"),
    ("Reading VNA parameters...", "info"),
    ("Parameters retrieved successfully", "success"),
    ("Starting measurement...", "info"),
    ("Measuring S11... (25%)", "progress"),
    ("Measuring S21... (50%)", "progress"),
    ("Measuring S12... (75%)", "progress"),
    ("Measuring S22... (100%)", "progress"),
    ("Measurement complete: 401 points", "success"),
    ("S2P file saved: measurement/sample_bandpass_20250101_120000.s2p", "success"),
]

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _demo_settings():
    from tina.config.settings import AppSettings

    return AppSettings(
        last_host="",
        last_port="inst0",
        start_freq_mhz=300.0,
        stop_freq_mhz=3000.0,
        sweep_points=401,
        filename_prefix="measurement",
        output_folder="measurement",
        plot_backend="terminal",
        tools_trace="S21",
    )


async def _take(app, pilot, path: Path) -> None:
    await pilot.pause(0.6)
    path.write_text(app.export_screenshot())
    print(f"  {path}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


async def main() -> None:
    from textual.widgets import TabbedContent

    from tina.config.settings import SettingsManager
    from tina.main import VNAApp

    DOCS.mkdir(exist_ok=True)
    demo = _demo_settings()

    with patch.object(SettingsManager, "load", return_value=demo):
        app = VNAApp(dev_mode=True)
        async with app.run_test(headless=True, size=(200, 52)) as pilot:
            await pilot.pause(0.5)

            # ── 1. Startup screenshot ────────────────────────────────────────
            await _take(app, pilot, DOCS / "screenshot.svg")

            # ── 2. Inject measurement data and log entries ───────────────────
            app.last_measurement = LAST_MEASUREMENT
            for msg, level in LOG_ENTRIES:
                app.log_message(msg, level)

            # ── 3. Measurement tab ───────────────────────────────────────────
            app.query_one(TabbedContent).active = "tab_results"
            await app._refresh_results_plot()
            await _take(app, pilot, DOCS / "screenshot-measurement.svg")

            # ── 4. Tools tab — distortion ────────────────────────────────────
            app.query_one(TabbedContent).active = "tab_tools"
            app.settings.tools_active_tool = "distortion"
            app.settings.tools_trace = "S21"
            await app._rebuild_tools_params()
            app._tools_cursor1_hz = CURSOR1_HZ
            app._tools_cursor2_hz = CURSOR2_HZ
            await app._refresh_tools_plot()
            await _take(app, pilot, DOCS / "screenshot-tools.svg")

            # ── 5. Log tab ───────────────────────────────────────────────────
            app.query_one(TabbedContent).active = "tab_log"
            await _take(app, pilot, DOCS / "screenshot-log.svg")


# ---------------------------------------------------------------------------
# Sample .s2p file generation
# ---------------------------------------------------------------------------


def write_sample_s2p() -> None:
    """Write docs/sample.s2p in Touchstone MA format."""
    path = DOCS / "sample.s2p"
    DOCS.mkdir(exist_ok=True)
    lines = [
        "! Sample S2P file — 4th-order Butterworth bandpass, centre 1.5 GHz",
        "! Generated by TINA screenshot script for demonstration purposes",
        "# MHz S MA R 50",
    ]
    freqs_mhz = _FREQS_HZ / 1e6
    s11, s21, s12, s22 = (
        _COMPLEX_SPARAMS["S11"],
        _COMPLEX_SPARAMS["S21"],
        _COMPLEX_SPARAMS["S12"],
        _COMPLEX_SPARAMS["S22"],
    )
    for i, f in enumerate(freqs_mhz):
        lines.append(
            f"{f:.3f}"
            f"  {abs(s11[i]):.6f}  {np.degrees(np.angle(s11[i])):.3f}"
            f"  {abs(s21[i]):.6f}  {np.degrees(np.angle(s21[i])):.3f}"
            f"  {abs(s12[i]):.6f}  {np.degrees(np.angle(s12[i])):.3f}"
            f"  {abs(s22[i]):.6f}  {np.degrees(np.angle(s22[i])):.3f}"
        )
    path.write_text("\n".join(lines) + "\n")
    print(f"  {path}")


if __name__ == "__main__":
    print("Generating sample S2P file:")
    write_sample_s2p()
    print("Capturing screenshots:")
    asyncio.run(main())
