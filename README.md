# tina - Terminal UI Network Analyzer

Modern terminal-based control interface for Vector Network Analyzers.

**tina** (Terminal UI Network Analyzer) is a TUI application for controlling VNAs with a clean interface and powerful CLI automation.

## Features

- 🎯 Clean TUI with real-time plotting and automatic S2P/PNG export
- 🖥️ CLI mode for automation: `hp-e5071b --now` for quick measurements
- ⚡ Fast SCPI over TCP/IP with multithreaded architecture
- 📊 Full S-parameter support (S11/S21/S12/S22) with outlier filtering
- 🔧 Configurable frequency, sweep points, averaging, and detailed logging

## Installation

```bash
uv tool install .
tina                # GUI mode
tina --now          # CLI quick measurement

# Or build standalone executables (Windows users)
cd scripts && ./build.sh  # Creates dist/tina.exe
```

## Quick Start

**GUI Mode:** Connect → Configure → Measure → View Results  
**CLI Mode:** `tina --now` (uses last settings)

**Tabs:** Measurement (setup) | Log (SCPI commands) | Results (plots)

## Configuration

**Connection:** VNA IP + VISA port (default: `inst0`)  
**Measurement:** Frequency range, sweep points, averaging (with override checkboxes)  
**Output:** Folder (`measurement/`), filename prefix, S-parameter selection

## Output Files

**Location:** `measurement/` folder (configurable)  
**Formats:** `.s2p` (Touchstone) + `.png` plots (CLI mode)  
**Example:** `measurement_20260127_143052.s2p`

CLI mode also generates magnitude/phase PNG plots at 1080p resolution.

## Plotting & CLI

**Plots:** 1% outlier filtering, selectable parameters, color-coded traces  
**Log Filtering:** TX/RX SCPI commands, progress, errors, debug info

**CLI Examples:**

```bash
tina --now                                    # Quick measure
tina --host 192.168.1.100 --points 201       # Custom params
tina -n --all-sparams --plot-all              # All S-params + plots
```

**Key Options:** `--host`, `--start-freq`, `--stop-freq`, `--points`, `--averaging`, `--output-folder`, `--all-sparams`, `--plot-all`

## Log Filtering

## Architecture

**Two-thread design:** UI thread (responsive) + worker thread (VNA operations)  
**Components:** `main.py` (GUI/CLI), `vna.py` (SCPI), `worker.py` (threading), `touchstone.py` (S2P export)

## Python API

```python
from tina import VNA, VNAConfig, TouchstoneExporter

config = VNAConfig(host="192.168.1.100", start_freq_hz=10e6, stop_freq_hz=1500e6)
with VNA(config) as vna:
    freqs, sparams = vna.perform_measurement()
    TouchstoneExporter().export(freqs, sparams, "measurement")
```

## Development & Troubleshooting

**Requirements:** Python 3.10+, PyVISA-py, Textual, NumPy, Matplotlib  
**Install:** `uv tool install .`

**Common Issues:** Check VNA IP, ensure network connectivity, verify VNA not in manual mode, sweep points 2-1601

## License

MIT License
