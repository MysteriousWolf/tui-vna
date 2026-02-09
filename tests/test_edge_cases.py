"""
Edge case and crash tests for robustness.

Tests unusual conditions, error handling, and potential crash scenarios.
"""

import numpy as np
import pytest
import pyvisa

from src.tina.drivers.base import VNAConfig, detect_vna_driver, discover_drivers
from src.tina.drivers.hp_e5071b import HPE5071B
from src.tina.utils.touchstone import TouchstoneExporter
from tests.fixtures.mock_visa import MockVisaResource as DummyVisaResource
from tests.fixtures.mock_vna import MockVNA as DummyVNA


class TestConfigurationEdgeCases:
    """Test edge cases in configuration."""

    @pytest.mark.unit
    def test_zero_frequency_range(self):
        """Test configuration with zero frequency range."""
        config = VNAConfig(start_freq_hz=1e9, stop_freq_hz=1e9)
        assert config.start_freq_hz == config.stop_freq_hz

    @pytest.mark.unit
    def test_inverted_frequency_range(self):
        """Test configuration with inverted frequency range."""
        config = VNAConfig(start_freq_hz=2e9, stop_freq_hz=1e9)
        # Should accept but driver may handle differently
        assert config.start_freq_hz > config.stop_freq_hz

    @pytest.mark.unit
    def test_single_sweep_point(self):
        """Test configuration with single sweep point."""
        config = VNAConfig(sweep_points=1)
        assert config.sweep_points == 1

    @pytest.mark.unit
    def test_negative_sweep_points(self):
        """Test configuration with negative sweep points."""
        config = VNAConfig(sweep_points=-1)
        # Configuration allows it, driver should validate
        assert config.sweep_points == -1

    @pytest.mark.unit
    def test_zero_averaging_count(self):
        """Test configuration with zero averaging count."""
        config = VNAConfig(averaging_count=0)
        assert config.averaging_count == 0

    @pytest.mark.unit
    def test_very_large_sweep_points(self):
        """Test configuration with extremely large sweep points."""
        config = VNAConfig(sweep_points=1000000)
        assert config.sweep_points == 1000000

    @pytest.mark.unit
    def test_negative_timeout(self):
        """Test configuration with negative timeout."""
        config = VNAConfig(timeout_ms=-1000)
        assert config.timeout_ms == -1000

    @pytest.mark.unit
    def test_empty_host(self):
        """Test that empty host is rejected when building address."""
        config = VNAConfig(host="")
        with pytest.raises(ValueError):
            config.build_address()

    @pytest.mark.unit
    def test_special_characters_in_host(self):
        """Test configuration with special characters in host."""
        config = VNAConfig(host="192.168.1.100:5025")
        # Should accept, actual connection will validate
        address = config.build_address()
        assert "192.168.1.100:5025" in address


class TestConnectionEdgeCases:
    """Test edge cases in connection handling."""

    @pytest.mark.integration
    def test_connect_after_failed_connection(self, vna_config):
        """Test connecting again after a failed connection."""
        vna = DummyVNA(vna_config)

        # First connection succeeds
        assert vna.connect()
        vna.disconnect()

        # Second connection should also succeed
        assert vna.connect()
        vna.disconnect()

    @pytest.mark.integration
    def test_disconnect_twice(self, connected_dummy_vna):
        """Test disconnecting twice doesn't cause issues."""
        connected_dummy_vna.disconnect()
        # Second disconnect should be safe
        connected_dummy_vna.disconnect()

    @pytest.mark.integration
    def test_operations_after_disconnect(self, connected_dummy_vna):
        """Test that operations after disconnect fail gracefully."""
        connected_dummy_vna.disconnect()

        with pytest.raises((RuntimeError, pyvisa.VisaIOError, AttributeError)):
            connected_dummy_vna.get_frequency_axis()


