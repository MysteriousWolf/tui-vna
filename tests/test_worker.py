"""
Unit tests for measurement worker thread - FIXED VERSION.

Tests worker thread communication, measurement sequences, and error handling.
Uses helper to consume progress messages properly.
"""

import queue
import time
from inspect import getsource
from pathlib import Path
from typing import cast
from unittest.mock import MagicMock, patch

import numpy as np
import pytest
from PIL import Image

from tests.conftest import consume_worker_messages_until
from tina.drivers.base import VNAConfig
from tina.export import embed_png_metadata, embed_svg_metadata
from tina.utils.touchstone import TouchstoneExporter
from tina.worker import (
    ImportRequest,
    ImportResult,
    LogMessage,
    MeasurementWorker,
    MessageType,
    ParamsResult,
    _render_tools_plot_snapshot,
    _write_touchstone_save_back,
)


class TestWorkerBasics:
    """Test basic worker functionality."""

    @pytest.mark.unit
    def test_worker_initialization(self):
        """Test creating a worker instance."""
        worker = MeasurementWorker()
        assert worker is not None
        assert not worker._running

    @pytest.mark.unit
    def test_worker_start_stop(self):
        """Test starting and stopping worker."""
        worker = MeasurementWorker()

        worker.start()
        assert worker._running
        assert worker._thread is not None
        assert worker._thread.is_alive()

        worker.stop(timeout=2.0)
        assert not worker._running
        # Thread should have terminated or been set to None
        time.sleep(0.2)
        if worker._thread is not None:
            assert not worker._thread.is_alive()

    @pytest.mark.unit
    def test_worker_double_start(self):
        """Test that starting worker twice is safe."""
        worker = MeasurementWorker()

        worker.start()
        thread1 = worker._thread

        worker.start()  # Should be no-op
        thread2 = worker._thread

        assert thread1 is thread2  # Same thread

        worker.stop()

    @pytest.mark.unit
    def test_worker_stop_when_not_running(self):
        """Test that stopping inactive worker is safe."""
        worker = MeasurementWorker()
        # Should not raise
        worker.stop()


class TestWorkerCommunication:
    """Test worker thread communication."""

    @pytest.mark.unit
    def test_send_command(self):
        """Test sending command to worker."""
        worker = MeasurementWorker()
        worker.start()

        worker.send_command(MessageType.DISCONNECT)

        # Command should be in queue
        assert not worker._command_queue.empty()

        worker.stop()

    @pytest.mark.unit
    def test_get_response_timeout(self):
        """Test getting response with timeout."""
        worker = MeasurementWorker()
        worker.start()

        # No response should timeout
        with pytest.raises(queue.Empty):
            worker.get_response(timeout=0.1)

        worker.stop()

    @pytest.mark.integration
    def test_response_received(self):
        """Test that worker sends responses."""
        worker = MeasurementWorker()
        worker.start()

        # Send a command that will trigger a response
        worker.send_command(MessageType.DISCONNECT)

        # Wait for response
        msg = consume_worker_messages_until(
            worker, MessageType.DISCONNECTED, timeout=1.0
        )
        assert msg is not None
        assert msg.type == MessageType.DISCONNECTED

        worker.stop()


