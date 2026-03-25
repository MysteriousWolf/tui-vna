"""
Unit tests for LoggingVNAWrapper.

Tests logging behaviour, log_tag overrides, debug SYST:ERR? checking,
error detection, and attribute delegation to the wrapped driver.
"""

import pytest

from src.tina.utils.logging_wrapper import LoggingVNAWrapper  # noqa: E402

# ---------------------------------------------------------------------------
# Minimal stub driver — satisfies the interface without any hardware
# ---------------------------------------------------------------------------


class _StubDriver:
    """Minimal stand-in for a real VNA driver."""

    driver_name = "Stub"
    idn = "STUB,MODEL,SN,FW"

    def __init__(self, query_responses: dict[str, str] | None = None):
        # Map command → response for _query; default returns "+0,\"No error\""
        self._responses = query_responses or {}
        self.commands_sent: list[str] = []
        self.queries_made: list[str] = []
        self.ascii_queries_made: list[str] = []

    def _send_command(self, command: str) -> None:
        self.commands_sent.append(command)

    def _query(self, command: str) -> str:
        self.queries_made.append(command)
        return self._responses.get(command, '+0,"No error"\n')

    def _query_ascii_values(self, command: str) -> list[float]:
        self.ascii_queries_made.append(command)
        return [1.0, 2.0, 3.0]

    def is_connected(self) -> bool:
        return True


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_wrapper(query_responses: dict[str, str] | None = None):
    """Return (stub_driver, wrapper, log_calls) for a fresh test setup."""
    log_calls: list[tuple[str, str]] = []
    stub = _StubDriver(query_responses)
    wrapper = LoggingVNAWrapper(stub, lambda msg, level: log_calls.append((msg, level)))
    return stub, wrapper, log_calls


def _levels(log_calls: list[tuple[str, str]]) -> list[str]:
    """Extract just the level strings from log_calls."""
    return [lvl for _, lvl in log_calls]


def _messages(log_calls: list[tuple[str, str]]) -> list[str]:
    """Extract just the message strings from log_calls."""
    return [msg for msg, _ in log_calls]


def _rx(log_calls: list[tuple[str, str]]) -> list[str]:
    """Return messages logged at 'rx' level."""
    return [msg for msg, lvl in log_calls if lvl == "rx"]


# ---------------------------------------------------------------------------
# Basic tx / rx logging
# ---------------------------------------------------------------------------


class TestBasicLogging:
    def test_send_command_logs_tx(self):
        stub, wrapper, log_calls = _make_wrapper()
        stub._send_command("*RST")
        assert ("*RST", "tx") in log_calls

    def test_query_logs_tx_and_rx(self):
        stub, wrapper, log_calls = _make_wrapper({"*IDN?": "Vendor,Model,SN\n"})
        stub._query("*IDN?")
        assert ("*IDN?", "tx") in log_calls
        assert ("Vendor,Model,SN", "rx") in log_calls

    def test_query_ascii_logs_tx_and_summary(self):
        stub, wrapper, log_calls = _make_wrapper()
        stub._query_ascii_values("CALC:DATA?")
        assert "CALC:DATA?" in _messages(log_calls)
        assert len(_rx(log_calls)) == 1

    def test_query_ascii_long_result_truncated(self, monkeypatch):
        """Results longer than 10 values should be logged as a summary."""
        import src.tina.utils.logging_wrapper as lw_mod

        monkeypatch.setattr(lw_mod, "SCPI_RESPONSE_TRUNCATE_LENGTH", 9999)

        log_calls: list[tuple[str, str]] = []
        stub = _StubDriver()
        # Patch ascii query to return 20 values; wrapper must be created after patching
        stub._query_ascii_values = lambda cmd: [float(i) for i in range(20)]
        LoggingVNAWrapper(stub, lambda msg, level: log_calls.append((msg, level)))

        stub._query_ascii_values("SENS:DATA?")
        rx_entries = _rx(log_calls)
        assert len(rx_entries) == 1
        assert "20 values" in rx_entries[0]

    def test_long_response_truncated(self, monkeypatch):
        """Responses longer than SCPI_RESPONSE_TRUNCATE_LENGTH are summarised."""
        import src.tina.utils.logging_wrapper as lw_mod

        monkeypatch.setattr(lw_mod, "SCPI_RESPONSE_TRUNCATE_LENGTH", 5)

        long_response = "1.0,2.0,3.0,4.0,5.0,6.0\n"
        stub, wrapper, log_calls = _make_wrapper({"SENS:DATA?": long_response})
        stub._query("SENS:DATA?")

        rx_entries = _rx(log_calls)
        assert len(rx_entries) == 1
        assert "values" in rx_entries[0]


# ---------------------------------------------------------------------------
# log_tag overrides
# ---------------------------------------------------------------------------