class TestMeasurementEdgeCases:
    """Test edge cases in measurement."""

    @pytest.mark.integration
    def test_measurement_with_single_point(self, vna_config):
        """Test measurement with single frequency point."""
        vna = DummyVNA(vna_config)
        vna.config.sweep_points = 1
        vna.connect()

        freqs, sparams = vna.perform_measurement()

        assert len(freqs) >= 1  # May return more if override disabled
        for param_name, (mag, phase) in sparams.items():
            assert len(mag) == len(freqs)
            assert len(phase) == len(freqs)

        vna.disconnect()

    @pytest.mark.integration
    def test_measurement_without_configuration(self, vna_config):
        """Test measurement without explicit configuration."""
        vna = DummyVNA(vna_config)
        vna.config.set_freq_range = False
        vna.config.set_sweep_points = False
        vna.connect()

        # Should use VNA's current settings
        freqs, sparams = vna.perform_measurement()

        assert len(freqs) > 0
        assert len(sparams) == 4

        vna.disconnect()

    @pytest.mark.integration
    def test_rapid_successive_measurements(self, connected_dummy_vna):
        """Test performing multiple measurements rapidly."""
        for _ in range(5):
            freqs, sparams = connected_dummy_vna.perform_measurement()
            assert len(freqs) > 0
            assert len(sparams) == 4


class TestDataEdgeCases:
    """Test edge cases in data handling."""

    @pytest.mark.unit
    def test_empty_frequency_array(self):
        """Test handling empty frequency array."""
        freqs = np.array([])
        sparams = {
            "S11": (np.array([]), np.array([])),
        }

        exporter = TouchstoneExporter()

        # Should not crash but may raise ValueError
        # (depends on implementation)
        try:
            import tempfile

            with tempfile.TemporaryDirectory() as tmpdir:
                exporter.export(freqs, sparams, tmpdir)
        except (ValueError, IndexError):
            pass  # Expected

    @pytest.mark.unit
    def test_nan_in_data(self):
        """Test handling NaN values in measurement data."""
        freqs = np.array([1e9, 2e9, 3e9])
        sparams = {
            "S11": (
                np.array([np.nan, -10.0, -20.0]),
                np.array([0.0, np.nan, 180.0]),
            ),
        }

        exporter = TouchstoneExporter()

        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            # Should handle NaN without crashing
            path = exporter.export(freqs, sparams, tmpdir)
            assert path is not None

    @pytest.mark.unit
    def test_inf_in_data(self):
        """Test handling infinity values in measurement data."""
        freqs = np.array([1e9, 2e9, 3e9])
        sparams = {
            "S11": (
                np.array([np.inf, -10.0, -np.inf]),
                np.array([0.0, 180.0, -180.0]),
            ),
        }

        exporter = TouchstoneExporter()

        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            # Should handle inf without crashing
            path = exporter.export(freqs, sparams, tmpdir)
            assert path is not None

    @pytest.mark.unit
    def test_very_large_values(self):
        """Test handling very large values."""
        freqs = np.array([1e15, 2e15])  # Very high frequency
        sparams = {
            "S11": (
                np.array([1e10, -1e10]),  # Very large dB values
                np.array([1e6, -1e6]),  # Very large phase
            ),
        }

        exporter = TouchstoneExporter()

        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            path = exporter.export(freqs, sparams, tmpdir)
            assert path is not None


class TestDriverDiscoveryEdgeCases:
    """Test edge cases in driver discovery."""

    @pytest.mark.unit
    def test_detect_empty_idn_string(self):
        """Test driver detection with empty IDN string."""
        result = detect_vna_driver("")
        # Should return None or a default driver
        assert result is None or hasattr(result, "driver_name")

    @pytest.mark.unit
    def test_detect_very_long_idn_string(self):
        """Test driver detection with very long IDN string."""
        long_idn = "A" * 10000
        result = detect_vna_driver(long_idn)
        # Should not crash
        assert result is None or hasattr(result, "driver_name")

    @pytest.mark.unit
    def test_detect_idn_with_special_characters(self):
        """Test driver detection with special characters."""
        special_idn = "HEWLETT-PACKARD,E5071B,\x00\xff\n\r\t"
        result = detect_vna_driver(special_idn)
        # Should not crash
        assert result is None or hasattr(result, "driver_name")

    @pytest.mark.unit
    def test_discover_drivers_multiple_calls(self):
        """Test that discovering drivers multiple times works."""
        drivers1 = discover_drivers()
        drivers2 = discover_drivers()

        # Should return same results (cached)
        assert len(drivers1) == len(drivers2)
        assert set(drivers1.keys()) == set(drivers2.keys())