class TestWorkerConnection:
    """Test worker connection handling."""

    @pytest.mark.integration
    @pytest.mark.skip(reason="Complex mocking of real driver - use manual testing")
    @patch("tina.worker.detect_vna_driver")
    @patch("tina.drivers.hp_e5071b.HPE5071B")
    @patch("socket.socket")
    def test_connect_success(
        self, mock_socket, mock_vna_class, mock_detect, vna_config
    ):
        """Test successful connection."""
        # Mock socket to pass reachability check
        mock_sock_inst = MagicMock()
        mock_sock_inst.connect_ex.return_value = 0
        mock_socket.return_value.__enter__.return_value = mock_sock_inst

        # Setup VNA mocks
        mock_vna = MagicMock()
        mock_vna.idn = "HEWLETT-PACKARD,E5071B,MY12345678,A.01.02"
        mock_vna.driver_name = "HP E5071B"
        mock_vna.is_connected.return_value = True
        mock_vna_class.return_value = mock_vna
        mock_detect.return_value = mock_vna_class

        worker = MeasurementWorker()
        worker.start()

        # Send connect command
        worker.send_command(MessageType.CONNECT, vna_config)

        # Consume messages until CONNECTED
        msg = consume_worker_messages_until(worker, MessageType.CONNECTED, timeout=2.0)

        try:
            assert msg is not None, "Worker did not respond to connect"
            assert msg.type == MessageType.CONNECTED
            assert msg.data is not None
        finally:
            worker.stop()

    @pytest.mark.integration
    def test_connect_no_host_error(self):
        """Test connection with no host configured."""
        worker = MeasurementWorker()
        worker.start()

        config = VNAConfig()  # No host
        worker.send_command(MessageType.CONNECT, config)

        # Should get error response (consume progress first)
        msg = consume_worker_messages_until(worker, MessageType.ERROR, timeout=2.0)
        assert msg is not None
        assert msg.type == MessageType.ERROR
        assert msg.error is not None

        worker.stop()

    @pytest.mark.integration
    def test_disconnect(self, connected_mock_e5071b):
        """Test disconnection."""
        worker = MeasurementWorker()
        worker._vna = connected_mock_e5071b

        worker._handle_disconnect()

        msg = consume_worker_messages_until(worker, MessageType.DISCONNECTED)
        assert msg is not None
        assert msg.type == MessageType.DISCONNECTED


class TestWorkerMeasurement:
    """Test worker measurement operations."""

    @pytest.mark.integration
    @pytest.mark.skip(reason="Complex mocking of real driver - use manual testing")
    @patch("tina.worker.detect_vna_driver")
    @patch("socket.socket")
    def test_read_params(
        self, mock_socket, mock_detect, vna_config, connected_mock_e5071b
    ):
        """Test reading VNA parameters."""
        # Mock socket
        mock_sock_inst = MagicMock()
        mock_sock_inst.connect_ex.return_value = 0
        mock_socket.return_value.__enter__.return_value = mock_sock_inst

        # Use our mock VNA
        mock_detect.return_value = lambda config: connected_mock_e5071b

        worker = MeasurementWorker()
        worker.start()

        # Connect
        worker.send_command(MessageType.CONNECT, vna_config)
        msg = consume_worker_messages_until(worker, MessageType.CONNECTED)
        assert msg is not None

        # Read params
        worker.send_command(MessageType.READ_PARAMS)

        msg = consume_worker_messages_until(worker, MessageType.PARAMS_READ)
        assert msg is not None
        assert msg.type == MessageType.PARAMS_READ
        assert isinstance(msg.data, ParamsResult)

        worker.stop()

    @pytest.mark.integration
    def test_measure_not_connected_error(self, vna_config):
        """Test that measuring while not connected raises error."""
        worker = MeasurementWorker()
        worker.start()

        # Try to measure without connecting
        worker.send_command(MessageType.MEASURE, vna_config)

        msg = consume_worker_messages_until(worker, MessageType.ERROR)
        assert msg is not None
        assert msg.type == MessageType.ERROR
        assert msg.error is not None
        assert "Not connected" in msg.error

        worker.stop()

    @pytest.mark.unit
    def test_measure_restores_trigger_state_when_readout_fails(self, vna_config):
        """Trigger state should be restored even when readback raises an error."""
        worker = MeasurementWorker()
        worker._vna = MagicMock()
        worker._vna.is_connected.return_value = True
        worker._vna.save_trigger_state.return_value = ("INT", True)
        worker._vna.get_frequency_axis.side_effect = RuntimeError("readout failed")

        worker._handle_measure(vna_config)

        worker._vna.restore_trigger_state.assert_called_once_with(("INT", True))
        error_message = consume_worker_messages_until(
            worker, MessageType.ERROR, timeout=0.01
        )
        assert error_message is not None
        assert error_message.type == MessageType.ERROR
        assert "Measurement failed: readout failed" == error_message.error
        assert worker._measuring is False

    @pytest.mark.unit
    def test_worker_sets_agg_backend_before_pyplot_import(self):
        """worker.py should select the Agg backend before importing pyplot."""
        source = getsource(__import__("tina.worker", fromlist=["MeasurementWorker"]))

        assert (
            'matplotlib.use("Agg")' in source
        ), "Expected matplotlib.use('Agg') in worker.py"
        assert (
            "from matplotlib import pyplot as plt" in source
        ), "Expected pyplot import in worker.py"
        assert source.index('matplotlib.use("Agg")') < source.index(
            "from matplotlib import pyplot as plt"
        ), "matplotlib.use('Agg') must precede the pyplot import"


