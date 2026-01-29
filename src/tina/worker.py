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
from typing import Any, Callable, Dict, Optional, Tuple

import numpy as np

from .vna import VNA, VNAConfig


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
    error: Optional[str] = None


@dataclass
class ProgressUpdate:
    """Progress update data."""

    message: str
    progress_pct: float


@dataclass
class MeasurementResult:
    """Measurement result data."""

    frequencies: np.ndarray
    sparams: Dict[str, Tuple[np.ndarray, np.ndarray]]


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


class LoggingVNAWrapper:
    """Wrapper around VNA that automatically logs all SCPI commands."""

    def __init__(self, vna: VNA, log_callback: Callable[[str, str], None]):
        """
        Initialize wrapper.

        Args:
            vna: VNA instance to wrap
            log_callback: Callback function(message, level) for logging
        """
        self._vna = vna
        self._log = log_callback

    def command(self, cmd: str):
        """Send command with automatic logging."""
        self._log(cmd, "tx")
        self._vna._send_command(cmd)

    def query(self, cmd: str) -> str:
        """Query with automatic logging."""
        self._log(cmd, "tx")
        response = self._vna._query(cmd)

        # Compress long responses for logging
        response_stripped = response.strip()
        if len(response_stripped) > 200:
            # Count data points (comma-separated values)
            data_count = response_stripped.count(",") + 1
            first_vals = ",".join(response_stripped.split(",")[:3])
            self._log(f"[{data_count} values: {first_vals}...]", "rx")
        else:
            self._log(response_stripped, "rx")

        return response

    def __getattr__(self, name):
        """Pass through other attributes to wrapped VNA."""
        return getattr(self._vna, name)


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
        self._thread: Optional[threading.Thread] = None
        self._running = False
        self._vna: Optional[VNA] = None
        self._vna_wrapper: Optional[LoggingVNAWrapper] = None
        self._config: Optional[VNAConfig] = None

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
        self, msg_type: MessageType, data: Any = None, error: Optional[str] = None
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
        """Handle connection command."""
        try:
            self._config = config
            self._vna = VNA(config)

            # Progress callback
            def on_progress(msg, pct):
                self._send_progress(msg, pct)

            # Connect (blocking operation)
            self._vna.connect(progress_callback=on_progress)

            # Create logging wrapper for automatic TX/RX logging
            self._vna_wrapper = LoggingVNAWrapper(self._vna, self._log)

            # Log the IDN query that was done during connect
            self._log("*IDN?", "tx")
            self._log(self._vna.idn, "rx")

            # Send success response
            self._send_response(MessageType.CONNECTED, data=self._vna.idn)

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
        """Handle read parameters command."""
        try:
            if not self._vna or not self._vna.is_connected():
                raise RuntimeError("Not connected to VNA")

            # Read start frequency
            self._send_progress("Reading start frequency...", 10)
            start_freq = float(self._vna_wrapper.query("SENS1:FREQ:STAR?").strip())

            # Read stop frequency
            self._send_progress("Reading stop frequency...", 30)
            stop_freq = float(self._vna_wrapper.query("SENS1:FREQ:STOP?").strip())

            # Read sweep points
            self._send_progress("Reading sweep points...", 50)
            points = int(float(self._vna_wrapper.query("SENS1:SWE:POIN?").strip()))

            # Read averaging state
            self._send_progress("Reading averaging state...", 70)
            avg_state_resp = self._vna_wrapper.query("SENS1:AVER:STAT?").strip()
            avg_state = avg_state_resp == "1"

            # Read averaging count
            self._send_progress("Reading averaging count...", 90)
            avg_count = int(float(self._vna_wrapper.query("SENS1:AVER:COUN?").strip()))

            result = ParamsResult(
                start_freq=start_freq,
                stop_freq=stop_freq,
                points=points,
                averaging_enabled=avg_state,
                averaging_count=avg_count,
            )

            self._send_progress("Done reading parameters", 100)
            self._send_response(MessageType.PARAMS_READ, data=result)

        except Exception as e:
            self._send_response(
                MessageType.ERROR, error=f"Failed to read parameters: {str(e)}"
            )

    def _wait_for_completion(self, vna_wrapper, timeout_seconds: float = 60.0) -> None:
        """
        Wait for VNA operation to complete.

        Args:
            vna_wrapper: VNA wrapper instance
            timeout_seconds: Maximum time to wait

        Raises:
            TimeoutError: If operation doesn't complete within timeout
        """
        import time

        timeout = time.time() + timeout_seconds
        while time.time() < timeout:
            resp = vna_wrapper.query("*OPC?")
            if resp.strip() in ("1", "+1"):
                return
            time.sleep(0.1)

        raise TimeoutError(
            f"Operation did not complete within {timeout_seconds} seconds"
        )

    def _handle_measure(self, config: VNAConfig) -> None:
        """Handle measurement command."""
        try:
            if not self._vna or not self._vna.is_connected():
                raise RuntimeError("Not connected to VNA")

            # Update config
            self._config = config
            self._vna.config = config

            vna = self._vna_wrapper  # Shorthand for readability

            # Configure frequency
            self._send_progress("Configuring frequency...", 5)
            if config.set_freq_range:
                vna.command(f"SENS1:FREQ:STAR {config.start_freq_hz}")
                vna.command(f"SENS1:FREQ:STOP {config.stop_freq_hz}")

            # Configure measurements
            self._send_progress("Configuring measurement settings...", 10)
            vna.command("FORM:DATA ASCII")
            vna.command("INIT1:CONT OFF")
            vna.command("SENS1:SWE:TYPE LIN")

            if config.set_sweep_points:
                vna.command(f"SENS1:SWE:POIN {config.sweep_points}")

            avg_state = "ON" if config.enable_averaging else "OFF"
            vna.command(f"SENS1:AVER:STAT {avg_state}")

            if config.set_averaging_count:
                vna.command(f"SENS1:AVER:COUN {config.averaging_count}")

            # Setup S-parameters
            self._send_progress("Setting up S-parameters...", 20)
            vna.command("CALC1:PAR:COUN 4")

            for idx, param in enumerate(["S11", "S21", "S12", "S22"], start=1):
                vna.command(f"CALC1:PAR{idx}:DEF {param}")
                vna.command(f"CALC1:PAR{idx}:SEL")

            vna.command("CALC1:PAR1:SEL")
            vna.command("ABOR")
            vna.command("INIT1")

            # Wait for S-parameter setup completion
            self._wait_for_completion(vna, timeout_seconds=30.0)

            # Trigger sweep
            self._send_progress("Triggering sweep...", 30)
            vna.command("ABOR")
            vna.command("INIT1")

            # Wait for sweep completion
            self._wait_for_completion(vna, timeout_seconds=60.0)

            # Get frequency axis
            self._send_progress("Reading frequency data...", 50)
            freqs_data = vna.query("SENS1:FREQ:DATA?")
            freqs = np.array(
                [float(x) for x in freqs_data.strip().split(",")], dtype=float
            )

            # Get S-parameters
            sparams = {}
            param_names = ["S11", "S21", "S12", "S22"]
            for idx, name in enumerate(param_names, start=1):
                progress = 50 + (idx * 10)
                self._send_progress(f"Reading {name}...", progress)

                # Select parameter
                vna.command(f"CALC1:PAR{idx}:SEL")

                # Query complex data
                data_str = vna.query("CALC1:DATA:SDAT?")
                data = [float(x) for x in data_str.strip().split(",")]

                # Parse real and imaginary
                if len(data) % 2 != 0:
                    data = data[:-1]
                real = np.array(data[0::2])
                imag = np.array(data[1::2])

                # Convert to magnitude (dB) and phase (degrees)
                comp = real + 1j * imag
                mag_db = 20 * np.log10(np.abs(comp) + 1e-15)
                phase_deg = np.angle(comp, deg=True)

                sparams[name] = (mag_db, phase_deg)

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
