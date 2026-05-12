"""Unit tests for log_logic helpers."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from tina.gui.tabs.log_logic import (
    MAX_LOG_HISTORY,
    build_style_map,
    copy_log,
    format_log_entry,
    log_message,
    refresh_log_display,
    should_show_log,
)


class _FakeCheckbox:
    def __init__(self, value: bool) -> None:
        self.value = value


class _FakeRichLog:
    def __init__(self) -> None:
        self.lines: list[str] = []
        self.cleared = False

    def clear(self) -> None:
        self.cleared = True
        self.lines = []

    def write(self, text: str) -> None:
        self.lines.append(text)

    def scroll_end(self, animate: bool = True) -> None:
        pass


def _make_app(
    *,
    css_vars: dict | None = None,
    checkboxes: dict | None = None,
    log_content: _FakeRichLog | None = None,
):
    """Build a minimal app stub for log_logic tests."""
    rich_log = log_content or _FakeRichLog()
    checks = checkboxes or {}

    def query_one(selector, _widget_type=None):
        if selector == "#log_content":
            return rich_log
        if selector in checks:
            return checks[selector]
        raise AssertionError(f"Unexpected selector: {selector}")

    app = SimpleNamespace(
        get_css_variables=lambda: css_vars or {},
        _cached_style_map=None,
        query_one=query_one,
        log_messages=[],
        copy_to_clipboard=MagicMock(),
        notify=MagicMock(),
    )
    return app, rich_log


@pytest.mark.unit
class TestBuildStyleMap:
    def test_uses_css_var_accent_for_tx(self):
        """build_style_map should use the 'accent' CSS variable for the tx icon style."""
        app, _ = _make_app(css_vars={"accent": "#aabbcc"})
        style_map = build_style_map(app)
        assert style_map["tx"][1] == "#aabbcc"

    def test_falls_back_to_constants_when_vars_absent(self):
        """build_style_map falls back to THEME_* constants when CSS vars are missing."""
        from tina.config.constants import THEME_ACCENT

        app, _ = _make_app(css_vars={})
        style_map = build_style_map(app)
        assert style_map["tx"][1] == THEME_ACCENT

    def test_compound_levels_exist(self):
        """Compound levels like tx/poll and rx/poll must be present in the style map."""
        app, _ = _make_app()
        style_map = build_style_map(app)
        assert "tx/poll" in style_map
        assert "rx/poll" in style_map


@pytest.mark.unit
class TestFormatLogEntry:
    def test_escapes_rich_markup_in_message(self):
        """format_log_entry must escape markup characters in the log message."""
        app, _ = _make_app()
        app._cached_style_map = build_style_map(app)
        entry = {
            "timestamp": "12:00:00",
            "level": "info",
            "message": "a [bold]b[/bold]",
        }
        result = format_log_entry(app, entry)
        # rich_escape turns [bold] into \[bold] — the bracket is escaped, not stripped
        assert r"\[bold]" in result
        assert "a" in result

    def test_uses_cached_style_map(self):
        """format_log_entry should build and cache the style_map on first call."""
        app, _ = _make_app()
        assert app._cached_style_map is None
        entry = {"timestamp": "12:00:00", "level": "error", "message": "oops"}
        format_log_entry(app, entry)
        assert app._cached_style_map is not None


@pytest.mark.unit
class TestShouldShowLog:
    def test_simple_level_shown_when_checkbox_true(self):
        """A simple level is shown when its filter checkbox is checked."""
        checks = {"#check_log_info": _FakeCheckbox(True)}
        app, _ = _make_app(checkboxes=checks)
        assert should_show_log(app, "info") is True

    def test_simple_level_hidden_when_checkbox_false(self):
        """A simple level is hidden when its filter checkbox is unchecked."""
        checks = {"#check_log_info": _FakeCheckbox(False)}
        app, _ = _make_app(checkboxes=checks)
        assert should_show_log(app, "info") is False

    def test_compound_level_requires_both_checkboxes(self):
        """tx/poll is shown only when both tx and poll checkboxes are checked."""
        checks = {
            "#check_log_tx": _FakeCheckbox(True),
            "#check_log_poll": _FakeCheckbox(False),
        }
        app, _ = _make_app(checkboxes=checks)
        assert should_show_log(app, "tx/poll") is False

    def test_compound_level_shown_when_both_checked(self):
        """tx/poll is shown when both tx and poll checkboxes are checked."""
        checks = {
            "#check_log_tx": _FakeCheckbox(True),
            "#check_log_poll": _FakeCheckbox(True),
        }
        app, _ = _make_app(checkboxes=checks)
        assert should_show_log(app, "tx/poll") is True

    def test_unknown_level_always_shown(self):
        """An unrecognised level without a filter ID is always shown."""
        app, _ = _make_app()
        assert should_show_log(app, "unknown_level") is True


@pytest.mark.unit
class TestLogMessage:
    def test_appends_entry_to_log_messages(self):
        """log_message must append a new entry to app.log_messages."""
        app, _ = _make_app()
        log_message(app, "hello", level="info")
        assert len(app.log_messages) == 1
        assert app.log_messages[0]["message"] == "hello"
        assert app.log_messages[0]["level"] == "info"

    def test_enforces_max_log_history_fifo(self):
        """Exceeding MAX_LOG_HISTORY should trim oldest entries from the front."""
        app, _ = _make_app()
        for i in range(MAX_LOG_HISTORY + 5):
            app.log_messages.append(
                {"timestamp": "00:00:00", "level": "info", "message": f"msg{i}"}
            )
        log_message(app, "new", level="info")
        assert len(app.log_messages) == MAX_LOG_HISTORY

    def test_writes_to_richlog_when_level_shown(self):
        """log_message writes to the RichLog widget when the level passes its filter."""
        rich_log = _FakeRichLog()
        checks = {"#check_log_info": _FakeCheckbox(True)}
        app, _ = _make_app(checkboxes=checks, log_content=rich_log)
        log_message(app, "visible", level="info")
        assert any("visible" in line for line in rich_log.lines)

    def test_does_not_write_to_richlog_when_level_hidden(self):
        """log_message must not write to the RichLog widget when the level is filtered out."""
        rich_log = _FakeRichLog()
        checks = {"#check_log_info": _FakeCheckbox(False)}
        app, _ = _make_app(checkboxes=checks, log_content=rich_log)
        log_message(app, "hidden", level="info")
        assert not rich_log.lines


@pytest.mark.unit
class TestRefreshLogDisplay:
    def test_clears_and_rebuilds_visible_lines(self):
        """refresh_log_display must clear the widget then write only visible entries."""
        rich_log = _FakeRichLog()
        checks = {
            "#check_log_info": _FakeCheckbox(True),
            "#check_log_error": _FakeCheckbox(False),
        }
        app, _ = _make_app(checkboxes=checks, log_content=rich_log)
        app.log_messages = [
            {"timestamp": "00:00:00", "level": "info", "message": "shown"},
            {"timestamp": "00:00:01", "level": "error", "message": "hidden"},
        ]
        refresh_log_display(app)
        assert rich_log.cleared
        assert len(rich_log.lines) == 1
        assert "shown" in rich_log.lines[0]


@pytest.mark.unit
class TestCopyLog:
    def test_produces_plain_text_and_calls_clipboard(self):
        """copy_log should produce plain-text lines and invoke copy_to_clipboard."""
        checks = {"#check_log_info": _FakeCheckbox(True)}
        app, _ = _make_app(checkboxes=checks)
        app.log_messages = [
            {"timestamp": "12:00:00", "level": "info", "message": "test msg"},
        ]
        copy_log(app)
        app.copy_to_clipboard.assert_called_once()
        text = app.copy_to_clipboard.call_args[0][0]
        assert "test msg" in text
        app.notify.assert_called_once()

    def test_caches_style_map(self):
        """copy_log should populate _cached_style_map when it is falsy."""
        app, _ = _make_app()
        assert app._cached_style_map is None
        copy_log(app)
        assert app._cached_style_map is not None