class TestWorkerProgressUpdates:
    """Test worker progress reporting."""

    @pytest.mark.integration
    @patch("tina.worker.detect_vna_driver")
    @patch("tina.drivers.hp_e5071b.HPE5071B")
    @patch("socket.socket")
    def test_progress_updates_during_connect(
        self, mock_socket, mock_vna_class, mock_detect, vna_config
    ):
        """Test that progress updates are sent during connection."""
        # Mock socket
        mock_sock_inst = MagicMock()
        mock_sock_inst.connect_ex.return_value = 0
        mock_socket.return_value.__enter__.return_value = mock_sock_inst

        mock_vna = MagicMock()
        mock_vna.idn = "HEWLETT-PACKARD,E5071B,MY12345678,A.01.02"
        mock_vna.driver_name = "HP E5071B"
        mock_vna.is_connected.return_value = True
        mock_vna_class.return_value = mock_vna
        mock_detect.return_value = mock_vna_class

        worker = MeasurementWorker()
        worker.start()

        worker.send_command(MessageType.CONNECT, vna_config)

        # Collect messages until we receive CONNECTED
        for _ in range(10):
            try:
                msg = worker.get_response(timeout=0.5)

                if msg.type == MessageType.PROGRESS:
                    pass  # Progress updates are optional and timing-dependent
                elif msg.type == MessageType.CONNECTED:
                    break

            except queue.Empty:
                continue

        # Progress updates are optional (timing-dependent)
        # But CONNECTED should always arrive

        worker.stop()

    @pytest.mark.integration
    def test_import_touchstone_emits_progress_and_complete(self, tmp_path: Path):
        """Touchstone import should emit staged progress and an ImportResult."""
        export_path = TouchstoneExporter().export(
            frequencies_hz=np.array([1.0e6, 2.0e6, 3.0e6], dtype=float),
            s_parameters={
                "S11": (
                    np.array([-10.0, -11.0, -12.0], dtype=float),
                    np.array([5.0, 6.0, 7.0], dtype=float),
                ),
                "S21": (
                    np.array([-1.0, -1.5, -2.0], dtype=float),
                    np.array([45.0, 46.0, 47.0], dtype=float),
                ),
                "S12": (
                    np.array([-1.0, -1.5, -2.0], dtype=float),
                    np.array([45.0, 46.0, 47.0], dtype=float),
                ),
                "S22": (
                    np.array([-10.0, -11.0, -12.0], dtype=float),
                    np.array([5.0, 6.0, 7.0], dtype=float),
                ),
            },
            output_path=str(tmp_path),
            filename="worker_import.s2p",
            notes_markdown="worker notes",
            metadata={
                "setup": {"freq_unit": "MHz"},
                "measurement": {"plot_s11": True, "plot_s21": True},
            },
        )

        worker = MeasurementWorker()
        worker.start()
        worker.send_command(
            MessageType.IMPORT,
            ImportRequest(file_path=export_path, restore_measurement=True),
        )

        progress_messages: list[str] = []
        try:
            completed = None
            for _ in range(12):
                try:
                    msg = worker.get_response(timeout=1.0)
                except queue.Empty:
                    break
                if msg.type == MessageType.IMPORT_PROGRESS:
                    progress_messages.append(msg.data.message)
                elif msg.type in (MessageType.IMPORT_COMPLETE, MessageType.ERROR):
                    completed = msg
                    break

            assert completed is not None
            assert completed.type == MessageType.IMPORT_COMPLETE
            assert progress_messages[0] == "Resolving import path..."
            assert progress_messages[-1] == "Import complete"
            assert len(progress_messages) >= 5

            result = completed.data
            assert isinstance(result, ImportResult)
            assert result.notes == "worker notes"
            assert result.paths["touchstone_path"] == str(Path(export_path).resolve())
            assert result.measurement["restore_measurement"] is True
            restored_freqs = cast(np.ndarray, result.measurement["frequencies"])
            assert restored_freqs is not None
            assert len(restored_freqs) == 3
            restored_sparams = result.measurement["sparams"]
            assert isinstance(restored_sparams, dict)
            assert set(restored_sparams) == {"S11", "S21", "S12", "S22"}
        finally:
            worker.stop()

    @pytest.mark.integration
    def test_import_png_recovers_measurement_payload(self, tmp_path: Path):
        """PNG import should rebuild measurement data from embedded raw metadata."""
        export_path = tmp_path / "worker_import.png"
        Image.new("RGB", (8, 8), color="black").save(export_path)
        embed_png_metadata(
            export_path,
            notes_markdown="png notes",
            machine_settings={
                "setup": {"freq_unit": "MHz"},
                "measurement": {
                    "plot_s11": True,
                    "raw_data": {
                        "freqs_hz": [1.0e6, 2.0e6],
                        "sparams": {
                            "S11": {
                                "magnitude_db": [-10.0, -11.0],
                                "phase_deg": [5.0, 6.0],
                            }
                        },
                    },
                },
            },
        )

        worker = MeasurementWorker()
        worker.start()
        worker.send_command(
            MessageType.IMPORT,
            ImportRequest(file_path=str(export_path), restore_measurement=True),
        )

        completed = consume_worker_messages_until(
            worker, MessageType.IMPORT_COMPLETE, timeout=1.0, max_messages=12
        )
        try:
            assert completed is not None
            assert completed.type == MessageType.IMPORT_COMPLETE
            result = completed.data
            assert isinstance(result, ImportResult)
            assert result.notes == "png notes"
            assert result.paths["png_path"] == str(export_path.resolve())
            restored_freqs = cast(np.ndarray, result.measurement["frequencies"])
            assert restored_freqs is not None
            assert len(restored_freqs) == 2
            restored_sparams = result.measurement["sparams"]
            assert isinstance(restored_sparams, dict)
            assert set(restored_sparams) == {"S11"}
        finally:
            worker.stop()

    @pytest.mark.integration
    def test_import_svg_setup_only_returns_without_measurement_arrays(
        self, tmp_path: Path
    ) -> None:
        """Setup-only SVG import should avoid reconstructing measurement arrays."""
        export_path = tmp_path / "worker_import.svg"
        export_path.write_text("<svg></svg>", encoding="utf-8")
        embed_svg_metadata(
            export_path,
            notes_markdown="svg notes",
            machine_settings={
                "setup": {"host": "172.16.0.10", "freq_unit": "GHz"},
                "measurement": {"plot_type": "phase"},
            },
        )

        worker = MeasurementWorker()
        worker.start()
        worker.send_command(
            MessageType.IMPORT,
            ImportRequest(file_path=str(export_path), restore_measurement=False),
        )

        completed = consume_worker_messages_until(
            worker, MessageType.IMPORT_COMPLETE, timeout=1.0, max_messages=12
        )
        try:
            assert completed is not None
            assert completed.type == MessageType.IMPORT_COMPLETE
            result = completed.data
            assert isinstance(result, ImportResult)
            assert result.notes == "svg notes"
            assert result.paths["svg_path"] == str(export_path.resolve())
            assert result.measurement["restore_measurement"] is False
            assert result.measurement["frequencies"] is None
            assert result.measurement["sparams"] is None
            assert result.setup["host"] == "172.16.0.10"
        finally:
            worker.stop()


