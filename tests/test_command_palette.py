"""Tests for command palette providers."""

from types import SimpleNamespace
from typing import cast

from textual.screen import Screen

from tina.gui.providers.command_palette import StatusPollProvider


class _FakeSelect:
    """Minimal select-like object for status-poll tests."""

    def __init__(self, value: int) -> None:
        self.value = value


class _FakeApp:
    """Minimal app stub for command-palette provider tests."""

    def __init__(self, *, connected: bool = False, value: int = 5) -> None:
        self.settings = SimpleNamespace(status_poll_interval=value)
        self.settings_manager = SimpleNamespace(save_calls=[])
        self.settings_manager.save = (
            lambda settings: self.settings_manager.save_calls.append(
                settings.status_poll_interval
            )
        )
        self.connected = connected
        self.last_measurement = None
        self._poll_restart_calls: list[int] = []
        self._select = _FakeSelect(value)

    def query_one(self, selector: str, _widget_type):
        """Return the fake poll-interval select widget."""
        assert selector == "#sb_poll_interval"
        return self._select

    def _start_status_polling(self, value: int) -> None:
        """Record status-poll restart requests."""
        self._poll_restart_calls.append(value)


class _FakeScreen:
    """Minimal screen-like object exposing the app reference Provider needs."""

    def __init__(self, app: _FakeApp) -> None:
        self.app = app
        self.focused = None


class TestStatusPollProvider:
    """Tests for status-poll command palette persistence."""

    def test_apply_persists_status_poll_interval(self) -> None:
        """Palette-driven status-poll changes should save through settings_manager."""
        app = _FakeApp(connected=False, value=5)
        provider = StatusPollProvider(cast(Screen[object], _FakeScreen(app)))

        provider._apply(10)

        assert app.settings.status_poll_interval == 10
        assert app.query_one("#sb_poll_interval", object).value == 10
        assert app.settings_manager.save_calls == [10]
        assert app._poll_restart_calls == []

    def test_apply_restarts_polling_when_connected(self) -> None:
        """Connected apps should persist and restart polling on palette changes."""
        app = _FakeApp(connected=True, value=5)
        provider = StatusPollProvider(cast(Screen[object], _FakeScreen(app)))

        provider._apply(2)

        assert app.settings.status_poll_interval == 2
        assert app.settings_manager.save_calls == [2]
        assert app._poll_restart_calls == [2]
