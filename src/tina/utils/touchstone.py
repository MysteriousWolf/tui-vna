"""
Touchstone file export and import helpers for S-parameter data.

This module supports standard Touchstone `.s2p` export/import plus TINA-specific
comment metadata blocks used for notes and future recovery workflows.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import numpy as np
from ruamel.yaml import YAML

_TOUCHSTONE_PARAM_ORDER: tuple[str, ...] = ("S11", "S21", "S12", "S22")
_FREQ_UNIT_FACTORS: dict[str, float] = {
    "Hz": 1.0,
    "kHz": 1e3,
    "MHz": 1e6,
    "GHz": 1e9,
}

_METADATA_VERSION = 1
_NOTES_BEGIN = "TINA NOTES BEGIN"
_NOTES_END = "TINA NOTES END"
_METADATA_BEGIN = "TINA METADATA BEGIN"
_METADATA_END = "TINA METADATA END"

_yaml = YAML()
_yaml.default_flow_style = False
_yaml.width = 4096


@dataclass(slots=True, frozen=True)
class TouchstoneMetadata:
    """Parsed TINA metadata extracted from a Touchstone file."""

    notes_markdown: str = ""
    machine_settings: dict[str, Any] | None = None
    metadata_version: int | None = None


@dataclass(slots=True, frozen=True)
class TouchstoneImportResult:
    """Structured Touchstone import result including optional metadata."""

    frequencies_hz: np.ndarray
    s_parameters: dict[str, tuple[np.ndarray, np.ndarray]]
    metadata: TouchstoneMetadata


class TouchstoneExporter:
    """Export and import S-parameter data in Touchstone `.s2p` format."""

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
        return freq_hz / _FREQ_UNIT_FACTORS.get(
            self.freq_unit, _FREQ_UNIT_FACTORS["MHz"]
        )

    @staticmethod
    def _normalize_export_params(
        s_parameters: dict[str, tuple[np.ndarray, np.ndarray]],
    ) -> list[str]:
        """Return exported S-parameters in Touchstone column order."""
        export_params = [
            name for name in _TOUCHSTONE_PARAM_ORDER if name in s_parameters
        ]
        if not export_params:
            raise ValueError("No valid S-parameters provided for export")
        return export_params

    @staticmethod
    def _validate_inputs(
        frequencies_hz: np.ndarray,
        s_parameters: dict[str, tuple[np.ndarray, np.ndarray]],
    ) -> None:
        """Validate frequency and S-parameter array lengths."""
        if len(frequencies_hz) == 0:
            raise ValueError("No frequency points provided for export")

        for param, data in s_parameters.items():
            mag_db, phase_deg = data
            if len(mag_db) != len(frequencies_hz) or len(phase_deg) != len(
                frequencies_hz
            ):
                raise ValueError(
                    f"S-parameter {param} data length mismatch with frequencies"
                )

    @staticmethod
    def _resolve_output_path(
        output_path: str,
        filename: str | None,
        prefix: str,
    ) -> str:
        """Resolve and create the destination path for the Touchstone export."""
        os.makedirs(output_path, exist_ok=True)

        resolved_name = filename
        if resolved_name is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            resolved_name = f"{prefix}_{timestamp}"

        if not resolved_name.lower().endswith(".s2p"):
            resolved_name += ".s2p"

        return os.path.join(output_path, resolved_name)

    @staticmethod
    def _build_notes_comment_lines(notes_markdown: str) -> list[str]:
        """Build the human-readable notes comment block."""
        notes = notes_markdown.rstrip("\n")
        if not notes:
            return []

        lines = [
            f"! {_NOTES_BEGIN}",
            "! Raw markdown notes below. You may edit these manually.",
        ]
        for line in notes.splitlines():
            lines.append(f"! {line}" if line else "!")
        lines.append(f"! {_NOTES_END}")
        lines.append("!")
        return lines

    @staticmethod
    def _build_metadata_payload(
        metadata: dict[str, Any] | None,
    ) -> dict[str, Any]:
        """Normalize machine-readable metadata payload with a required version."""
        payload: dict[str, Any] = {"metadata_version": _METADATA_VERSION}
        if metadata:
            payload.update(metadata)
            payload["metadata_version"] = metadata.get(
                "metadata_version", _METADATA_VERSION
            )
        return payload

    @classmethod
    def _serialize_metadata_comment_lines(
        cls,
        metadata: dict[str, Any] | None,
    ) -> list[str]:
        """Build the trailing machine-readable metadata comment block."""
        if metadata is None:
            return []

        payload = cls._build_metadata_payload(metadata)

        from io import StringIO

        buffer = StringIO()
        _yaml.dump(payload, buffer)
        yaml_text = buffer.getvalue().rstrip("\n")

        lines = [
            "!",
            f"! {_METADATA_BEGIN}",
            "! Machine-readable settings for TINA import/recovery.",
            "! You may edit the markdown notes block manually, but avoid changing",
            "! this machine settings block if reliable re-import is desired.",
        ]
        for line in yaml_text.splitlines():
            lines.append(f"! {line}" if line else "!")
        lines.append(f"! {_METADATA_END}")
        return lines

    @staticmethod
    def _strip_comment_prefix(line: str) -> str:
        """Remove the Touchstone comment prefix from one line."""
        if not line.startswith("!"):
            return line.rstrip("\n")
        stripped = line[1:]
        if stripped.startswith(" "):
            stripped = stripped[1:]
        return stripped.rstrip("\n")

    @classmethod
    def _extract_block_lines(
        cls,
        lines: list[str],
        begin_marker: str,
        end_marker: str,
    ) -> list[str]:
        """Extract raw comment payload lines between two TINA markers."""
        begin_index: int | None = None
        end_index: int | None = None

        for index, line in enumerate(lines):
            content = cls._strip_comment_prefix(line)
            if content == begin_marker:
                begin_index = index
            elif content == end_marker and begin_index is not None:
                end_index = index
                break

        if begin_index is None or end_index is None or end_index <= begin_index:
            return []

        return [
            cls._strip_comment_prefix(line)
            for line in lines[begin_index + 1 : end_index]
        ]

    @classmethod
    def _parse_notes_block(cls, lines: list[str]) -> str:
        """Parse the human-readable notes block from Touchstone comments."""
        payload_lines = cls._extract_block_lines(lines, _NOTES_BEGIN, _NOTES_END)
        if not payload_lines:
            return ""

        if (
            payload_lines
            and payload_lines[0]
            == "Raw markdown notes below. You may edit these manually."
        ):
            payload_lines = payload_lines[1:]

        return "\n".join(payload_lines).rstrip()

    @classmethod
    def _parse_metadata_block(cls, lines: list[str]) -> dict[str, Any] | None:
        """Parse the trailing machine-readable YAML metadata block."""
        payload_lines = cls._extract_block_lines(lines, _METADATA_BEGIN, _METADATA_END)
        if not payload_lines:
            return None

        filtered_lines: list[str] = []
        for line in payload_lines:
            if line.startswith("Machine-readable settings for TINA import/recovery."):
                continue
            if line.startswith(
                "You may edit the markdown notes block manually, but avoid changing"
            ):
                continue
            if line.startswith(
                "this machine settings block if reliable re-import is desired."
            ):
                continue
            filtered_lines.append(line)

        yaml_text = "\n".join(filtered_lines).strip()
        if not yaml_text:
            return None

        try:
            parsed = _yaml.load(yaml_text)
        except Exception:
            return None

        if isinstance(parsed, dict):
            return dict(parsed)
        return None

    @classmethod
    def parse_metadata_from_text(cls, text: str) -> TouchstoneMetadata:
        """Parse TINA notes and machine metadata blocks from Touchstone text."""
        lines = text.splitlines()
        notes_markdown = cls._parse_notes_block(lines)
        machine_settings = cls._parse_metadata_block(lines)
        metadata_version: int | None = None

        if isinstance(machine_settings, dict):
            version = machine_settings.get("metadata_version")
            if isinstance(version, int):
                metadata_version = version

        return TouchstoneMetadata(
            notes_markdown=notes_markdown,
            machine_settings=machine_settings,
            metadata_version=metadata_version,
        )

    def export(
        self,
        frequencies_hz: np.ndarray,
        s_parameters: dict[str, tuple[np.ndarray, np.ndarray]],
        output_path: str,
        filename: str | None = None,
        prefix: str = "measurement",
        *,
        notes_markdown: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """
        Export S-parameters to a Touchstone file.

        Follows Touchstone format specification:
        - Option line: # <freq_unit> S DB R <impedance>
        - Data format: freq S11_mag S11_ang S21_mag S21_ang S12_mag S12_ang S22_mag S22_ang
        - All angles in degrees
        - All magnitudes in dB

        TINA-specific additions:
        - Optional human-readable notes block at the beginning in comment lines
        - Optional machine-readable YAML metadata block at the end in comment lines

        Args:
            frequencies_hz: Frequency array in Hz
            s_parameters: Dict with S-parameters as keys (e.g., 'S11', 'S21'),
                values are (magnitude_db, phase_deg) tuples
            output_path: Output directory
            filename: Custom filename (auto-generated if None)
            prefix: Prefix for auto-generated filename
            notes_markdown: Raw markdown notes to include in a readable comment block
            metadata: Machine-readable metadata/settings payload

        Returns:
            Full path to created file
        """
        self._validate_inputs(frequencies_hz, s_parameters)
        export_params = self._normalize_export_params(s_parameters)
        full_path = self._resolve_output_path(output_path, filename, prefix)

        with open(full_path, "w", encoding="utf-8") as f:
            f.write("! HP E5071B S-Parameter Data\n")
            f.write(f"! Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(
                f"! Frequency Range: {frequencies_hz[0] / 1e6:.3f} - "
                f"{frequencies_hz[-1] / 1e6:.3f} MHz\n"
            )
            f.write(f"! Points: {len(frequencies_hz)}\n")
            f.write("!\n")

            for line in self._build_notes_comment_lines(notes_markdown):
                f.write(line + "\n")

            f.write(f"# {self.freq_unit} S DB R {self.reference_impedance}\n")

            for i, freq_hz in enumerate(frequencies_hz):
                freq = self._convert_frequency(float(freq_hz))
                values = [f"{freq:.6f}"]

                for param in export_params:
                    mag_db, phase_deg = s_parameters[param]
                    values.append(f"{float(mag_db[i]):.6f}")
                    values.append(f"{float(phase_deg[i]):.6f}")

                f.write("  ".join(values) + "\n")

            for line in self._serialize_metadata_comment_lines(metadata):
                f.write(line + "\n")

        return full_path

    @classmethod
    def import_with_metadata(cls, file_path: str) -> TouchstoneImportResult:
        """
        Import a Touchstone file and return numeric data plus parsed TINA metadata.

        Args:
            file_path: Path to `.s2p` file

        Returns:
            Structured import result with frequencies, S-parameters, and metadata

        Raises:
            ValueError: If file format is invalid
            FileNotFoundError: If file doesn't exist
        """
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File not found: {file_path}")

        freq_unit = "MHz"
        frequencies: list[float] = []
        s_params: dict[str, tuple[list[float], list[float]]] = {
            "S11": ([], []),
            "S21": ([], []),
            "S12": ([], []),
            "S22": ([], []),
        }

        # Read the file once into memory and reuse the content for both
        # metadata parsing and numeric line iteration to avoid double I/O.
        with open(file_path, encoding="utf-8") as f:
            text = f.read()
        metadata = cls.parse_metadata_from_text(text)

        for raw_line in text.splitlines():
            line = raw_line.strip()

            if not line:
                continue

            if line.startswith("!"):
                continue

            if line.startswith("#"):
                parts = line.split()
                if len(parts) >= 2:
                    freq_unit = parts[1]
                continue

            try:
                values = [float(v) for v in line.split()]
                if len(values) < 3:
                    continue

                frequencies.append(values[0])

                for idx, param_name in enumerate(_TOUCHSTONE_PARAM_ORDER):
                    mag_idx = 1 + idx * 2
                    phase_idx = 2 + idx * 2
                    if phase_idx < len(values):
                        s_params[param_name][0].append(values[mag_idx])
                        s_params[param_name][1].append(values[phase_idx])

            except (ValueError, IndexError):
                continue

        if not frequencies:
            raise ValueError("No valid data found in file")

        freq_array = np.array(frequencies, dtype=float)
        multiplier = _FREQ_UNIT_FACTORS.get(freq_unit, _FREQ_UNIT_FACTORS["MHz"])
        freq_hz = freq_array * multiplier

        result_params: dict[str, tuple[np.ndarray, np.ndarray]] = {}
        for param_name, (mags, phases) in s_params.items():
            if mags:
                result_params[param_name] = (
                    np.array(mags, dtype=float),
                    np.array(phases, dtype=float),
                )

        return TouchstoneImportResult(
            frequencies_hz=freq_hz,
            s_parameters=result_params,
            metadata=metadata,
        )

    @staticmethod
    def import_file(
        file_path: str,
    ) -> tuple[np.ndarray, dict[str, tuple[np.ndarray, np.ndarray]]]:
        """
        Import S-parameters from a Touchstone file.

        This compatibility helper preserves the historical return type while
        delegating parsing to the metadata-aware importer.

        Args:
            file_path: Path to `.s2p` file

        Returns:
            Tuple of (frequencies_hz, s_parameters)

        Raises:
            ValueError: If file format is invalid
            FileNotFoundError: If file doesn't exist
        """
        result = TouchstoneExporter.import_with_metadata(file_path)
        return result.frequencies_hz, result.s_parameters
