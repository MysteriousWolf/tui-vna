"""Smoke test for the compose_tools_tab() composer."""

from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING

import pytest
from textual.app import App, ComposeResult
from textual.widgets import Select

from tina.gui.tabs.tools import compose_tools_tab

if TYPE_CHECKING:
    pass


class _FakeSettings(SimpleNamespace):
    """Minimal settings stub for compose_tools_tab."""

    tools_plot_type: str = "magnitude"
    tools_trace: str = "S21"


class _ToolsTabApp(App):
    """Minimal Textual app that renders the tools tab for inspection."""

    def __init__(self) -> None:
        super().__init__()
        self.settings = _FakeSettings()
        self.last_measurement = None

    def compose(self) -> ComposeResult:
        """Delegate to compose_tools_tab."""
        yield from compose_tools_tab(self)  # type: ignore[arg-type]


@pytest.mark.unit
class TestComposeToolsTab:
    """Smoke tests for the Tools tab composition contract."""

    @pytest.mark.asyncio
    async def test_select_tools_plot_type_defaults_to_magnitude(self) -> None:
        """Select widget should default to magnitude when settings are absent."""
        async with _ToolsTabApp().run_test() as pilot:
            select = pilot.app.query_one("#select_tools_plot_type", Select)
            assert select.value == "magnitude"

    @pytest.mark.asyncio
    async def test_tools_params_containers_are_present(self) -> None:
        """Dynamic and placeholder param containers must be mounted."""
        async with _ToolsTabApp().run_test() as pilot:
            pilot.app.query_one("#tools_params_dynamic")
            pilot.app.query_one("#tools_params_placeholder")

    @pytest.mark.asyncio
    async def test_cursor_input_ids_are_present(self) -> None:
        """Cursor frequency inputs must be mounted with stable IDs."""
        async with _ToolsTabApp().run_test() as pilot:
            for widget_id in (
                "input_tools_cursor1",
                "input_tools_cursor2",
                "btn_freq1_prev",
                "btn_freq1_next",
                "btn_freq2_prev",
                "btn_freq2_next",
            ):
                pilot.app.query_one(f"#{widget_id}")
