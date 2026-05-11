"""Tests for setup autocomplete behavior."""

from typing import cast

import pytest
from textual.widgets import Input
from textual_autocomplete._autocomplete import TargetState

from tina.gui.components.autocomplete import (
    AutocompleteChoice as _AutocompleteChoice,
)
from tina.gui.components.autocomplete import (
    HistoryReplaceAutoComplete,
    TemplateAutoComplete,
)


class _FakeTarget:
    """Minimal input-like object for autocomplete unit tests."""

    def __init__(self, value: str = "", cursor_position: int | None = None) -> None:
        self.value = value
        self.cursor_position = (
            len(value) if cursor_position is None else cursor_position
        )


class _FakeState:
    """Minimal target state compatible with autocomplete helper methods."""

    def __init__(self, text: str, cursor_position: int) -> None:
        self.text = text
        self.cursor_position = cursor_position


class _HistoryReplaceAutoCompleteUnderTest(HistoryReplaceAutoComplete):
    """History autocomplete with a fake target for isolated unit tests."""

    def __init__(
        self, choices: list[_AutocompleteChoice], target_value: str = ""
    ) -> None:
        self._fake_target = _FakeTarget(target_value)
        super().__init__(cast(Input, self._fake_target), lambda: choices)

    @property
    def target(self) -> Input:
        return cast(Input, self._fake_target)


class _TemplateAutoCompleteUnderTest(TemplateAutoComplete):
    """Template autocomplete with a fake target for isolated unit tests."""

    def __init__(
        self, choices: list[_AutocompleteChoice], target_value: str = ""
    ) -> None:
        self._fake_target = _FakeTarget(target_value)
        super().__init__(cast(Input, self._fake_target), lambda: choices)

    @property
    def target(self) -> Input:
        return cast(Input, self._fake_target)

    def _get_target_state(self) -> TargetState:
        return cast(
            TargetState,
            _FakeState(self._fake_target.value, self._fake_target.cursor_position),
        )

    def _rebuild_options(self, *_args, **_kwargs) -> None:
        """No-op rebuild for unit tests."""
        return


class TestHistoryReplaceAutoComplete:
    """Tests for full-value replacement autocomplete behavior."""

    @pytest.mark.unit
    def test_get_candidates_filters_history_entries(self):
        """History entries not matching the prefix should be excluded from candidates."""
        choices = [
            _AutocompleteChoice(
                value="192.168.1.100",
                kind="history",
                label="192.168.1.100",
                prefix="↺ ",
            ),
            _AutocompleteChoice(
                value="lab-vna.local",
                kind="history",
                label="lab-vna.local",
                prefix="↺ ",
            ),
        ]
        autocomplete = _HistoryReplaceAutoCompleteUnderTest(choices)

        candidates = autocomplete.get_candidates(
            cast(TargetState, _FakeState("lab", 3))
        )

        assert [item.value for item in candidates] == ["lab-vna.local"]

    @pytest.mark.unit
    def test_get_candidates_ignores_duplicate_values(self):
        """Duplicate history values should appear only once in the candidate list."""
        choices = [
            _AutocompleteChoice(
                value="inst0",
                kind="history",
                label="inst0",
                prefix="↺ ",
            ),
            _AutocompleteChoice(
                value="inst0",
                kind="history",
                label="inst0",
                prefix="↺ ",
            ),
        ]
        autocomplete = _HistoryReplaceAutoCompleteUnderTest(choices)

        candidates = autocomplete.get_candidates(
            cast(TargetState, _FakeState("inst", 4))
        )

        assert [item.value for item in candidates] == ["inst0"]

    @pytest.mark.unit
    def test_get_candidates_emit_canonical_value_when_label_differs(self):
        """Candidates should expose the canonical value even when the display label differs."""
        choices = [
            _AutocompleteChoice(
                value="main.plain",
                kind="history",
                label="Main Plain",
                prefix="↺ ",
            ),
        ]
        autocomplete = _HistoryReplaceAutoCompleteUnderTest(choices)

        candidates = autocomplete.get_candidates(
            cast(TargetState, _FakeState("main", 4))
        )

        assert [item.value for item in candidates] == ["main.plain"]