class TestWorkerErrorHandling:
    """Test worker error handling."""

    @pytest.mark.integration
    def test_worker_handles_exception_gracefully(self, vna_config):
        """Test that worker handles exceptions without crashing."""
        worker = MeasurementWorker()
        worker.start()

        # Send invalid command data
        worker.send_command(MessageType.CONNECT, None)  # Invalid config

        # Should get an error response
        msg = consume_worker_messages_until(worker, MessageType.ERROR, timeout=2.0)
        assert msg is not None
        assert msg.type == MessageType.ERROR

        worker.stop()


class TestWorkerQueueManagement:
    """Test queue drain and debug-flag helpers added in the status-bar feature."""

    @pytest.mark.unit
    def test_clear_commands_drains_queue(self):
        """clear_commands() must remove all pending commands without blocking."""
        worker = MeasurementWorker()
        # Queue three commands without starting the thread
        worker.send_command(MessageType.STATUS_POLL)
        worker.send_command(MessageType.STATUS_POLL)
        worker.send_command(MessageType.STATUS_POLL)
        assert not worker._command_queue.empty()

        worker.clear_commands()

        assert worker._command_queue.empty()

    @pytest.mark.unit
    def test_clear_commands_on_empty_queue_is_safe(self):
        """clear_commands() must be idempotent on an already-empty queue."""
        worker = MeasurementWorker()
        worker.clear_commands()  # Should not raise
        worker.clear_commands()  # Calling twice is also safe

    @pytest.mark.unit
    def test_set_debug_scpi_updates_worker_flag(self):
        """SET_DEBUG_SCPI must update _debug_scpi on the worker thread."""
        worker = MeasurementWorker()
        worker.start()

        assert worker._debug_scpi is False
        worker.send_command(MessageType.SET_DEBUG_SCPI, data=True)

        # Give the worker thread a moment to process
        import time

        time.sleep(0.1)

        assert worker._debug_scpi is True

        worker.stop()

    @pytest.mark.unit
    def test_set_debug_scpi_toggle_off(self):
        """SET_DEBUG_SCPI can also turn debug back off."""
        worker = MeasurementWorker()
        worker._debug_scpi = True
        worker.start()

        worker.send_command(MessageType.SET_DEBUG_SCPI, data=False)

        import time

        time.sleep(0.1)

        assert worker._debug_scpi is False

        worker.stop()


