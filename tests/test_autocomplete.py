"""Tests for setup autocomplete behavior."""

from src.tina.main import (
    HistoryReplaceAutoComplete,
    TemplateAutoComplete,
    _AutocompleteChoice,
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
        super().__init__(self._fake_target, lambda: choices)

    @property
    def target(self) -> _FakeTarget:
        return self._fake_target


class _TemplateAutoCompleteUnderTest(TemplateAutoComplete):
    """Template autocomplete with a fake target for isolated unit tests."""

    def __init__(
        self, choices: list[_AutocompleteChoice], target_value: str = ""
    ) -> None:
        self._fake_target = _FakeTarget(target_value)
        super().__init__(self._fake_target, lambda: choices)

    @property
    def target(self) -> _FakeTarget:
        return self._fake_target

    def _get_target_state(self) -> _FakeState:
        return _FakeState(self.target.value, self.target.cursor_position)

    def _rebuild_options(self, *_args, **_kwargs) -> None:
        """No-op rebuild for unit tests."""
        return


class TestHistoryReplaceAutoComplete:
    """Tests for full-value replacement autocomplete behavior."""

    def test_get_candidates_filters_history_entries(self):
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

        candidates = autocomplete.get_candidates(_FakeState("lab", 3))

        assert [item.value for item in candidates] == ["lab-vna.local"]

    def test_get_candidates_ignores_duplicate_values(self):
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

        candidates = autocomplete.get_candidates(_FakeState("inst", 4))

        assert [item.value for item in candidates] == ["inst0"]


class TestTemplateAutoComplete:
    """Tests for template autocomplete behavior."""

    def test_get_search_string_uses_current_token_fragment(self):
        autocomplete = _TemplateAutoCompleteUnderTest([])

        search = autocomplete.get_search_string(
            _FakeState("measurement_{da", len("measurement_{da"))
        )

        assert search == "{da"

    def test_get_search_string_falls_back_to_full_text_without_token(self):
        autocomplete = _TemplateAutoCompleteUnderTest([])

        search = autocomplete.get_search_string(_FakeState("measure", len("measure")))

        assert search == "measure"

    def test_get_candidates_include_matching_history_and_tags(self):
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
            _FakeState("measurement_{da", len("measurement_{da"))
        )

        assert [item.value for item in candidates] == [
            "measurement_{date}_{time}",
            "{date}",
        ]

    def test_history_completion_replaces_entire_value(self):
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
            _FakeState("partial_name", len("partial_name")),
        )

        assert autocomplete.target.value == "measurement_{date}_{time}"
        assert autocomplete.target.cursor_position == len("measurement_{date}_{time}")

    def test_tag_completion_replaces_only_current_fragment(self):
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
            _FakeState("measurement_{da}_suffix", len("measurement_{da")),
        )

        assert autocomplete.target.value == "measurement_{date}_suffix"
        assert autocomplete.target.cursor_position == len("measurement_{date}")

    def test_tag_completion_inserts_when_no_token_prefix_exists(self):
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
            _FakeState("prefix ", len("prefix ")),
        )

        assert autocomplete.target.value == "prefix {host}"
        assert autocomplete.target.cursor_position == len("prefix {host}")

    def test_get_candidates_deduplicates_same_kind_and_value(self):
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

        candidates = autocomplete.get_candidates(_FakeState("{da", 3))

        assert [item.value for item in candidates] == ["{date}", "measurement_{date}"]
