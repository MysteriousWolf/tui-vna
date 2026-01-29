# tina - Terminal user Interface Network Analyzer

Terminal-based VNA control with **dynamic driver discovery**.

## Features

- 🔌 Plugin architecture - add VNA support by dropping a driver file
- 🎯 Clean TUI with real-time plotting and S2P export
- ⚡ Automatic driver detection from `*IDN?` response
- 🖥️ CLI mode: `tina --now` for quick measurements

## Installation

### Option 1: Install via uv (Recommended)

```bash
# Install directly from GitHub repository
uv tool install git+https://github.com/MysteriousWolf/tui-vna

# Run the application
tina                # GUI mode
tina --now          # CLI quick measurement
```

**Why uv?** Faster startup, smaller footprint, automatic dependency management.

### Option 2: Pre-built Binaries

For systems without Python/uv, download standalone executables from [GitHub Releases](https://github.com/MysteriousWolf/tui-vna/releases):

- **Windows**: `tina-windows-x86_64.exe`
- **Linux**: `tina-linux-x86_64`
- **macOS**: `tina-macos-x86_64`

No installation required - just download and run!

Note: Binaries have larger size and slower startup compared to uv installation.

### Option 3: Install from Local Clone (Development)

```bash
# Clone and install
git clone https://github.com/MysteriousWolf/tui-vna
cd tui-vna
uv tool install .

# Run the application
tina                # GUI mode
tina --now          # CLI quick measurement
```

## Project Structure

```
src/tina/            # Main application package
├── config/          # Settings and constants
├── drivers/         # VNA drivers (auto-discovered!)
├── utils/           # Helper modules (colors, terminal, paths, touchstone)
├── gui/             # TUI resources
├── main.py          # Application entry point
└── worker.py        # Threaded measurement worker
scripts/             # Build configurations (PyInstaller)
res/                 # Resources (icons)
run_tina.py          # PyInstaller entry point stub
```

## Adding a New VNA Driver

Create `src/tina/drivers/your_vna.py`:

```python
from .base import VNABase, VNAConfig

class YourVNA(VNABase):
    driver_name = "Your VNA Model"

    @staticmethod
    def idn_matcher(idn_string: str) -> bool:
        return "your_model" in idn_string.lower()

    # Implement required methods...
```

**Done!** Auto-discovered on startup. See `src/tina/drivers/README.md`.

## Quick Start

**GUI:** Connect → Configure → Measure → View Results

**CLI:**

```bash
tina --now                              # Quick measure
tina --host 192.168.1.100 --points 201 # Custom params
```

## Configuration

- **Connection:** VNA IP + VISA port (default: `inst0`)
- **Measurement:** Frequency range, sweep points, averaging
- **Output:** Folder (`measurement/`), S-parameter selection

All constants in `src/tina/config/constants.py`.

## Architecture

- **Plugin System:** Drivers auto-discovered from `drivers/` folder
- **Auto-detection:** Connects, reads `*IDN?`, switches to matching driver
- **Modular:** Config, drivers, utils clearly separated
- **SCPI library:** Reusable commands in `drivers/scpi_commands.py`

Supported VNAs:

- HP/Agilent/Keysight E5071 series

## Python API

```python
from tina.drivers import VNAConfig, HPE5071B
from tina.utils import TouchstoneExporter

config = VNAConfig(host="192.168.1.100", start_freq_hz=10e6, stop_freq_hz=1500e6)
with HPE5071B(config) as vna:
    freqs, sparams = vna.perform_measurement()
    TouchstoneExporter().export(freqs, sparams, "measurement")
```

## Development

**Requirements:** Python 3.10+, PyVISA-py, Textual, NumPy, Matplotlib

**Structure:**

- `config/` - Constants and settings
- `drivers/` - VNA drivers with auto-discovery
- `utils/` - Colors, terminal, paths, touchstone
- `gui/` - TUI resources (CSS in `.tcss`)

## License

MIT

---

<sub>This project is developed with the assistance of LLMs.</sub>
