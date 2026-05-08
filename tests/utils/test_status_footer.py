"""Unit tests for status_footer helpers."""

import pytest


class TestScpiMnemonic:
    """Tests for the _scpi_mnemonic() display helper in the status footer module."""

    @pytest.fixture(autouse=True)
    def _import(self):
        from tina.gui.components.status_footer import _scpi_mnemonic

        self.mnem = _scpi_mnemonic

    def test_strips_query_mark(self):
        assert self.mnem("BWID?") == "BWID"

    def test_strips_channel_prefix(self):
        assert self.mnem("SENS1:CORR:STAT?") == "CORR:STAT"

    def test_strips_channel_prefix_calc(self):
        assert self.mnem("CALC1:SMO:APER?") == "SMO:APER"

    def test_no_channel_prefix_left_intact(self):
        assert self.mnem("TRIG:SOUR?") == "TRIG:SOUR"

    def test_star_command(self):
        assert self.mnem("*RST") == "*RST"

    def test_strips_parameter_value(self):
        assert self.mnem("SOUR1:POW -10") == "POW"

    def test_single_node_with_channel(self):
        assert self.mnem("SENS1:BWID?") == "BWID"