class TestLogTag:
    def test_log_tag_prefixes_levels(self):
        stub, wrapper, log_calls = _make_wrapper()
        wrapper.log_tag = "poll"
        stub._send_command("TRIG:SOUR?")
        assert ("TRIG:SOUR?", "tx/poll") in log_calls

    def test_log_tag_affects_query(self):
        stub, wrapper, log_calls = _make_wrapper({"BWID?": "70000\n"})
        wrapper.log_tag = "poll"
        stub._query("BWID?")
        tx_levels = [lvl for lvl in _levels(log_calls) if lvl.startswith("tx")]
        rx_levels = [lvl for lvl in _levels(log_calls) if lvl.startswith("rx")]
        assert "tx/poll" in tx_levels
        assert "rx/poll" in rx_levels

    def test_clearing_log_tag_restores_plain_levels(self):
        stub, wrapper, log_calls = _make_wrapper()
        wrapper.log_tag = "poll"
        wrapper.log_tag = None
        stub._send_command("*CLS")
        assert ("*CLS", "tx") in log_calls


# ---------------------------------------------------------------------------
# Debug mode — SYST:ERR? checking
# ---------------------------------------------------------------------------


class TestDebugMode:
    def test_debug_off_no_syst_err_query(self):
        stub, wrapper, log_calls = _make_wrapper()
        wrapper.debug = False
        stub._send_command("*RST")
        assert "SYST:ERR?" not in _messages(log_calls)

    def test_debug_on_queries_syst_err_after_command(self):
        stub, wrapper, log_calls = _make_wrapper()
        wrapper.debug = True
        stub._send_command("*RST")
        assert _messages(log_calls).count("SYST:ERR?") == 1

    def test_debug_on_queries_syst_err_after_query(self):
        stub, wrapper, log_calls = _make_wrapper({"BWID?": "70000\n"})
        wrapper.debug = True
        stub._query("BWID?")
        assert _messages(log_calls).count("SYST:ERR?") == 1

    def test_debug_logs_syst_err_at_debug_level(self):
        stub, wrapper, log_calls = _make_wrapper()
        wrapper.debug = True
        stub._send_command("*RST")
        assert ("SYST:ERR?", "tx/debug") in log_calls
        assert _levels(log_calls).count("rx/debug") == 1

    def test_debug_error_response_logged_at_error_level(self):
        """A non-zero SYST:ERR? response must produce an 'error' level entry."""
        responses = {
            "BAD:CMD": "ignored\n",
            "SYST:ERR?": '-113,"Undefined header"\n',
        }
        stub, wrapper, log_calls = _make_wrapper(responses)
        wrapper.debug = True
        stub._query("BAD:CMD")
        error_entries = [(msg, lvl) for msg, lvl in log_calls if lvl == "error"]
        assert len(error_entries) == 1
        assert "BAD:CMD" in error_entries[0][0]
        assert "-113" in error_entries[0][0]

    def test_debug_no_error_no_extra_log(self):
        """A +0 response to SYST:ERR? must NOT produce an 'error' entry."""
        stub, wrapper, log_calls = _make_wrapper({"BWID?": "70000\n"})
        wrapper.debug = True
        stub._query("BWID?")
        assert "error" not in _levels(log_calls)

    def test_debug_syst_err_exception_is_silenced(self):
        """If SYST:ERR? itself raises, the wrapper must not propagate."""
        stub = _StubDriver()
        log_calls: list[tuple[str, str]] = []
        wrapper = LoggingVNAWrapper(
            stub, lambda msg, level: log_calls.append((msg, level))
        )
        # Make the raw query raise
        wrapper._raw_query = lambda _: (_ for _ in ()).throw(OSError("broken"))
        wrapper.debug = True
        # Must not raise
        stub._send_command("*RST")


# ---------------------------------------------------------------------------
# Attribute delegation
# ---------------------------------------------------------------------------


class TestAttributeDelegation:
    def test_driver_name_delegated(self):
        _, wrapper, _ = _make_wrapper()
        assert wrapper.driver_name == "Stub"

    def test_idn_delegated(self):
        _, wrapper, _ = _make_wrapper()
        assert wrapper.idn == "STUB,MODEL,SN,FW"

    def test_is_connected_delegated(self):
        _, wrapper, _ = _make_wrapper()
        assert wrapper.is_connected() is True

    def test_unknown_attr_raises_attribute_error(self):
        _, wrapper, _ = _make_wrapper()
        with pytest.raises(AttributeError):
            _ = wrapper.nonexistent_attribute


# ---------------------------------------------------------------------------
# _raw_query bypass (no recursion in debug mode)
# ---------------------------------------------------------------------------


class TestRawQueryBypass:
    def test_raw_query_does_not_go_through_wrapper(self):
        """SYST:ERR? in debug mode must use _raw_query, not the patched _query."""
        stub = _StubDriver(
            {
                "SYST:ERR?": '+0,"No error"\n',
                "BWID?": "70000\n",
            }
        )
        log_calls: list[tuple[str, str]] = []
        wrapper = LoggingVNAWrapper(
            stub, lambda msg, level: log_calls.append((msg, level))
        )
        wrapper.debug = True

        stub._query("BWID?")

        # SYST:ERR? should appear exactly once in the query log (from _raw_query),
        # not twice (which would happen if it went through the patched _query again).
        assert _messages(log_calls).count("SYST:ERR?") == 1
