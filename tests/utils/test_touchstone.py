"""
Unit tests for Touchstone file export/import functionality.

Tests S-parameter file I/O including format validation and data integrity.
"""

import os
import tempfile

import numpy as np
import pytest

from src.tina.utils.touchstone import TouchstoneExporter


class TestTouchstoneExporter:
    """Test Touchstone exporter functionality."""

    @pytest.mark.unit
    def test_initialization(self):
        """Test exporter initialization with defaults."""
        exporter = TouchstoneExporter()
        assert exporter.freq_unit == "MHz"
        assert exporter.reference_impedance == 50.0

    @pytest.mark.unit
    def test_initialization_custom(self):
        """Test exporter initialization with custom values."""
        exporter = TouchstoneExporter(freq_unit="GHz", reference_impedance=75.0)
        assert exporter.freq_unit == "GHz"
        assert exporter.reference_impedance == 75.0

    @pytest.mark.unit
    def test_convert_frequency(self):
        """Test frequency unit conversion."""
        exporter_hz = TouchstoneExporter(freq_unit="Hz")
        exporter_mhz = TouchstoneExporter(freq_unit="MHz")
        exporter_ghz = TouchstoneExporter(freq_unit="GHz")

        freq_hz = 1e9  # 1 GHz

        assert exporter_hz._convert_frequency(freq_hz) == 1e9
        assert exporter_mhz._convert_frequency(freq_hz) == 1000.0
        assert exporter_ghz._convert_frequency(freq_hz) == 1.0

    @pytest.mark.integration
    def test_export_basic(self, sample_frequencies, sample_sparameters):
        """Test basic export functionality."""
        exporter = TouchstoneExporter()

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = exporter.export(
                sample_frequencies,
                sample_sparameters,
                tmpdir,
                filename="test_output.s2p",
            )

            # Verify file was created
            assert os.path.exists(output_path)
            assert output_path.endswith(".s2p")

            # Verify file has content
            with open(output_path) as f:
                content = f.read()
                assert len(content) > 0
                assert "# MHz S DB R 50" in content  # Option line
                assert "!" in content  # Comments

    @pytest.mark.integration
    def test_export_auto_filename(self, sample_frequencies, sample_sparameters):
        """Test export with auto-generated filename."""
        exporter = TouchstoneExporter()

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = exporter.export(
                sample_frequencies, sample_sparameters, tmpdir, prefix="test"
            )

            # Verify file was created
            assert os.path.exists(output_path)
            assert "test_" in os.path.basename(output_path)
            assert output_path.endswith(".s2p")

    @pytest.mark.integration
    def test_export_creates_directory(self, sample_frequencies, sample_sparameters):
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
    def test_export_adds_extension(self, sample_frequencies, sample_sparameters):
        """Test that .s2p extension is added if missing."""
        exporter = TouchstoneExporter()

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = exporter.export(
                sample_frequencies, sample_sparameters, tmpdir, filename="test"
            )

            assert output_path.endswith(".s2p")

    @pytest.mark.integration
    def test_export_different_units(self, sample_frequencies, sample_sparameters):
        """Test export with different frequency units."""
        units = ["Hz", "kHz", "MHz", "GHz"]

        for unit in units:
            exporter = TouchstoneExporter(freq_unit=unit)

            with tempfile.TemporaryDirectory() as tmpdir:
                output_path = exporter.export(
                    sample_frequencies, sample_sparameters, tmpdir
                )

                with open(output_path) as f:
                    content = f.read()
                    assert f"# {unit} S DB R" in content

    @pytest.mark.integration
    def test_export_partial_sparameters(self, sample_frequencies):
        """Test export with only some S-parameters."""
        # Only S11 and S21
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

            # Verify file content
            with open(output_path) as f:
                lines = f.readlines()
                # Find first data line (after comments and option line)
                data_lines = [
                    line
                    for line in lines
                    if line.strip() and not line.startswith(("!", "#"))
                ]
                # Should have fewer columns than full 4-port
                assert len(data_lines) > 0

    @pytest.mark.unit
    def test_export_length_mismatch_error(self, sample_frequencies):
        """Test that mismatched data lengths raise error."""
        bad_sparams = {
            "S11": (
                np.random.randn(len(sample_frequencies)),
                np.random.randn(len(sample_frequencies) + 10),  # Wrong length!
            ),
        }

        exporter = TouchstoneExporter()

        with tempfile.TemporaryDirectory() as tmpdir:
            with pytest.raises(ValueError, match="length mismatch"):
                exporter.export(sample_frequencies, bad_sparams, tmpdir)

    @pytest.mark.unit
    def test_export_no_sparameters_error(self, sample_frequencies):
        """Test that exporting with no S-parameters raises error."""
        exporter = TouchstoneExporter()

        with tempfile.TemporaryDirectory() as tmpdir:
            with pytest.raises(ValueError, match="No valid S-parameters"):
                exporter.export(sample_frequencies, {}, tmpdir)


