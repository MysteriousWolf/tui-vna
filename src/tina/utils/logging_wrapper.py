"""
Logging wrapper for VNA drivers.

Automatically logs all SCPI commands sent to the VNA for debugging and monitoring.
"""

from collections.abc import Callable

from ..config.constants import SCPI_RESPONSE_TRUNCATE_LENGTH
from ..drivers.base import VNABase


class LoggingVNAWrapper:
    """Wraps a VNA driver to log every SCPI command sent and response received.

    The driver's low-level communication methods (_send_command, _query,
    _query_ascii_values) are monkey-patched in-place so that higher-level
    driver methods (get_status, configure_frequency, etc.) automatically
    produce log entries without any changes to the driver itself.

    Attributes:
        debug:          When True, issues ``SYST:ERR?`` after every command and
                        logs any non-zero error codes at ``"error"`` level.
        log_tag:        When set, composite log levels ``"tx/<tag>"`` /
                        ``"rx/<tag>"`` replace plain ``"tx"`` / ``"rx"``.  Set
                        to ``"poll"`` during status polling to allow separate
                        filtering in the UI.
        on_scpi_error:  Optional callback ``(command, raw_error)`` fired after
                        every ``SYST:ERR?`` check when ``debug=True``.  Called
                        for both clean (``"+0,…"``) and error responses so the
                        caller can maintain a last-error display.
    """

    def __init__(
        self,
        vna: VNABase,
        log_callback: Callable[[str, str], None],
        on_scpi_error: Callable[[str, str], None] | None = None,
    ):
        """
        Args:
            vna:            VNA driver instance to wrap.
            log_callback:   ``callback(message, level)`` used for all log output.
            on_scpi_error:  Optional ``callback(command, raw_error)`` fired after
                            every ``SYST:ERR?`` check in debug mode.  ``raw_error``
                            is the stripped SYST:ERR? response string; the command is
                            the SCPI command that preceded the check.
        """
        self._vna = vna
        self._log = log_callback
        self.on_scpi_error = on_scpi_error
        self.debug = False
        self.log_tag: str | None = None

        self._wrap_scpi_methods()

    def _wrap_scpi_methods(self) -> None:
        """Monkey-patch the driver's three SCPI primitives with logging versions.

        Originals are captured before patching and invoked inside each wrapper.
        ``_raw_query`` is stored separately so the ``SYST:ERR?`` debug check
        can bypass the wrapper and avoid recursive logging.
        """
        original_send = self._vna._send_command
        original_query = self._vna._query
        original_query_ascii = self._vna._query_ascii_values

        # Must not route SYST:ERR? back through the patched _query — that would
        # trigger another debug check, causing infinite recursion.
        self._raw_query = original_query

        # --- closures (capture self from outer scope) ---

        def _tx_rx() -> tuple[str, str]:
            """Return (send_level, recv_level) respecting the current log_tag."""
            if self.log_tag:
                return f"tx/{self.log_tag}", f"rx/{self.log_tag}"
            return "tx", "rx"

        def _check_error(command: str) -> None:
            """Issue SYST:ERR? and report non-zero errors. No-op unless debug=True."""
            if not self.debug:
                return
            try:
                self._log("SYST:ERR?", "tx/debug")
                err = self._raw_query("SYST:ERR?").strip()
                self._log(err, "rx/debug")
                if not err.startswith("+0"):
                    self._log(f"SCPI ERR after '{command}': {err}", "error")
                if self.on_scpi_error is not None:
                    self.on_scpi_error(command, err)
            except Exception:
                pass

        def logged_send_command(command: str):
            send_tag, _ = _tx_rx()
            self._log(command, send_tag)
            result = original_send(command)
            _check_error(command)
            return result

        def logged_query(command: str) -> str:
            send_tag, recv_tag = _tx_rx()
            self._log(command, send_tag)
            response = original_query(command)
            stripped = response.strip()
            if len(stripped) > SCPI_RESPONSE_TRUNCATE_LENGTH:
                count = stripped.count(",") + 1
                preview = ",".join(stripped.split(",")[:3])
                self._log(f"[{count} values: {preview}...]", recv_tag)
            else:
                self._log(stripped, recv_tag)
            _check_error(command)
            return response

        def logged_query_ascii(command: str):
            send_tag, recv_tag = _tx_rx()
            self._log(command, send_tag)
            result = original_query_ascii(command)
            if len(result) > 10:
                self._log(
                    f"[{len(result)} values: {result[0]:.3e},{result[1]:.3e},{result[2]:.3e}...]",
                    recv_tag,
                )
            else:
                self._log(str(result), recv_tag)
            _check_error(command)
            return result

        self._vna._send_command = logged_send_command
        self._vna._query = logged_query
        self._vna._query_ascii_values = logged_query_ascii

    def __getattr__(self, name):
        """Delegate all attribute lookups not found on the wrapper to the driver."""
        return getattr(self._vna, name)