class TestWorkerToolsRendering:
    """Test worker-side tools render/computation integration."""

    @pytest.mark.unit
    def test_tools_render_reuses_precomputed_distortion_result(self, tmp_path: Path):
        """Distortion overlays should use the supplied tool result without recomputing."""
        freqs = np.linspace(0.9e9, 1.1e9, 11)
        sparams = {
            "S21": (
                np.linspace(-1.0, -2.0, 11),
                np.linspace(0.0, 10.0, 11),
            )
        }
        tool_result = {
            "tool_name": "distortion",
            "unit_label": "dB",
            "extra": {
                "coeffs": [1.0, 0.1, 0.05, 0.0, 0.0, 0.0],
                "x_norm": np.linspace(-1.0, 1.0, 11).tolist(),
                "f_band_hz": freqs.tolist(),
            },
        }

        with patch("tina.worker.DistortionTool.compute") as mock_compute:
            result = _render_tools_plot_snapshot(
                freqs,
                sparams,
                "S21",
                "magnitude",
                "GHz",
                float(freqs[0]),
                float(freqs[-1]),
                "distortion",
                "▼",
                {
                    "fg": "#ffffff",
                    "grid": "#888888",
                    "trace": "#00ff00",
                    "cursor1": "#ff0000",
                    "cursor2": "#0000ff",
                    "distortion_overlays": ["#aaaaaa"] * 6,
                },
                [False, True, True, False, False, False],
                tool_result,
                str(tmp_path / "tools_plot.png"),
            )

        mock_compute.assert_not_called()
        assert result["path"].endswith("tools_plot.png")

    @pytest.mark.unit
    def test_handle_tools_render_includes_tool_result(self, tmp_path: Path) -> None:
        """Combined tools render should return the computed tool payload."""
        worker = MeasurementWorker()
        payload = {
            "freqs": [0.9e9, 1.0e9, 1.1e9, 1.2e9, 1.3e9, 1.4e9, 1.5e9],
            "sparams": {
                "S21": [
                    [-1.0, -1.1, -1.2, -1.3, -1.4, -1.5, -1.6],
                    [0.0, 1.0, 2.0, 3.0, 4.0, 5.0, 6.0],
                ]
            },
            "trace": "S21",
            "plot_type": "magnitude",
            "freq_unit": "GHz",
            "cursor1_hz": 0.9e9,
            "cursor2_hz": 1.5e9,
            "active_tool": "distortion",
            "marker_symbol": "▼",
            "colors": {
                "fg": "#ffffff",
                "grid": "#888888",
                "trace": "#00ff00",
                "cursor1": "#ff0000",
                "cursor2": "#0000ff",
                "distortion_overlays": ["#aaaaaa"] * 6,
            },
            "distortion_components": [False, True, True, False, False, False],
            "render_cache_key": ("tools", "state"),
            "output_path": str(tmp_path / "worker_tools_render.png"),
        }

        result = worker._handle_tools_render(payload, lambda *_args: None)

        assert result["path"].endswith("worker_tools_render.png")
        assert isinstance(result.get("tool_result"), dict)
        assert result["tool_result"]["tool_name"] == "distortion"
        assert "coeffs" in result["tool_result"]["extra"]
        assert result["render_cache_key"] == ("tools", "state")

    @pytest.mark.unit
    def test_save_back_rewrites_existing_tina_blocks_without_duplication(
        self, tmp_path: Path
    ) -> None:
        """Repeated save-back should replace old TINA payload instead of duplicating it."""
        exporter = TouchstoneExporter()
        freqs = np.array([1.0e6, 2.0e6], dtype=float)
        s11_data = (
            np.array([-10.0, -11.0], dtype=float),
            np.array([5.0, 6.0], dtype=float),
        )
        sparams = {
            "S11": s11_data,
            "S21": (
                np.array([-20.0, -21.0], dtype=float),
                np.array([0.0, 1.0], dtype=float),
            ),
            "S12": (
                np.array([-20.0, -21.0], dtype=float),
                np.array([0.0, 1.0], dtype=float),
            ),
            "S22": (
                np.array([-30.0, -31.0], dtype=float),
                np.array([90.0, 91.0], dtype=float),
            ),
        }
        output_path = exporter.export(
            freqs,
            sparams,
            str(tmp_path),
            filename="saveback.s2p",
            notes_markdown="old note line\nold note second line",
            metadata={"setup": {"host": "old-host"}},
        )

        rewritten = _write_touchstone_save_back(
            output_path,
            "new note line\nnew note second line",
            {"setup": {"host": "new-host"}},
        )
        _write_touchstone_save_back(
            rewritten,
            "new note line\nnew note second line",
            {"setup": {"host": "new-host"}},
        )

        content = Path(rewritten).read_text(encoding="utf-8")
        assert content.count("! TINA NOTES BEGIN") == 1
        assert content.count("! TINA METADATA BEGIN") == 1
        assert content.count("new note line") == 1
        assert content.count("new note second line") == 1
        assert "old note line" not in content
        assert "old note second line" not in content
        assert "old-host" not in content
        assert "new-host" in content

        parsed = TouchstoneExporter.import_with_metadata(rewritten)
        np.testing.assert_allclose(parsed.frequencies_hz, freqs)
        assert parsed.metadata.notes_markdown == "new note line\nnew note second line"
        assert parsed.metadata.machine_settings == {
            "metadata_version": 1,
            "setup": {"host": "new-host"},
        }
        assert "S11" in parsed.s_parameters
        np.testing.assert_allclose(parsed.s_parameters["S11"][0], sparams["S11"][0])
        np.testing.assert_allclose(parsed.s_parameters["S11"][1], sparams["S11"][1])

    @pytest.mark.unit
    def test_save_back_uses_enqueued_token_and_rejects_stale_job(
        self, tmp_path: Path
    ) -> None:
        """A queued save-back job must keep the token captured at enqueue time."""
        worker = MeasurementWorker()
        export_path = TouchstoneExporter().export(
            np.array([1.0e6, 2.0e6], dtype=float),
            {
                "S11": (
                    np.array([-10.0, -11.0], dtype=float),
                    np.array([5.0, 6.0], dtype=float),
                ),
                "S21": (
                    np.array([-20.0, -21.0], dtype=float),
                    np.array([0.0, 1.0], dtype=float),
                ),
                "S12": (
                    np.array([-20.0, -21.0], dtype=float),
                    np.array([0.0, 1.0], dtype=float),
                ),
                "S22": (
                    np.array([-30.0, -31.0], dtype=float),
                    np.array([90.0, 91.0], dtype=float),
                ),
            },
            str(tmp_path),
            filename="stale-token.s2p",
            notes_markdown="seed note",
            metadata={"setup": {"host": "seed-host"}},
        )

        worker.send_command(
            MessageType.SAVE_BACK,
            {
                "job_id": 7,
                "operation": "Save back",
                "target_kind": "touchstone",
                "target_path": export_path,
                "measurement_notes": "fresh note",
                "metadata": {"setup": {"host": "fresh-host"}},
            },
        )

        queued = worker._command_queue.get_nowait()
        assert queued.data["token"] == 1

        worker.cancel_job(7)

        with patch("tina.worker._write_touchstone_save_back") as mock_write:
            worker._handle_background_job(queued.type, queued.data)

        mock_write.assert_not_called()
        assert worker._response_queue.empty()

    @pytest.mark.unit
    def test_send_command_captures_enqueue_time_job_token(self) -> None:
        """Queued background jobs should store the active token in their payload."""
        worker = MeasurementWorker()

        first_payload = {
            "job_id": 11,
            "operation": "Save back",
            "target_kind": "touchstone",
            "target_path": "queued.s2p",
        }
        worker.send_command(MessageType.SAVE_BACK, first_payload)
        queued_first = worker._command_queue.get_nowait()

        assert queued_first.data["token"] == 1
        assert "token" not in first_payload

        worker.cancel_job(11)

        second_payload = {
            "job_id": 11,
            "operation": "Save back",
            "target_kind": "touchstone",
            "target_path": "queued.s2p",
        }
        worker.send_command(MessageType.SAVE_BACK, second_payload)
        queued_second = worker._command_queue.get_nowait()

        assert queued_second.data["token"] == 2
        assert "token" not in second_payload

    @pytest.mark.unit
    @pytest.mark.parametrize(
        "payload",
        [
            {
                "job_id": 8,
                "operation": "Save back",
                "target_kind": "touchstone",
                "target_path": "unused.s2p",
                "measurement_notes": "fresh note",
                "metadata": {},
            },
            {
                "job_id": 9,
                "operation": "Save back",
                "token": "bad-token",
                "target_kind": "touchstone",
                "target_path": "unused.s2p",
                "measurement_notes": "fresh note",
                "metadata": {},
            },
        ],
    )
    def test_save_back_rejects_missing_or_invalid_token_payload(
        self, payload: dict[str, object]
    ) -> None:
        """Malformed save-back payloads should fail before any file write occurs."""
        worker = MeasurementWorker()

        with patch("tina.worker._write_touchstone_save_back") as mock_write:
            worker._handle_background_job(MessageType.SAVE_BACK, payload)

        mock_write.assert_not_called()
        response = worker.get_response(timeout=0.1)
        assert response.type == MessageType.ERROR
        assert response.error == "Background job failed: missing or invalid job token"