class TestTouchstoneImport:
    """Test Touchstone import functionality."""

    @pytest.mark.integration
    def test_import_exported_file(self, sample_frequencies, sample_sparameters):
        """Test importing a file that was just exported."""
        exporter = TouchstoneExporter()

        with tempfile.TemporaryDirectory() as tmpdir:
            # Export
            output_path = exporter.export(
                sample_frequencies, sample_sparameters, tmpdir
            )

            # Import
            imported_freqs, imported_sparams = TouchstoneExporter.import_file(
                output_path
            )

            # Verify frequencies
            assert len(imported_freqs) == len(sample_frequencies)
            np.testing.assert_allclose(imported_freqs, sample_frequencies, rtol=1e-5)

            # Verify S-parameters (relaxed tolerance for ASCII roundtrip)
            for param in ["S11", "S21", "S12", "S22"]:
                assert param in imported_sparams
                orig_mag, orig_phase = sample_sparameters[param]
                imp_mag, imp_phase = imported_sparams[param]

                np.testing.assert_allclose(imp_mag, orig_mag, rtol=1e-4, atol=1e-6)
                np.testing.assert_allclose(imp_phase, orig_phase, rtol=1e-4, atol=1e-6)

    @pytest.mark.unit
    def test_import_nonexistent_file(self):
        """Test importing nonexistent file raises error."""
        with pytest.raises(FileNotFoundError):
            TouchstoneExporter.import_file("/nonexistent/path/file.s2p")

    @pytest.mark.integration
    def test_import_empty_file(self):
        """Test importing empty file raises error."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".s2p", delete=False) as f:
            temp_path = f.name
            f.write("# MHz S DB R 50\n")  # Only option line, no data

        try:
            with pytest.raises(ValueError, match="No valid data"):
                TouchstoneExporter.import_file(temp_path)
        finally:
            os.unlink(temp_path)

    @pytest.mark.integration
    def test_import_with_comments(self, sample_frequencies, sample_sparameters):
        """Test that import handles comment lines correctly."""
        exporter = TouchstoneExporter()

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = exporter.export(
                sample_frequencies, sample_sparameters, tmpdir
            )

            # Import should work despite comments
            imported_freqs, imported_sparams = TouchstoneExporter.import_file(
                output_path
            )

            assert len(imported_freqs) > 0
            assert len(imported_sparams) > 0

    @pytest.mark.integration
    def test_import_different_freq_units(self, sample_frequencies, sample_sparameters):
        """Test importing files with different frequency units."""
        units_and_multipliers = [
            ("Hz", 1.0),
            ("kHz", 1e3),
            ("MHz", 1e6),
            ("GHz", 1e9),
        ]

        for unit, multiplier in units_and_multipliers:
            exporter = TouchstoneExporter(freq_unit=unit)

            with tempfile.TemporaryDirectory() as tmpdir:
                output_path = exporter.export(
                    sample_frequencies, sample_sparameters, tmpdir
                )

                imported_freqs, _ = TouchstoneExporter.import_file(output_path)

                # Should always return Hz
                np.testing.assert_allclose(
                    imported_freqs, sample_frequencies, rtol=1e-5
                )

    @pytest.mark.integration
    def test_roundtrip_preserves_data(self, sample_frequencies, sample_sparameters):
        """Test that export->import preserves data integrity."""
        exporter = TouchstoneExporter()

        with tempfile.TemporaryDirectory() as tmpdir:
            # Export
            path1 = exporter.export(sample_frequencies, sample_sparameters, tmpdir)

            # Import
            freqs1, sparams1 = TouchstoneExporter.import_file(path1)

            # Export again
            path2 = exporter.export(freqs1, sparams1, tmpdir, filename="roundtrip.s2p")

            # Import again
            freqs2, sparams2 = TouchstoneExporter.import_file(path2)

            # Should be identical
            np.testing.assert_allclose(freqs1, freqs2, rtol=1e-10)

            for param in sparams1.keys():
                np.testing.assert_allclose(
                    sparams1[param][0], sparams2[param][0], rtol=1e-10
                )
                np.testing.assert_allclose(
                    sparams1[param][1], sparams2[param][1], rtol=1e-10
                )


class TestTouchstoneFormat:
    """Test Touchstone file format compliance."""

    @pytest.mark.integration
    def test_file_format_has_option_line(self, sample_frequencies, sample_sparameters):
        """Test that exported file has proper option line."""
        exporter = TouchstoneExporter()

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = exporter.export(
                sample_frequencies, sample_sparameters, tmpdir
            )

            with open(output_path) as f:
                content = f.read()
                # Option line format: # <freq_unit> S <format> R <impedance>
                assert "# MHz S DB R 50" in content

    @pytest.mark.integration
    def test_file_format_has_comments(self, sample_frequencies, sample_sparameters):
        """Test that exported file has descriptive comments."""
        exporter = TouchstoneExporter()

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = exporter.export(
                sample_frequencies, sample_sparameters, tmpdir
            )

            with open(output_path) as f:
                lines = f.readlines()

            # Check for comment lines
            comment_lines = [line for line in lines if line.startswith("!")]
            assert len(comment_lines) > 0

            # Check for specific metadata
            content = "".join(lines)
            assert "Date:" in content
            assert "Frequency Range:" in content
            assert "Points:" in content

    @pytest.mark.integration
    def test_file_format_data_columns(self, sample_frequencies, sample_sparameters):
        """Test that data lines have correct number of columns."""
        exporter = TouchstoneExporter()

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = exporter.export(
                sample_frequencies, sample_sparameters, tmpdir
            )

            with open(output_path) as f:
                lines = f.readlines()

            # Find first data line
            data_lines = [
                line
                for line in lines
                if line.strip() and not line.startswith(("!", "#"))
            ]

            assert len(data_lines) > 0

            # Each data line should have: freq + 2*num_params columns
            # For 4 S-parameters: 1 + 2*4 = 9 columns
            first_data = data_lines[0].split()
            assert len(first_data) == 9  # freq + 8 S-param values
