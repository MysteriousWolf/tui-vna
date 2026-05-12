"""Autocomplete helpers for setup and template inputs."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol, cast

from textual.widgets import Input
from textual_autocomplete import AutoComplete, DropdownItem
from textual_autocomplete._autocomplete import TargetState


@dataclass(slots=True, frozen=True)
class AutocompleteChoice:
    """Autocomplete option with explicit application behavior."""

    value: str
    kind: str
    label: str
    prefix: str | None = None


class _TemplateRefreshApp(Protocol):
    """Protocol for apps that can refresh export template validation."""

    def _refresh_export_template_validation(self) -> None: ...

    def call_after_refresh(
        self, callback: Callable[..., object], *args: object
    ) -> bool: ...


_KIND_SEP = "\x00"


def _build_dropdown_item(
    choice: AutocompleteChoice, *, key: str | None = None
) -> DropdownItem:
    """Build a dropdown item whose emitted value is *key* (defaults to choice.value)."""
    prefix_parts: list[str] = []
    if choice.prefix:
        prefix_parts.append(choice.prefix)
    if choice.label != choice.value:
        prefix_parts.append(f"{choice.label} ")
    prefix = "".join(prefix_parts) or None
    return DropdownItem(key if key is not None else choice.value, prefix=prefix)


class HistoryReplaceAutoComplete(AutoComplete):
    """Autocomplete for inputs where selecting a suggestion replaces the full value."""

    def __init__(
        self,
        target: Input | str,
        get_choices: Callable[[], list[AutocompleteChoice]],
        **kwargs,
    ) -> None:
        """Initialise with a target input and a callable that provides choices."""
        super().__init__(target=target, candidates=None, **kwargs)
        self._get_choices = get_choices

    def get_candidates(self, target_state: TargetState) -> list[DropdownItem]:
        """Return deduplicated dropdown items filtered by the current query."""
        query = target_state.text.strip().lower()
        seen: set[str] = set()
        items: list[DropdownItem] = []
        for choice in self._get_choices():
            if not choice.value or choice.value in seen:
                continue
            seen.add(choice.value)
            if (
                query
                and query not in choice.label.lower()
                and query not in choice.value.lower()
            ):
                continue
            items.append(_build_dropdown_item(choice))
        return items


class TemplateAutoComplete(AutoComplete):
    """Autocomplete for template inputs with whole-value and tag insertion completions."""

    def __init__(
        self,
        target: Input | str,
        get_choices: Callable[[], list[AutocompleteChoice]],
        **kwargs,
    ) -> None:
        """Initialise with a target input and a callable that provides template choices."""
        super().__init__(target=target, candidates=None, **kwargs)
        self._get_choices = get_choices

    def get_candidates(self, target_state: TargetState) -> list[DropdownItem]:
        """Return deduplicated dropdown items filtered by the token near the cursor."""
        search = self.get_search_string(target_state).lower().strip()
        seen: set[tuple[str, str]] = set()
        items: list[DropdownItem] = []
        for choice in self._get_choices():
            dedup_key = (choice.kind, choice.value)
            if dedup_key in seen:
                continue
            seen.add(dedup_key)
            haystack = f"{choice.label} {choice.value}".lower()
            if search and search not in haystack:
                continue
            # Encode kind into the emitted key so apply_completion can uniquely
            # resolve a choice even when a "history" and a "tag" share the same value.
            emitted_key = f"{choice.kind}{_KIND_SEP}{choice.value}"
            items.append(_build_dropdown_item(choice, key=emitted_key))
        return items

    def get_search_string(self, target_state: TargetState) -> str:
        """Search only the current token-ish fragment around the cursor."""
        text = target_state.text[: target_state.cursor_position]
        token_start = max(text.rfind("{"), text.rfind(" "))
        if token_start == -1:
            return text
        return text[token_start:]

    def apply_completion(self, value: str, state: TargetState) -> None:
        """Apply either a whole-template replacement or a tag insertion."""
        target = self.target
        # Decode the kind-encoded key emitted by get_candidates to pick the
        # correct choice when a history and a tag share the same value string.
        if _KIND_SEP in value:
            kind, actual_value = value.split(_KIND_SEP, 1)
            choice = next(
                (
                    c
                    for c in self._get_choices()
                    if c.kind == kind and c.value == actual_value
                ),
                None,
            )
        else:
            actual_value = value
            choice = next(
                (c for c in self._get_choices() if c.value == actual_value), None
            )
        if choice is None:
            super().apply_completion(actual_value, state)
            target.cursor_position = len(target.value)
            return

        if choice.kind == "history":
            target.value = actual_value
            target.cursor_position = len(actual_value)
        else:
            cursor = state.cursor_position
            before = state.text[:cursor]
            after = state.text[cursor:]
            token_start = max(before.rfind("{"), before.rfind(" "))
            if token_start == -1:
                token_start = 0
            elif before[token_start] == " ":
                token_start += 1

            token_end = 0
            if after.startswith("}"):
                token_end = 1

            target.value = before[:token_start] + actual_value + after[token_end:]
            target.cursor_position = token_start + len(actual_value)

        new_target_state = self._get_target_state()
        self.rebuild_options(new_target_state)

    def rebuild_options(self, target_state: TargetState | None = None) -> None:
        """Rebuild the dropdown options for the current or given target state.

        Wraps the upstream private _rebuild_options so callers use a stable method.
        # TODO: open an issue against textual_autocomplete to expose a public rebuild hook.
        """
        if target_state is None:
            target_state = self._get_target_state()
        self._rebuild_options(target_state, self.get_search_string(target_state))

    def post_completion(self) -> None:
        """Hide the dropdown and refresh dependent previews after completion."""
        super().post_completion()
        app = self.app
        if hasattr(app, "_refresh_export_template_validation") and hasattr(
            app, "call_after_refresh"
        ):
            typed_app = cast(_TemplateRefreshApp, app)
            typed_app.call_after_refresh(typed_app._refresh_export_template_validation)
