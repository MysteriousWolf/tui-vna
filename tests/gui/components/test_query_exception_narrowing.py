"""Focused tests for query lookup exception narrowing in GUI components."""

from __future__ import annotations

import pytest
from textual.css.query import NoMatches, WrongType

from tina.gui.components.frequency_entry import FrequencyEntry
from tina.gui.components.status_footer import StatusFooter


class _StatusFooterNoMatches(StatusFooter):
    """Status footer test double that always raises NoMatches."""

    def query_one(self, *args, **kwargs):
        raise NoMatches("#sb_cal")


class _StatusFooterWrongType(StatusFooter):
    """Status footer test double that always raises WrongType."""

    def query_one(self, *args, **kwargs):
        raise WrongType("#sb_cal")


class _StatusFooterRuntimeError(StatusFooter):
    """Status footer test double that always raises RuntimeError."""

    def query_one(self, *args, **kwargs):
        raise RuntimeError("boom")


class _FrequencyEntryNoMatches(FrequencyEntry):
    """FrequencyEntry test double that always raises NoMatches."""

    def query_one(self, *args, **kwargs):
        raise NoMatches("#input_frequency")


class _FrequencyEntryWrongType(FrequencyEntry):
    """FrequencyEntry test double that always raises WrongType."""

    def query_one(self, *args, **kwargs):
        raise WrongType("#btn_freq_minima")


class _FrequencyEntryRuntimeError(FrequencyEntry):
    """FrequencyEntry test double that always raises RuntimeError."""

    def query_one(self, *args, **kwargs):
        raise RuntimeError("boom")


@pytest.mark.unit
class TestStatusFooterQueryExceptionNarrowing:
    """Status footer should ignore only expected query lookup failures."""

    def test_set_item_ignores_missing_widget_lookup(self) -> None:
        """Missing status chips should not raise during best-effort updates."""
        footer = _StatusFooterNoMatches()

        footer._set_item("sb_cal", "CAL", "--state-ok")

        assert footer._sb_state["sb_cal"] == ("CAL", "--state-ok")

    def test_set_item_ignores_wrong_type_lookup(self) -> None:
        """Wrong-type query results should be treated like absent status chips."""
        footer = _StatusFooterWrongType()

        footer._set_item("sb_cal", "CAL", "--state-ok")

        assert footer._sb_state["sb_cal"] == ("CAL", "--state-ok")

    def test_set_item_does_not_swallow_unexpected_runtime_errors(self) -> None:
        """Unexpected runtime failures should surface instead of being hidden."""
        footer = _StatusFooterRuntimeError()

        with pytest.raises(RuntimeError, match="boom"):
            footer._set_item("sb_cal", "CAL", "--state-ok")


@pytest.mark.unit
class TestFrequencyEntryQueryExceptionNarrowing:
    """FrequencyEntry should ignore only expected Textual lookup failures."""

    def test_set_frequency_hz_ignores_missing_input_lookup(self) -> None:
        """Clearing or setting frequency should tolerate an unmounted input."""
        entry = _FrequencyEntryNoMatches()

        entry.set_frequency_hz(1.0)

        assert entry.get_frequency_hz() is None

    def test_update_toggle_visual_ignores_wrong_type_lookup(self) -> None:
        """Toggle visual updates should ignore wrong-type query results."""
        entry = _FrequencyEntryWrongType()

        entry._update_toggle_visual(entry.minima_toggle_id, True)

        assert entry._minima_mode is False

    def test_set_frequency_hz_does_not_swallow_unexpected_runtime_errors(self) -> None:
        """Unexpected query failures should propagate to callers."""
        entry = _FrequencyEntryRuntimeError()

        with pytest.raises(RuntimeError, match="boom"):
            entry.set_frequency_hz(1.0)
