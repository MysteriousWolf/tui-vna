"""
Unit tests for Touchstone file export/import functionality.

Tests S-parameter file I/O including format validation, data integrity, and
TINA-specific metadata blocks for notes and recovery settings.
"""

from __future__ import annotations

import os
import tempfile

import numpy as np
import pytest

from src.tina.utils.touchstone import (
    TouchstoneExporter,
    TouchstoneImportResult,
    TouchstoneMetadata,
)


class TestTouchstoneExporter:
    """Test Touchstone exporter functionality."""

    @pytest.mark.unit
    def test_initialization(self) -> None:
        """Test exporter initialization with defaults."""
        exporter = TouchstoneExporter()
        assert exporter.freq_unit == "MHz"
        assert exporter.reference_impedance == 50.0

    @pytest.mark.unit
    def test_initialization_custom(self) -> None:
        """Test exporter initialization with custom values."""
        exporter = TouchstoneExporter(freq_unit="GHz", reference_impedance=75.0)
        assert exporter.freq_unit == "GHz"
        assert exporter.reference_impedance == 75.0

    @pytest.mark.unit
    def test_convert_frequency(self) -> None:
        """Test frequency unit conversion."""
        exporter_hz = TouchstoneExporter(freq_unit="Hz")
        exporter_mhz = TouchstoneExporter(freq_unit="MHz")
        exporter_ghz = TouchstoneExporter(freq_unit="GHz")

        freq_hz = 1e9  # 1 GHz

        assert exporter_hz._convert_frequency(freq_hz) == 1e9
        assert exporter_mhz._convert_frequency(freq_hz) == 1000.0
        assert exporter_ghz._convert_frequency(freq_hz) == 1.0

    @pytest.mark.integration
    def test_export_basic(self, sample_frequencies, sample_sparameters) -> None:
        """Test basic export functionality."""
        exporter = TouchstoneExporter()

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = exporter.export(
                sample_frequencies,
                sample_sparameters,
                tmpdir,
                filename="test_output.s2p",
            )

            assert os.path.exists(output_path)
            assert output_path.endswith(".s2p")

            with open(output_path, encoding="utf-8") as f:
                content = f.read()
                assert len(content) > 0
                assert "# MHz S DB R 50" in content
                assert "!" in content

    @pytest.mark.integration
    def test_export_auto_filename(self, sample_frequencies, sample_sparameters) -> None:
        """Test export with auto-generated filename."""
        exporter = TouchstoneExporter()

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = exporter.export(
                sample_frequencies, sample_sparameters, tmpdir, prefix="test"
            )

            assert os.path.exists(output_path)
            assert "test_" in os.path.basename(output_path)
            assert output_path.endswith(".s2p")

    @pytest.mark.integration
    def test_export_creates_directory(
        self, sample_frequencies, sample_sparameters
    ) -> None:
        """Test that export creates output directory if it doesn't exist."""
        exporter = TouchstoneExporter()

        with tempfile.TemporaryDirectory() as tmpdir:
            nested_dir = os.path.join(tmpdir, "nested", "path")
            output_path = exporter.export(
                sample_frequencies, sample_sparameters, nested_dir
            )

            assert os.path.exists(output_path)
            assert os.path.exists(nested_dir)

    @pytest.mark.integration
    def test_export_adds_extension(
        self, sample_frequencies, sample_sparameters
    ) -> None:
        """Test that .s2p extension is added if missing."""
        exporter = TouchstoneExporter()

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = exporter.export(
                sample_frequencies, sample_sparameters, tmpdir, filename="test"
            )

            assert output_path.endswith(".s2p")

    @pytest.mark.integration
    def test_export_different_units(
        self, sample_frequencies, sample_sparameters
    ) -> None:
        """Test export with different frequency units."""
        units = ["Hz", "kHz", "MHz", "GHz"]

        for unit in units:
            exporter = TouchstoneExporter(freq_unit=unit)

            with tempfile.TemporaryDirectory() as tmpdir:
                output_path = exporter.export(
                    sample_frequencies, sample_sparameters, tmpdir
                )

                with open(output_path, encoding="utf-8") as f:
                    content = f.read()
                    assert f"# {unit} S DB R" in content

    @pytest.mark.integration
    def test_export_partial_sparameters(self, sample_frequencies) -> None:
        """Test export with only some S-parameters."""
        partial_sparams = {
            "S11": (
                np.random.randn(len(sample_frequencies)),
                np.random.randn(len(sample_frequencies)),
            ),
            "S21": (
                np.random.randn(len(sample_frequencies)),
                np.random.randn(len(sample_frequencies)),
            ),
        }

        exporter = TouchstoneExporter()

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = exporter.export(sample_frequencies, partial_sparams, tmpdir)

            assert os.path.exists(output_path)

            with open(output_path, encoding="utf-8") as f:
                lines = f.readlines()
                data_lines = [
                    line
                    for line in lines
                    if line.strip() and not line.startswith(("!", "#"))
                ]
                assert len(data_lines) > 0

    @pytest.mark.unit
    def test_export_length_mismatch_error(self, sample_frequencies) -> None:
        """Test that mismatched data lengths raise error."""
        bad_sparams = {
            "S11": (
                np.random.randn(len(sample_frequencies)),
                np.random.randn(len(sample_frequencies) + 10),
            ),
        }

        exporter = TouchstoneExporter()

        with tempfile.TemporaryDirectory() as tmpdir:
            with pytest.raises(ValueError, match="length mismatch"):
                exporter.export(sample_frequencies, bad_sparams, tmpdir)

    @pytest.mark.unit
    def test_export_no_sparameters_error(self, sample_frequencies) -> None:
        """Test that exporting with no S-parameters raises error."""
        exporter = TouchstoneExporter()

        with tempfile.TemporaryDirectory() as tmpdir:
            with pytest.raises(ValueError, match="No valid S-parameters"):
                exporter.export(sample_frequencies, {}, tmpdir)

    @pytest.mark.unit
    def test_export_no_frequency_points_error(self) -> None:
        """Test that exporting with no frequency points raises error."""
        exporter = TouchstoneExporter()
        empty_freqs = np.array([], dtype=float)
        sparams = {
            "S11": (
                np.array([], dtype=float),
                np.array([], dtype=float),
            )
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            with pytest.raises(ValueError, match="No frequency points"):
                exporter.export(empty_freqs, sparams, tmpdir)

    @pytest.mark.integration
    def test_export_includes_notes_block(
        self, sample_frequencies, sample_sparameters
    ) -> None:
        """Test that readable markdown notes are written at the beginning."""
        exporter = TouchstoneExporter()
        notes = "# DUT notes\n- warmed up\n- calibrated"

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = exporter.export(
                sample_frequencies,
                sample_sparameters,
                tmpdir,
                filename="notes.s2p",
                notes_markdown=notes,
            )

            content = open(output_path, encoding="utf-8").read()

        assert "! TINA NOTES BEGIN" in content
        assert "! Raw markdown notes below. You may edit these manually." in content
        assert "! # DUT notes" in content
        assert "! - warmed up" in content
        assert "! - calibrated" in content
        assert "! TINA NOTES END" in content

    @pytest.mark.integration
    def test_export_omits_notes_block_when_empty(
        self, sample_frequencies, sample_sparameters
    ) -> None:
        """Test that empty notes do not create a readable notes block."""
        exporter = TouchstoneExporter()

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = exporter.export(
                sample_frequencies,
                sample_sparameters,
                tmpdir,
                filename="no_notes.s2p",
                notes_markdown="",
            )

            content = open(output_path, encoding="utf-8").read()

        assert "! TINA NOTES BEGIN" not in content
        assert "! TINA NOTES END" not in content

    @pytest.mark.integration
    def test_export_includes_machine_metadata_block(
        self, sample_frequencies, sample_sparameters
    ) -> None:
        """Test that trailing YAML metadata is written for recovery/import."""
        exporter = TouchstoneExporter()
        metadata = {
            "setup": {
                "host": "192.168.1.50",
                "port": "inst0",
                "freq_unit": "MHz",
            },
            "measurement": {
                "plot_type": "magnitude",
                "plot_traces": ["S11", "S21"],
            },
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = exporter.export(
                sample_frequencies,
                sample_sparameters,
                tmpdir,
                filename="metadata.s2p",
                metadata=metadata,
            )

            content = open(output_path, encoding="utf-8").read()

        assert "! TINA METADATA BEGIN" in content
        assert "! Machine-readable settings for TINA import/recovery." in content
        assert "! metadata_version: 1" in content
        assert "! setup:" in content
        assert "!   host: 192.168.1.50" in content
        assert "!   port: inst0" in content
        assert "! measurement:" in content
        assert "!   plot_type: magnitude" in content
        assert "! TINA METADATA END" in content

    @pytest.mark.integration
    def test_export_metadata_block_is_written_after_data_lines(
        self, sample_frequencies, sample_sparameters
    ) -> None:
        """Test that machine metadata is appended after the numeric body."""
        exporter = TouchstoneExporter()

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = exporter.export(
                sample_frequencies,
                sample_sparameters,
                tmpdir,
                filename="ordering.s2p",
                metadata={"setup": {"host": "lab-vna"}},
            )

            with open(output_path, encoding="utf-8") as f:
                lines = [line.rstrip("\n") for line in f]

        metadata_begin_index = lines.index("! TINA METADATA BEGIN")
        data_line_indices = [
            index
            for index, line in enumerate(lines)
            if line.strip() and not line.startswith(("!", "#"))
        ]

        assert data_line_indices
        assert metadata_begin_index > max(data_line_indices)

    @pytest.mark.integration
    def test_export_metadata_defaults_version_when_missing(
        self, sample_frequencies, sample_sparameters
    ) -> None:
        """Test that metadata_version is always present in exported YAML."""
        exporter = TouchstoneExporter()

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = exporter.export(
                sample_frequencies,
                sample_sparameters,
                tmpdir,
                filename="versioned.s2p",
                metadata={"setup": {"host": "lab-vna"}},
            )

            content = open(output_path, encoding="utf-8").read()

        assert "! metadata_version: 1" in content

    @pytest.mark.integration
    def test_export_preserves_explicit_metadata_version(
        self, sample_frequencies, sample_sparameters
    ) -> None:
        """Test that an explicit metadata version is preserved."""
        exporter = TouchstoneExporter()

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = exporter.export(
                sample_frequencies,
                sample_sparameters,
                tmpdir,
                filename="version_override.s2p",
                metadata={
                    "metadata_version": 7,
                    "setup": {"host": "lab-vna"},
                },
            )

            content = open(output_path, encoding="utf-8").read()

        assert "! metadata_version: 7" in content


class TestTouchstoneImport:
    """Test Touchstone import functionality."""

    @pytest.mark.integration
    def test_import_exported_file(self, sample_frequencies, sample_sparameters) -> None:
        """Test importing a file that was just exported."""
        exporter = TouchstoneExporter()

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = exporter.export(
                sample_frequencies, sample_sparameters, tmpdir
            )

            imported_freqs, imported_sparams = TouchstoneExporter.import_file(
                output_path
            )

            assert len(imported_freqs) == len(sample_frequencies)
            np.testing.assert_allclose(imported_freqs, sample_frequencies, rtol=1e-5)

            for param in ["S11", "S21", "S12", "S22"]:
                assert param in imported_sparams
                orig_mag, orig_phase = sample_sparameters[param]
                imp_mag, imp_phase = imported_sparams[param]

                np.testing.assert_allclose(imp_mag, orig_mag, rtol=1e-4, atol=1e-6)
                np.testing.assert_allclose(imp_phase, orig_phase, rtol=1e-4, atol=1e-6)

    @pytest.mark.unit
    def test_import_nonexistent_file(self) -> None:
        """Test importing nonexistent file raises error."""
        with pytest.raises(FileNotFoundError):
            TouchstoneExporter.import_file("/nonexistent/path/file.s2p")

    @pytest.mark.integration
    def test_import_empty_file(self) -> None:
        """Test importing empty file raises error."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".s2p", delete=False, encoding="utf-8"
        ) as f:
            temp_path = f.name
            f.write("# MHz S DB R 50\n")

        try:
            with pytest.raises(ValueError, match="No valid data"):
                TouchstoneExporter.import_file(temp_path)
        finally:
            os.unlink(temp_path)

    @pytest.mark.integration
    def test_import_with_comments(self, sample_frequencies, sample_sparameters) -> None:
        """Test that import handles comment lines correctly."""
        exporter = TouchstoneExporter()

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = exporter.export(
                sample_frequencies, sample_sparameters, tmpdir
            )

            imported_freqs, imported_sparams = TouchstoneExporter.import_file(
                output_path
            )

            assert len(imported_freqs) > 0
            assert len(imported_sparams) > 0

    @pytest.mark.integration
    def test_import_different_freq_units(
        self, sample_frequencies, sample_sparameters
    ) -> None:
        """Test importing files with different frequency units."""
        units = ["Hz", "kHz", "MHz", "GHz"]

        for unit in units:
            exporter = TouchstoneExporter(freq_unit=unit)

            with tempfile.TemporaryDirectory() as tmpdir:
                output_path = exporter.export(
                    sample_frequencies, sample_sparameters, tmpdir
                )

                imported_freqs, _ = TouchstoneExporter.import_file(output_path)

                np.testing.assert_allclose(
                    imported_freqs, sample_frequencies, rtol=1e-5
                )

    @pytest.mark.integration
    def test_roundtrip_preserves_data(
        self, sample_frequencies, sample_sparameters
    ) -> None:
        """Test that export->import preserves data integrity."""
        exporter = TouchstoneExporter()

        with tempfile.TemporaryDirectory() as tmpdir:
            path1 = exporter.export(sample_frequencies, sample_sparameters, tmpdir)
            freqs1, sparams1 = TouchstoneExporter.import_file(path1)
            path2 = exporter.export(freqs1, sparams1, tmpdir, filename="roundtrip.s2p")
            freqs2, sparams2 = TouchstoneExporter.import_file(path2)

            np.testing.assert_allclose(freqs1, freqs2, rtol=1e-10)

            for param in sparams1:
                np.testing.assert_allclose(
                    sparams1[param][0], sparams2[param][0], rtol=1e-10
                )
                np.testing.assert_allclose(
                    sparams1[param][1], sparams2[param][1], rtol=1e-10
                )

    @pytest.mark.integration
    def test_import_with_metadata_returns_structured_result(
        self, sample_frequencies, sample_sparameters
    ) -> None:
        """Test metadata-aware import returns the structured result type."""
        exporter = TouchstoneExporter()

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = exporter.export(
                sample_frequencies,
                sample_sparameters,
                tmpdir,
                filename="structured.s2p",
                notes_markdown="hello",
                metadata={"setup": {"host": "lab-vna"}},
            )

            result = TouchstoneExporter.import_with_metadata(output_path)

        assert isinstance(result, TouchstoneImportResult)
        assert isinstance(result.metadata, TouchstoneMetadata)
        np.testing.assert_allclose(result.frequencies_hz, sample_frequencies, rtol=1e-5)
        assert "S11" in result.s_parameters

    @pytest.mark.integration
    def test_import_with_metadata_parses_notes_and_machine_settings(
        self, sample_frequencies, sample_sparameters
    ) -> None:
        """Test metadata-aware import extracts both notes and YAML settings."""
        exporter = TouchstoneExporter()
        notes = "# Notes\nMeasured after warm-up."
        metadata = {
            "setup": {
                "host": "192.168.1.50",
                "port": "inst0",
            },
            "measurement": {
                "plot_type": "phase",
            },
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = exporter.export(
                sample_frequencies,
                sample_sparameters,
                tmpdir,
                filename="import_metadata.s2p",
                notes_markdown=notes,
                metadata=metadata,
            )

            result = TouchstoneExporter.import_with_metadata(output_path)

        assert result.metadata.notes_markdown == notes
        assert result.metadata.metadata_version == 1
        assert result.metadata.machine_settings is not None
        assert result.metadata.machine_settings["setup"]["host"] == "192.168.1.50"
        assert result.metadata.machine_settings["measurement"]["plot_type"] == "phase"

    @pytest.mark.integration
    def test_import_with_metadata_handles_legacy_file_without_metadata(
        self, sample_frequencies, sample_sparameters
    ) -> None:
        """Test metadata-aware import remains compatible with plain Touchstone files."""
        exporter = TouchstoneExporter()

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = exporter.export(
                sample_frequencies,
                sample_sparameters,
                tmpdir,
                filename="legacy.s2p",
            )

            result = TouchstoneExporter.import_with_metadata(output_path)

        assert result.metadata.notes_markdown == ""
        assert result.metadata.machine_settings is None
        assert result.metadata.metadata_version is None

    @pytest.mark.unit
    def test_parse_metadata_from_text_extracts_notes_and_yaml(self) -> None:
        """Test direct metadata parsing from Touchstone text."""
        text = "\n".join(
            [
                "! HP E5071B S-Parameter Data",
                "! TINA NOTES BEGIN",
                "! Raw markdown notes below. You may edit these manually.",
                "! # Heading",
                "! line two",
                "! TINA NOTES END",
                "# MHz S DB R 50",
                "1.000000  -10.000000  5.000000",
                "2.000000  -11.000000  6.000000",
                "!",
                "! TINA METADATA BEGIN",
                "! Machine-readable settings for TINA import/recovery.",
                "! You may edit the markdown notes block manually, but avoid changing",
                "! this machine settings block if reliable re-import is desired.",
                "! metadata_version: 1",
                "! setup:",
                "!   host: lab-vna",
                "!   port: inst0",
                "! TINA METADATA END",
            ]
        )

        metadata = TouchstoneExporter.parse_metadata_from_text(text)

        assert metadata.notes_markdown == "# Heading\nline two"
        assert metadata.metadata_version == 1
        assert metadata.machine_settings is not None
        assert metadata.machine_settings["setup"]["host"] == "lab-vna"
        assert metadata.machine_settings["setup"]["port"] == "inst0"

    @pytest.mark.unit
    def test_parse_metadata_from_text_returns_empty_metadata_when_missing(self) -> None:
        """Test direct metadata parsing on plain Touchstone text."""
        text = "\n".join(
            [
                "! HP E5071B S-Parameter Data",
                "# MHz S DB R 50",
                "1.000000  -10.000000  5.000000",
            ]
        )

        metadata = TouchstoneExporter.parse_metadata_from_text(text)

        assert metadata.notes_markdown == ""
        assert metadata.machine_settings is None
        assert metadata.metadata_version is None

    @pytest.mark.unit
    def test_parse_metadata_from_text_ignores_invalid_yaml(self) -> None:
        """Test invalid metadata YAML is ignored instead of crashing parsing."""
        text = "\n".join(
            [
                "! HP E5071B S-Parameter Data",
                "# MHz S DB R 50",
                "1.000000  -10.000000  5.000000",
                "!",
                "! TINA METADATA BEGIN",
                "! metadata_version: [unterminated",
                "! TINA METADATA END",
            ]
        )

        metadata = TouchstoneExporter.parse_metadata_from_text(text)

        assert metadata.machine_settings is None
        assert metadata.metadata_version is None


class TestTouchstoneFormat:
    """Test Touchstone file format compliance."""

    @pytest.mark.integration
    def test_file_format_has_option_line(
        self, sample_frequencies, sample_sparameters
    ) -> None:
        """Test that exported file has proper option line."""
        exporter = TouchstoneExporter()

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = exporter.export(
                sample_frequencies, sample_sparameters, tmpdir
            )

            with open(output_path, encoding="utf-8") as f:
                content = f.read()
                assert "# MHz S DB R 50" in content

    @pytest.mark.integration
    def test_file_format_has_comments(
        self, sample_frequencies, sample_sparameters
    ) -> None:
        """Test that exported file has descriptive comments."""
        exporter = TouchstoneExporter()

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = exporter.export(
                sample_frequencies, sample_sparameters, tmpdir
            )

            with open(output_path, encoding="utf-8") as f:
                lines = f.readlines()

            comment_lines = [line for line in lines if line.startswith("!")]
            assert len(comment_lines) > 0

            content = "".join(lines)
            assert "Date:" in content
            assert "Frequency Range:" in content
            assert "Points:" in content

    @pytest.mark.integration
    def test_file_format_data_columns(
        self, sample_frequencies, sample_sparameters
    ) -> None:
        """Test that data lines have correct number of columns."""
        exporter = TouchstoneExporter()

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = exporter.export(
                sample_frequencies, sample_sparameters, tmpdir
            )

            with open(output_path, encoding="utf-8") as f:
                lines = f.readlines()

            data_lines = [
                line
                for line in lines
                if line.strip() and not line.startswith(("!", "#"))
            ]

            assert len(data_lines) > 0

            first_data = data_lines[0].split()
            assert len(first_data) == 9