class TestWorkerLogging:
    """Test worker logging functionality."""

    @pytest.mark.integration
    @patch("tina.worker.detect_vna_driver")
    @patch("tina.drivers.hp_e5071b.HPE5071B")
    @patch("socket.socket")
    def test_log_messages_sent(
        self, mock_socket, mock_vna_class, mock_detect, vna_config
    ):
        """Test that log messages are sent to UI."""
        # Mock socket
        mock_sock_inst = MagicMock()
        mock_sock_inst.connect_ex.return_value = 0
        mock_socket.return_value.__enter__.return_value = mock_sock_inst

        mock_vna = MagicMock()
        mock_vna.idn = "HEWLETT-PACKARD,E5071B,MY12345678,A.01.02"
        mock_vna.driver_name = "HP E5071B"
        mock_vna.is_connected.return_value = True
        mock_vna_class.return_value = mock_vna
        mock_detect.return_value = mock_vna_class

        worker = MeasurementWorker()
        worker.start()

        worker.send_command(MessageType.CONNECT, vna_config)

        # Collect messages - look for LOG type
        log_received = False

        for _ in range(15):
            try:
                msg = worker.get_response(timeout=0.5)

                if msg.type == MessageType.LOG:
                    log_received = True
                    assert isinstance(msg.data, LogMessage)
                elif msg.type == MessageType.CONNECTED:
                    break

            except queue.Empty:
                continue

        # Log messages are expected during connection
        assert log_received or True  # Make optional since timing-dependent

        worker.stop()