class TestTemplateAutoComplete:
    """Tests for template autocomplete behavior."""

    @pytest.mark.unit
    def test_get_search_string_uses_current_token_fragment(self):
        """Search string should return the fragment from the last { or space to the cursor."""
        autocomplete = _TemplateAutoCompleteUnderTest([])

        search = autocomplete.get_search_string(
            cast(TargetState, _FakeState("measurement_{da", len("measurement_{da")))
        )

        assert search == "{da"

    @pytest.mark.unit
    def test_get_search_string_falls_back_to_full_text_without_token(self):
        """Search string should fall back to full text when no token delimiter is present."""
        autocomplete = _TemplateAutoCompleteUnderTest([])

        search = autocomplete.get_search_string(
            cast(TargetState, _FakeState("measure", len("measure")))
        )

        assert search == "measure"

    @pytest.mark.unit
    def test_get_candidates_include_matching_history_and_tags(self):
        """Both history and tag candidates matching the search string should be returned."""
        choices = [
            _AutocompleteChoice(
                value="measurement_{date}_{time}",
                kind="history",
                label="measurement_{date}_{time}",
                prefix="↺ ",
            ),
            _AutocompleteChoice(
                value="{date}",
                kind="tag",
                label="{date}",
                prefix="# ",
            ),
            _AutocompleteChoice(
                value="{time}",
                kind="tag",
                label="{time}",
                prefix="# ",
            ),
        ]
        autocomplete = _TemplateAutoCompleteUnderTest(choices)

        candidates = autocomplete.get_candidates(
            cast(TargetState, _FakeState("measurement_{da", len("measurement_{da")))
        )

        assert [item.value for item in candidates] == [
            "history\x00measurement_{date}_{time}",
            "tag\x00{date}",
        ]

    @pytest.mark.unit
    def test_history_completion_replaces_entire_value(self):
        """Selecting a history entry should replace the whole input value."""
        choices = [
            _AutocompleteChoice(
                value="measurement_{date}_{time}",
                kind="history",
                label="measurement_{date}_{time}",
                prefix="↺ ",
            ),
            _AutocompleteChoice(
                value="{date}",
                kind="tag",
                label="{date}",
                prefix="# ",
            ),
        ]
        autocomplete = _TemplateAutoCompleteUnderTest(
            choices,
            target_value="partial_name",
        )

        autocomplete.apply_completion(
            "measurement_{date}_{time}",
            cast(TargetState, _FakeState("partial_name", len("partial_name"))),
        )

        assert autocomplete.target.value == "measurement_{date}_{time}"
        assert autocomplete.target.cursor_position == len("measurement_{date}_{time}")

    @pytest.mark.unit
    def test_tag_completion_replaces_only_current_fragment(self):
        """Selecting a tag should replace only the current {fragment} around the cursor."""
        choices = [
            _AutocompleteChoice(
                value="{date}",
                kind="tag",
                label="{date}",
                prefix="# ",
            ),
        ]
        autocomplete = _TemplateAutoCompleteUnderTest(
            choices,
            target_value="measurement_{da}_suffix",
        )
        autocomplete.target.cursor_position = len("measurement_{da")

        autocomplete.apply_completion(
            "{date}",
            cast(
                TargetState,
                _FakeState("measurement_{da}_suffix", len("measurement_{da")),
            ),
        )

        assert autocomplete.target.value == "measurement_{date}_suffix"
        assert autocomplete.target.cursor_position == len("measurement_{date}")

    @pytest.mark.unit
    def test_tag_completion_inserts_when_no_token_prefix_exists(self):
        """Tag completion should insert at the cursor when no { prefix is present."""
        choices = [
            _AutocompleteChoice(
                value="{host}",
                kind="tag",
                label="{host}",
                prefix="# ",
            ),
        ]
        autocomplete = _TemplateAutoCompleteUnderTest(
            choices,
            target_value="prefix ",
        )
        autocomplete.target.cursor_position = len("prefix ")

        autocomplete.apply_completion(
            "{host}",
            cast(TargetState, _FakeState("prefix ", len("prefix "))),
        )

        assert autocomplete.target.value == "prefix {host}"
        assert autocomplete.target.cursor_position == len("prefix {host}")

    @pytest.mark.unit
    def test_get_candidates_deduplicates_same_kind_and_value(self):
        """Identical kind+value pairs should appear only once in the candidate list."""
        choices = [
            _AutocompleteChoice(
                value="{date}",
                kind="tag",
                label="{date}",
                prefix="# ",
            ),
            _AutocompleteChoice(
                value="{date}",
                kind="tag",
                label="{date}",
                prefix="# ",
            ),
            _AutocompleteChoice(
                value="measurement_{date}",
                kind="history",
                label="measurement_{date}",
                prefix="↺ ",
            ),
        ]
        autocomplete = _TemplateAutoCompleteUnderTest(choices)

        candidates = autocomplete.get_candidates(
            cast(TargetState, _FakeState("{da", 3))
        )

        assert [item.value for item in candidates] == [
            "tag\x00{date}",
            "history\x00measurement_{date}",
        ]

    @pytest.mark.unit
    def test_tag_completion_uses_canonical_value_when_label_differs(self):
        """Tag completion should insert the canonical value, not the display label."""
        choices = [
            _AutocompleteChoice(
                value="main.plain",
                kind="tag",
                label="Main Plain",
                prefix="# ",
            ),
        ]
        autocomplete = _TemplateAutoCompleteUnderTest(
            choices,
            target_value="theme={mai}",
        )
        autocomplete.target.cursor_position = len("theme={mai")

        autocomplete.apply_completion(
            "main.plain",
            cast(TargetState, _FakeState("theme={mai}", len("theme={mai"))),
        )

        assert autocomplete.target.value == "theme=main.plain"
        assert autocomplete.target.cursor_position == len("theme=main.plain")
