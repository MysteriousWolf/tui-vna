# VNA Drivers

VNA drivers are automatically discovered - just drop a file here!

## Quick Start

Create a driver file (e.g., `my_vna.py`):

```python
from .base import VNABase, VNAConfig
import numpy as np

class MyVNA(VNABase):
    """My VNA Model controller."""

    # Required: driver metadata
    driver_name = "My VNA Model"

    @staticmethod
    def idn_matcher(idn_string: str) -> bool:
        """Return True if this driver supports the instrument."""
        return "my_model" in idn_string.lower()

    # Required: implement abstract methods
    def __init__(self, config=None):
        super().__init__(config)
        self.inst = None

    def connect(self, progress_callback=None) -> bool:
        # Connection code
        pass

    def disconnect(self) -> None:
        # Disconnection code
        pass

    def configure_frequency(self) -> None:
        pass

    def configure_measurements(self) -> None:
        pass

    def setup_s_parameters(self) -> None:
        pass

    def trigger_sweep(self) -> None:
        pass

    def get_frequency_axis(self) -> np.ndarray:
        pass

    def get_sparam_data(self, param_num: int):
        pass

    def get_all_sparameters(self) -> dict:
        pass
```

**That's it!** Your driver is automatically:

- Discovered on startup
- Tested against every VNA connection
- Used when `idn_matcher` returns `True`

## How Discovery Works

On startup:

1. Scans all `.py` files in this directory
2. Imports each module
3. Finds classes that inherit `VNABase` and have `idn_matcher`
4. Registers them

On connection:

1. Connects to get `*IDN?` response
2. Tests each driver's `idn_matcher()`
3. Uses the first match
4. Logs: "Detected: [Driver Name]"

## IDN Matching Examples

**Simple string match:**

```python
@staticmethod
def idn_matcher(idn_string: str) -> bool:
    return "e5071" in idn_string.lower()
```

**Multiple patterns:**

```python
@staticmethod
def idn_matcher(idn_string: str) -> bool:
    return any(p in idn_string.lower()
               for p in ["n9913", "fieldfox"])
```

**Regex:**

```python
import re

@staticmethod
def idn_matcher(idn_string: str) -> bool:
    return bool(re.search(r'n99\d{2}', idn_string, re.I))
```

## SCPI Commands

Reusable commands in `scpi_commands.py`:

```python
from .scpi_commands import (
    CMD_IDN,                # "*IDN?"
    cmd_set_freq_start,     # Function: cmd_set_freq_start(freq_hz)
    cmd_set_sweep_points,   # Function: cmd_set_sweep_points(points)
)
```

## Testing

```python
from tina.drivers import detect_vna_driver, list_available_drivers

# List all drivers
print(list_available_drivers())

# Test detection
driver_class = detect_vna_driver("MANUFACTURER,MODEL,...")
if driver_class:
    print(f"Detected: {driver_class.driver_name}")
```

## Current Drivers

- **HP E5071B** - HP/Agilent/Keysight E5071 series (A/B/C variants)

## Troubleshooting

**Driver not discovered:**

- File must be in this directory
- Must inherit from `VNABase`
- Must have `driver_name` and `idn_matcher`
- Check syntax: `python3 -m py_compile your_driver.py`

**Driver not selected:**

- Test your `idn_matcher` with actual IDN string
- First matching driver wins
- Use case-insensitive matching

For more details, see the main README or look at `hp_e5071b.py` as an example.
