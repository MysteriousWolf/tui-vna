"""Tests for the mock VISA fixture helpers."""

import pytest

from tests.fixtures.mock_visa import MockVisaResource


class TestMockVisaResource:
    """Validate SCPI normalization and active-parameter tracking."""

    @pytest.mark.unit
    def test_normalizes_prefixes_for_commands_and_queries(self):
        """Leading colons should not affect recognized SCPI commands."""
        resource = MockVisaResource()

        resource.write("SENS1:FREQ:STAR 123")
        assert resource.query(":SENS1:FREQ:STAR?") == "123.0"

        resource.write(":SENS1:FREQ:STOP 456")
        assert resource.query("SENS1:FREQ:STOP?") == "456.0"

    @pytest.mark.unit
    def test_updates_active_param_for_parameter_selection(self):
        """Parameter selection commands should update the active parameter."""
        resource = MockVisaResource()

        resource.write("CALC1:PAR2:SEL")
        assert resource._active_param == 2

        resource.write(":CALC1:PAR:SEL 'S22'")
        assert resource._active_param == 4

        resource.write("CALC1:PAR:SEL 'CH1_S11'")
        assert resource._active_param == 1