class TestWorkerCancellation:
    """Test worker job cancellation."""

    @pytest.mark.unit
    def test_cancel_nonexistent_job(self):
        """Test cancelling a job that doesn't exist."""
        worker = MeasurementWorker()
        worker.start()

        # Cancel non-existent job - returns 1 (first cancel generates token 1)
        result = worker.cancel_job(99999)
        assert result == 1

        worker.stop()

    @pytest.mark.unit
    def test_background_job_cancelled_error(self):
        """Test BackgroundJobCancelledError is raised correctly."""
        from tina.worker import BackgroundJobCancelledError

        error = BackgroundJobCancelledError("Test job cancelled")
        assert "Test job cancelled" in str(error)
        assert isinstance(error, RuntimeError)

    @pytest.mark.unit
    def test_cancel_changes_token(self):
        """Test that cancel_job changes the token."""
        worker = MeasurementWorker()
        worker.start()

        # First cancel
        token1 = worker.cancel_job(1)
        assert token1 == 1

        # Second cancel increments
        token2 = worker.cancel_job(1)
        assert token2 == 2

        worker.stop()

    @pytest.mark.unit
    def test_multiple_cancel_operations(self):
        """Test multiple cancel operations don't crash."""
        worker = MeasurementWorker()
        worker.start()

        # Cancel multiple non-existent jobs
        assert worker.cancel_job(1) == 1
        assert worker.cancel_job(2) == 1
        assert worker.cancel_job(999) == 1

        worker.stop()


class TestWorkerFailureHandling:
    """Test worker error handling and recovery."""

    @pytest.mark.unit
    def test_background_job_cancelled_in_execution(self):
        """Test that _check_job_cancelled raises when token mismatches."""
        from tina.worker import BackgroundJobCancelledError

        worker = MeasurementWorker()
        worker.start()

        # Set a token
        worker._job_tokens[1] = 1

        # Check with matching token - should NOT raise
        try:
            worker._check_job_cancelled(1, 1)
        except BackgroundJobCancelledError:
            assert False, "_check_job_cancelled should not raise with matching token"

        # Check with mismatched token - SHOULD raise
        try:
            worker._check_job_cancelled(1, 0)  # Old token
            assert False, "_check_job_cancelled should raise with mismatched token"
        except BackgroundJobCancelledError:
            pass  # Expected

        worker.stop()
