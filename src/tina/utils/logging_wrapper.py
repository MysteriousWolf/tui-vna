"""
Logging wrapper for VNA drivers.

Automatically logs all SCPI commands sent to the VNA for debugging and monitoring.
"""

from collections.abc import Callable

from ..config.constants import SCPI_RESPONSE_TRUNCATE_LENGTH
from ..drivers.base import VNABase


class LoggingVNAWrapper:
    """Wrapper that intercepts VNA driver methods to log SCPI commands."""

    def __init__(self, vna: VNABase, log_callback: Callable[[str, str], None]):
        """
        Initialize logging wrapper.

        Args:
            vna: VNA driver instance to wrap
            log_callback: Callback function(message, level) for logging
        """
        self._vna = vna
        self._log = log_callback
        self.debug = False

        # Wrap the low-level SCPI methods
        self._wrap_scpi_methods()

    def _wrap_scpi_methods(self):
        """Wrap the driver's SCPI communication methods with logging."""
        # Store original methods
        original_send_command = self._vna._send_command
        original_query = self._vna._query
        original_query_ascii = self._vna._query_ascii_values

        # Capture raw query before wrapping (used for SYST:ERR? checks)
        self._raw_query = original_query

        # Wrap _send_command
        def logged_send_command(command: str):
            self._log(command, "tx")
            result = original_send_command(command)
            if self.debug:
                try:
                    self._log("SYST:ERR?", "debug")
                    err = self._raw_query("SYST:ERR?").strip()
                    self._log(err, "debug")
                    if not err.startswith("+0"):
                        self._log(f"SCPI ERR after '{command}': {err}", "error")
                except Exception:
                    pass
            return result

        # Wrap _query
        def logged_query(command: str) -> str:
            self._log(command, "tx")
            response = original_query(command)

            # Log response (truncated if needed)
            response_stripped = response.strip()
            if len(response_stripped) > SCPI_RESPONSE_TRUNCATE_LENGTH:
                data_count = response_stripped.count(",") + 1
                first_vals = ",".join(response_stripped.split(",")[:3])
                self._log(f"[{data_count} values: {first_vals}...]", "rx")
            else:
                self._log(response_stripped, "rx")

            if self.debug:
                try:
                    self._log("SYST:ERR?", "debug")
                    err = self._raw_query("SYST:ERR?").strip()
                    self._log(err, "debug")
                    if not err.startswith("+0"):
                        self._log(f"SCPI ERR after '{command}': {err}", "error")
                except Exception:
                    pass

            return response

        # Wrap _query_ascii_values
        def logged_query_ascii(command: str):
            self._log(command, "tx")
            result = original_query_ascii(command)

            # Log abbreviated response for large arrays
            if len(result) > 10:
                self._log(
                    f"[{len(result)} values: {result[0]:.3e},{result[1]:.3e},{result[2]:.3e}...]",
                    "rx",
                )
            else:
                self._log(str(result), "rx")

            if self.debug:
                try:
                    self._log("SYST:ERR?", "debug")
                    err = self._raw_query("SYST:ERR?").strip()
                    self._log(err, "debug")
                    if not err.startswith("+0"):
                        self._log(f"SCPI ERR after '{command}': {err}", "error")
                except Exception:
                    pass

            return result

        # Replace methods on the driver instance
        self._vna._send_command = logged_send_command
        self._vna._query = logged_query
        self._vna._query_ascii_values = logged_query_ascii

    def __getattr__(self, name):
        """Pass through all other attributes to wrapped VNA."""
        return getattr(self._vna, name)