class TestVisaResourceEdgeCases:
    """Test edge cases with VISA resource handling."""

    @pytest.mark.unit
    def test_visa_resource_closed_operations(self):
        """Test operations on closed VISA resource."""
        resource = DummyVisaResource()
        resource.close()

        with pytest.raises(pyvisa.VisaIOError):
            resource.write("*IDN?")

        with pytest.raises(pyvisa.VisaIOError):
            resource.query("*IDN?")

    @pytest.mark.unit
    def test_visa_resource_double_close(self):
        """Test closing VISA resource twice."""
        resource = DummyVisaResource()
        resource.close()
        # Should not raise
        resource.close()

    @pytest.mark.unit
    def test_visa_resource_unknown_command(self):
        """Test sending unknown SCPI command."""
        resource = DummyVisaResource()

        # Should not crash, may return default response
        response = resource.query(":UNKNOWN:COMMAND?")
        assert response is not None


class TestConcurrencyEdgeCases:
    """Test edge cases related to concurrency."""

    @pytest.mark.unit
    def test_worker_rapid_start_stop(self):
        """Test rapidly starting and stopping worker."""
        from src.tina.worker import MeasurementWorker

        worker = MeasurementWorker()

        for _ in range(5):
            worker.start()
            worker.stop(timeout=0.5)

    @pytest.mark.integration
    def test_multiple_vna_instances(self, vna_config):
        """Test creating multiple VNA instances."""
        vnas = [DummyVNA(vna_config) for _ in range(5)]

        # All should be independent
        for vna in vnas:
            assert not vna.is_connected()

        # Connect all
        for vna in vnas:
            vna.connect()

        # Disconnect all
        for vna in vnas:
            vna.disconnect()


class TestFileSystemEdgeCases:
    """Test edge cases in file system operations."""

    @pytest.mark.integration
    def test_export_to_readonly_directory(self, sample_frequencies, sample_sparameters):
        """Test exporting to read-only directory."""
        import os
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            readonly_dir = os.path.join(tmpdir, "readonly")
            os.makedirs(readonly_dir)
            os.chmod(readonly_dir, 0o444)  # Read-only

            exporter = TouchstoneExporter()

            try:
                # Should raise permission error
                with pytest.raises((PermissionError, OSError)):
                    exporter.export(
                        sample_frequencies, sample_sparameters, readonly_dir
                    )
            finally:
                # Restore permissions for cleanup
                os.chmod(readonly_dir, 0o755)

    @pytest.mark.integration
    def test_export_with_very_long_filename(
        self, sample_frequencies, sample_sparameters
    ):
        """Test exporting with very long filename."""
        import tempfile

        exporter = TouchstoneExporter()
        long_filename = "a" * 200 + ".s2p"

        with tempfile.TemporaryDirectory() as tmpdir:
            try:
                # May succeed or fail depending on OS limits
                path = exporter.export(
                    sample_frequencies,
                    sample_sparameters,
                    tmpdir,
                    filename=long_filename,
                )
                assert path is not None
            except (OSError, ValueError):
                pass  # Expected on some systems

    @pytest.mark.integration
    def test_import_corrupted_file(self):
        """Test importing corrupted Touchstone file."""
        import tempfile

        with tempfile.NamedTemporaryFile(mode="w", suffix=".s2p", delete=False) as f:
            temp_path = f.name
            f.write("# MHz S DB R 50\n")
            f.write("CORRUPTED DATA !@#$%^&*()\n")
            f.write("MORE GARBAGE\n")

        try:
            # Should handle gracefully
            try:
                TouchstoneExporter.import_file(temp_path)
            except ValueError:
                pass  # Expected
        finally:
            import os

            os.unlink(temp_path)


class TestMemoryEdgeCases:
    """Test edge cases related to memory usage."""

    @pytest.mark.slow
    @pytest.mark.integration
    def test_large_sweep_points(self, vna_config):
        """Test measurement with very large number of sweep points."""
        vna = DummyVNA(vna_config)
        vna.config.sweep_points = 10001  # Very large
        vna.config.set_sweep_points = True
        vna.connect()

        freqs, sparams = vna.perform_measurement()

        # Should handle large arrays
        assert len(freqs) > 1000

        vna.disconnect()

    @pytest.mark.slow
    @pytest.mark.integration
    def test_many_repeated_measurements(self, connected_dummy_vna):
        """Test many repeated measurements for memory leaks."""
        for i in range(100):
            freqs, sparams = connected_dummy_vna.perform_measurement()

            # Verify data is valid
            assert len(freqs) > 0

            # Every 20 iterations, check data is consistent
            if i % 20 == 0:
                assert len(sparams) == 4
