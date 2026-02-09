"""
Measurement worker thread for non-blocking VNA operations.

This module provides a clean thread-based architecture for running VNA measurements
without blocking the UI thread. Uses standard library queue.Queue for thread-safe
communication.
"""

import queue
import threading
import traceback
from dataclasses import dataclass
from enum import Enum
from typing import Any

import numpy as np

from .drivers import VNABase, VNAConfig, detect_vna_driver
from .utils import LoggingVNAWrapper


class MessageType(Enum):
    """Message types for worker communication."""

    # Commands (UI -> Worker)
    CONNECT = "connect"
    DISCONNECT = "disconnect"
    READ_PARAMS = "read_params"
    MEASURE = "measure"
    SHUTDOWN = "shutdown"

    # Responses (Worker -> UI)
    CONNECTED = "connected"
    DISCONNECTED = "disconnected"
    PARAMS_READ = "params_read"
    MEASUREMENT_COMPLETE = "measurement_complete"
    ERROR = "error"
    PROGRESS = "progress"
    LOG = "log"  # Log message (TX/RX/info)


@dataclass
class Message:
    """Message structure for inter-thread communication."""

    type: MessageType
    data: Any = None
    error: str | None = None


@dataclass
class ProgressUpdate:
    """Progress update data."""

    message: str
    progress_pct: float


@dataclass
class MeasurementResult:
    """Measurement result data."""

    frequencies: np.ndarray
    sparams: dict[str, tuple[np.ndarray, np.ndarray]]


@dataclass
class ParamsResult:
    """VNA parameters read result."""

    start_freq: float
    stop_freq: float
    points: int
    averaging_enabled: bool
    averaging_count: int


@dataclass
class LogMessage:
    """Log message data."""

    message: str
    level: str  # "tx", "rx", "info", "progress", etc.


