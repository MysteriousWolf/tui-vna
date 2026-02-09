"""
Touchstone file export for S-parameter data.
"""

import os
from datetime import datetime

import numpy as np


class TouchstoneExporter:
    """Export S-parameter data to Touchstone .s2p format."""

    def __init__(self, freq_unit: str = "MHz", reference_impedance: float = 50.0):
        """
        Initialize exporter.

        Args:
            freq_unit: Frequency unit ('Hz', 'kHz', 'MHz', 'GHz')
            reference_impedance: Reference impedance in ohms
        """
        self.freq_unit = freq_unit
        self.reference_impedance = reference_impedance

    def _convert_frequency(self, freq_hz: float) -> float:
        """Convert frequency from Hz to configured unit."""
        conversions = {"Hz": 1.0, "kHz": 1e3, "MHz": 1e6, "GHz": 1e9}
        return freq_hz / conversions.get(self.freq_unit, 1e6)

    def export(
        self,
        frequencies_hz: np.ndarray,
        s_parameters: dict[str, tuple[np.ndarray, np.ndarray]],
        output_path: str,
        filename: str = None,
        prefix: str = "measurement",
    ) -> str:
        """
        Export S-parameters to Touchstone file (.s2p format).

        Follows Touchstone format specification:
        - Option line: # <freq_unit> S <format> R <impedance>
        - Data format: freq S11_mag S11_ang S21_mag S21_ang S12_mag S12_ang S22_mag S22_ang
        - All angles in degrees
        - All magnitudes in dB

        Args:
            frequencies_hz: Frequency array in Hz
            s_parameters: Dict with S-parameters as keys (e.g., 'S11', 'S21'),
                         values are (magnitude_db, phase_deg) tuples
            output_path: Output directory
            filename: Custom filename (auto-generated if None)
            prefix: Prefix for auto-generated filename

        Returns:
            Full path to created file
        """
        # Validate inputs - now flexible for any subset of S-parameters
        for param, data in s_parameters.items():
            mag_db, phase_deg = data
            if len(mag_db) != len(frequencies_hz) or len(phase_deg) != len(
                frequencies_hz
            ):
                raise ValueError(
                    f"S-parameter {param} data length mismatch with frequencies"
                )

        # Get all available parameters
        available_params = ["S11", "S21", "S12", "S22"]
        export_params = [p for p in available_params if p in s_parameters]

        if not export_params:
            raise ValueError("No valid S-parameters provided for export")

        # Create output directory
        os.makedirs(output_path, exist_ok=True)

        # Generate filename
        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"{prefix}_{timestamp}"

        if not filename.lower().endswith(".s2p"):
            filename += ".s2p"

        full_path = os.path.join(output_path, filename)

        # Write file
        with open(full_path, "w", encoding="utf-8") as f:
            # Write header comments
            f.write("! HP E5071B S-Parameter Data\n")
            f.write(f"! Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(
                f"! Frequency Range: {frequencies_hz[0] / 1e6:.3f} - {frequencies_hz[-1] / 1e6:.3f} MHz\n"
            )
            f.write(f"! Points: {len(frequencies_hz)}\n")
            f.write("!\n")

            # Write option line (Touchstone format specification)
            # Format: # <freq_unit> S <format> R <impedance>
            # freq_unit: Hz, kHz, MHz, GHz
            # S: S-parameters
            # DB: dB magnitude and angle in degrees
            # R: Reference impedance follows
            f.write(f"# {self.freq_unit} S DB R {self.reference_impedance}\n")

            # Write data points
            # Format per line: freq S11_mag S11_ang S21_mag S21_ang S12_mag S12_ang S22_mag S22_ang
            # All angles in degrees, all magnitudes in dB
            for i, freq_hz in enumerate(frequencies_hz):
                freq = self._convert_frequency(freq_hz)

                # Build data line with proper S-parameter order (only exported params)
                values = [f"{freq:.6f}"]

                for param in export_params:
                    mag_db, phase_deg = s_parameters[param]
                    values.append(f"{mag_db[i]:.6f}")
                    values.append(f"{phase_deg[i]:.6f}")

                # Write data line with space separation
                f.write("  ".join(values) + "\n")

        return full_path

    @staticmethod
    def import_file(
        file_path: str,
    ) -> tuple[np.ndarray, dict[str, tuple[np.ndarray, np.ndarray]]]:
        """
        Import S-parameters from Touchstone file (.s2p format).

        Args:
            file_path: Path to .s2p file

        Returns:
            Tuple of (frequencies_hz, s_parameters)
            where s_parameters is Dict[str, Tuple[mag_db, phase_deg]]

        Raises:
            ValueError: If file format is invalid
            FileNotFoundError: If file doesn't exist
        """
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File not found: {file_path}")

        freq_unit = "MHz"  # Default
        frequencies = []
        s_params = {"S11": ([], []), "S21": ([], []), "S12": ([], []), "S22": ([], [])}

        with open(file_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()

                # Skip empty lines and comments (but not option line)
                if not line or (line.startswith("!") and not line.startswith("# ")):
                    continue

                # Parse option line
                if line.startswith("#"):
                    parts = line.split()
                    if len(parts) >= 2:
                        freq_unit = parts[1]  # Extract frequency unit
                    continue

                # Parse data line
                try:
                    values = [float(v) for v in line.split()]
                    if len(values) < 3:  # At least freq + one S-param
                        continue

                    freq = values[0]
                    frequencies.append(freq)

                    # Parse S-parameters (pairs of mag, phase)
                    # Format: freq S11_mag S11_ang S21_mag S21_ang S12_mag S12_ang S22_mag S22_ang
                    param_names = ["S11", "S21", "S12", "S22"]
                    for idx, param_name in enumerate(param_names):
                        mag_idx = 1 + idx * 2
                        phase_idx = 2 + idx * 2

                        if phase_idx < len(values):
                            s_params[param_name][0].append(values[mag_idx])
                            s_params[param_name][1].append(values[phase_idx])

                except (ValueError, IndexError):
                    continue  # Skip malformed lines

        if not frequencies:
            raise ValueError("No valid data found in file")

        # Convert to numpy arrays
        freq_array = np.array(frequencies)

        # Convert frequency to Hz
        conversions = {"Hz": 1.0, "kHz": 1e3, "MHz": 1e6, "GHz": 1e9}
        multiplier = conversions.get(freq_unit, 1e6)
        freq_hz = freq_array * multiplier

        # Convert S-parameter lists to numpy arrays
        result_params = {}
        for param_name, (mags, phases) in s_params.items():
            if mags:  # Only include parameters that have data
                result_params[param_name] = (np.array(mags), np.array(phases))

        return freq_hz, result_params
