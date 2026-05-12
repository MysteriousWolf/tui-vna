"""Compose-level tests for the Log tab UI."""

from __future__ import annotations

import pytest
from textual.app import App, ComposeResult
from textual.widgets import Checkbox, RichLog

from tina.gui.tabs.log import compose_log_tab


class _LogTabApp(App):
    """Minimal Textual app that renders the log tab for inspection."""

    def compose(self) -> ComposeResult:
        yield from compose_log_tab()


@pytest.mark.unit
class TestComposeLogTab:
    """Smoke tests for the Log tab composition contract."""

    @pytest.mark.asyncio
    async def test_primary_filter_checkboxes_exist_and_default_true(self) -> None:
        """Primary filter checkboxes must be present and default to True."""
        async with _LogTabApp().run_test() as pilot:
            for checkbox_id in (
                "check_log_tx",
                "check_log_rx",
                "check_log_info",
                "check_log_progress",
                "check_log_success",
                "check_log_error",
            ):
                cb = pilot.app.query_one(f"#{checkbox_id}", Checkbox)
                assert cb.value is True, f"#{checkbox_id} should default to True"

    @pytest.mark.asyncio
    async def test_secondary_filter_checkboxes_exist_and_default_false(self) -> None:
        """Secondary filter checkboxes must be present and default to False."""
        async with _LogTabApp().run_test() as pilot:
            for checkbox_id in ("check_log_debug", "check_log_poll"):
                cb = pilot.app.query_one(f"#{checkbox_id}", Checkbox)
                assert cb.value is False, f"#{checkbox_id} should default to False"

    @pytest.mark.asyncio
    async def test_log_content_richlog_is_present(self) -> None:
        """A RichLog with id 'log_content' must be composed."""
        async with _LogTabApp().run_test() as pilot:
            pilot.app.query_one("#log_content", RichLog)

    @pytest.mark.asyncio
    async def test_log_content_border_title_contains_copy_action(self) -> None:
        """The log area border_title must wire the copy action markup."""
        async with _LogTabApp().run_test() as pilot:
            log_area = pilot.app.query_one("#log_content", RichLog)
            assert "copy_log" in (log_area.border_title or "")
