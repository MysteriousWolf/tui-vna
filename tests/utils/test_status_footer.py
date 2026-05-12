"""Unit tests for status_footer helpers."""

import pytest

from tina.gui.components.status_footer import _scpi_mnemonic


@pytest.mark.unit
class TestScpiMnemonic:
    """Tests for the _scpi_mnemonic() display helper in the status footer module."""

    def test_strips_query_mark(self):
        """Query marker '?' should be removed from command strings."""
        assert _scpi_mnemonic("BWID?") == "BWID"

    def test_strips_channel_prefix(self):
        """SENS<ch>: prefix should be stripped from multi-node commands."""
        assert _scpi_mnemonic("SENS1:CORR:STAT?") == "CORR:STAT"

    def test_strips_channel_prefix_calc(self):
        """CALC<ch>: prefix should be stripped from calculation commands."""
        assert _scpi_mnemonic("CALC1:SMO:APER?") == "SMO:APER"

    def test_no_channel_prefix_left_intact(self):
        """Commands without channel prefixes should remain unchanged."""
        assert _scpi_mnemonic("TRIG:SOUR?") == "TRIG:SOUR"

    def test_star_command(self):
        """Star commands like *RST should remain unchanged."""
        assert _scpi_mnemonic("*RST") == "*RST"

    def test_strips_parameter_value(self):
        """Parameter values should be stripped, leaving only the parameter name."""
        assert _scpi_mnemonic("SOUR1:POW -10") == "POW"

    def test_single_node_with_channel(self):
        """Single-node commands with channel prefixes should strip the prefix."""
        assert _scpi_mnemonic("SENS1:BWID?") == "BWID"

    def test_leading_colon_stripped(self):
        """Optional leading ':' should be ignored before channel-prefix stripping."""
        assert _scpi_mnemonic(":SENS1:CORR:STAT?") == "CORR:STAT"
        assert _scpi_mnemonic(":SENS1:BWID?") == "BWID"
        assert _scpi_mnemonic(":CALC1:SMO:APER?") == "SMO:APER"