class MeasurementWorker:
    """
    Worker thread for VNA measurements.

    Handles all blocking VNA operations in a separate thread, communicating
    with the UI thread via thread-safe queues.

    Usage:
        worker = MeasurementWorker()
        worker.start()

        # Send command
        worker.send_command(MessageType.CONNECT, config)

        # Check for responses
        try:
            msg = worker.get_response(timeout=0.1)
            if msg.type == MessageType.CONNECTED:
                print("Connected!")
        except queue.Empty:
            pass

        # Cleanup
        worker.stop()
    """

    def __init__(self):
        """Initialize worker thread."""
        self._command_queue: queue.Queue = queue.Queue()
        self._response_queue: queue.Queue = queue.Queue()
        self._thread: threading.Thread | None = None
        self._running = False
        self._vna: VNABase | None = None
        self._vna_wrapper: LoggingVNAWrapper | None = None
        self._config: VNAConfig | None = None

    def start(self):
        """Start the worker thread."""
        if self._running:
            return

        self._running = True
        self._thread = threading.Thread(target=self._worker_loop, daemon=True)
        self._thread.start()

    def stop(self, timeout: float = 5.0):
        """
        Stop the worker thread gracefully.

        Args:
            timeout: Maximum time to wait for thread shutdown in seconds
        """
        if not self._running:
            return

        self.send_command(MessageType.SHUTDOWN)

        if self._thread:
            self._thread.join(timeout=timeout)
            self._thread = None

        self._running = False

    def send_command(self, msg_type: MessageType, data: Any = None):
        """
        Send command to worker thread.

        Args:
            msg_type: Type of message
            data: Optional data payload
        """
        self._command_queue.put(Message(type=msg_type, data=data))

    def get_response(self, timeout: float = 0.1) -> Message:
        """
        Get response from worker thread (non-blocking with timeout).

        Args:
            timeout: Timeout in seconds

        Returns:
            Message from worker

        Raises:
            queue.Empty: If no message available within timeout
        """
        return self._response_queue.get(timeout=timeout)

    def _send_response(
        self, msg_type: MessageType, data: Any = None, error: str | None = None
    ):
        """Send response to UI thread."""
        self._response_queue.put(Message(type=msg_type, data=data, error=error))

    def _send_progress(self, message: str, progress_pct: float):
        """Send progress update to UI thread."""
        self._send_response(
            MessageType.PROGRESS,
            ProgressUpdate(message=message, progress_pct=progress_pct),
        )

    def _log(self, message: str, level: str = "info"):
        """Send log message to UI thread."""
        self._send_response(MessageType.LOG, LogMessage(message=message, level=level))

    def _vna_command(self, command: str):
        """Send VNA command with logging."""
        self._log(command, "tx")
        self._vna._send_command(command)

    def _vna_query(self, command: str) -> str:
        """Query VNA with logging."""
        self._log(command, "tx")
        response = self._vna._query(command)
        self._log(response.strip(), "rx")
        return response

    def _worker_loop(self):
        """Main worker thread loop."""
        while self._running:
            try:
                # Wait for command with timeout to allow checking _running flag
                try:
                    msg = self._command_queue.get(timeout=0.1)
                except queue.Empty:
                    continue

                # Process command
                if msg.type == MessageType.SHUTDOWN:
                    self._handle_shutdown()
                    break
                elif msg.type == MessageType.CONNECT:
                    self._handle_connect(msg.data)
                elif msg.type == MessageType.DISCONNECT:
                    self._handle_disconnect()
                elif msg.type == MessageType.READ_PARAMS:
                    self._handle_read_params()
                elif msg.type == MessageType.MEASURE:
                    self._handle_measure(msg.data)

            except Exception as e:
                # Catch-all error handler
                self._send_response(
                    MessageType.ERROR,
                    error=f"Worker error: {str(e)}\n{traceback.format_exc()}",
                )

    def _handle_connect(self, config: VNAConfig):
        """Handle connection command with automatic driver detection."""
        try:
            self._config = config

            # First, try connecting with a generic driver to get IDN
            # We'll use HPE5071B as the default for now, but this could be
            # made more generic with a basic SCPI connection class
            from .drivers import HPE5071B

            temp_vna = HPE5071B(config)

            # Progress callback
            def on_progress(msg, pct):
                self._send_progress(msg, pct)

            # Connect to get IDN
            self._send_progress("Connecting...", 10)
            temp_vna.connect(progress_callback=on_progress)
            idn_string = temp_vna.idn

            # Detect the correct driver
            self._send_progress("Detecting VNA type...", 90)
            driver_class = detect_vna_driver(idn_string)

            if driver_class is None:
                # No specific driver found, use the temp connection
                self._log(f"No specific driver found for: {idn_string}", "info")
                self._log("Using default driver", "info")
                self._vna = temp_vna
            elif isinstance(temp_vna, driver_class):
                # Already using the right driver
                self._vna = temp_vna
            else:
                # Need to switch to a different driver
                temp_vna.disconnect()
                self._log(f"Detected: {driver_class.driver_name}", "info")
                self._vna = driver_class(config)
                self._vna.connect(progress_callback=on_progress)

            # Wrap driver with logging to capture all SCPI commands
            self._vna = LoggingVNAWrapper(self._vna, self._log)
            self._vna_wrapper = self._vna  # Keep for compatibility

            # Log the IDN (already queried during connection)
            self._log("*IDN?", "tx")
            self._log(self._vna.idn, "rx")

            # Send success response with driver info
            driver_info = f"{self._vna.idn} [{self._vna.driver_name}]"
            self._send_response(MessageType.CONNECTED, data=driver_info)

        except Exception as e:
            self._send_response(MessageType.ERROR, error=f"Connection failed: {str(e)}")
            self._vna = None
            self._vna_wrapper = None

    def _handle_disconnect(self) -> None:
        """Handle disconnection command."""
        try:
            if self._vna:
                self._vna.disconnect()
                self._vna = None
                self._vna_wrapper = None

            self._send_response(MessageType.DISCONNECTED)

        except Exception as e:
            self._send_response(MessageType.ERROR, error=f"Disconnect failed: {str(e)}")

    def _handle_read_params(self) -> None:
        """Handle read parameters command using driver abstraction."""
        try:
            if not self._vna or not self._vna.is_connected():
                raise RuntimeError("Not connected to VNA")

            self._send_progress("Reading VNA parameters...", 50)

            # Get all parameters from driver
            params = self._vna.get_current_parameters()

            result = ParamsResult(
                start_freq=params.get("start_freq_hz", 0.0),
                stop_freq=params.get("stop_freq_hz", 0.0),
                points=params.get("sweep_points", 0),
                averaging_enabled=params.get("averaging_enabled", False),
                averaging_count=params.get("averaging_count", 0),
            )

            self._send_progress("Done reading parameters", 100)
            self._send_response(MessageType.PARAMS_READ, data=result)

        except Exception as e:
            self._send_response(
                MessageType.ERROR, error=f"Failed to read parameters: {str(e)}"
            )

    def _handle_measure(self, config: VNAConfig) -> None:
        """Handle measurement command using driver abstraction."""
        try:
            if not self._vna or not self._vna.is_connected():
                raise RuntimeError("Not connected to VNA")

            # Update config
            self._config = config
            self._vna.config = config

            # Configure frequency
            self._send_progress("Configuring frequency...", 5)
            self._vna.configure_frequency()

            # Configure measurements
            self._send_progress("Configuring measurement settings...", 10)
            self._vna.configure_measurements()

            # Setup S-parameters
            self._send_progress("Setting up S-parameters...", 20)
            self._vna.setup_s_parameters()

            # Save trigger state before sweep
            self._send_progress("Triggering sweep...", 30)
            trigger_state = self._vna.save_trigger_state()

            # Trigger sweep (doesn't restore state)
            self._vna.trigger_sweep()

            # Get frequency axis
            self._send_progress("Reading frequency data...", 50)
            freqs = self._vna.get_frequency_axis()

            # Get S-parameters
            sparams = {}
            param_names = ["S11", "S21", "S12", "S22"]
            for idx, name in enumerate(param_names, start=1):
                progress = 50 + (idx * 10)
                self._send_progress(f"Reading {name}...", progress)
                sparams[name] = self._vna.get_sparam_data(idx)

            # Restore trigger state AFTER reading all data
            self._vna.restore_trigger_state(trigger_state)

            result = MeasurementResult(frequencies=freqs, sparams=sparams)

            self._send_progress("Measurement complete", 100)
            self._log(
                f"Sending measurement result: {len(freqs)} freqs, {len(sparams)} sparams",
                "debug",
            )
            self._send_response(MessageType.MEASUREMENT_COMPLETE, data=result)

        except Exception as e:
            self._send_response(
                MessageType.ERROR, error=f"Measurement failed: {str(e)}"
            )

    def _handle_shutdown(self) -> None:
        """Handle shutdown command."""
        if self._vna:
            try:
                self._vna.disconnect()
            except Exception:
                pass
        self._vna = None
        self._vna_wrapper = None
        self._running = False
