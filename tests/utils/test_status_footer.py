"""Unit tests for status_footer helpers."""

import pytest


class TestScpiMnemonic:
    """Tests for the _scpi_mnemonic() display helper in the status footer module."""

    @pytest.fixture(autouse=True)
    def _import(self):
        from tina.gui.components.status_footer import _scpi_mnemonic

        self.mnem = _scpi_mnemonic

    def test_strips_query_mark(self):
        """Query marker '?' should be removed from command strings."""
        assert self.mnem("BWID?") == "BWID"

    def test_strips_channel_prefix(self):
        """SENS<ch>: prefix should be stripped from multi-node commands."""
        assert self.mnem("SENS1:CORR:STAT?") == "CORR:STAT"

    def test_strips_channel_prefix_calc(self):
        """CALC<ch>: prefix should be stripped from calculation commands."""
        assert self.mnem("CALC1:SMO:APER?") == "SMO:APER"

    def test_no_channel_prefix_left_intact(self):
        """Commands without channel prefixes should remain unchanged."""
        assert self.mnem("TRIG:SOUR?") == "TRIG:SOUR"

    def test_star_command(self):
        """Star commands like *RST should remain unchanged."""
        assert self.mnem("*RST") == "*RST"

    def test_strips_parameter_value(self):
        """Parameter values should be stripped, leaving only the parameter name."""
        assert self.mnem("SOUR1:POW -10") == "POW"

    def test_single_node_with_channel(self):
        """Single-node commands with channel prefixes should strip the prefix."""
        assert self.mnem("SENS1:BWID?") == "BWID"
