"""Tests for command palette providers."""

from __future__ import annotations

from types import SimpleNamespace
from typing import cast

import pytest
from textual.screen import Screen

from tina.gui.providers.command_palette import (
    CursorMarkerProvider,
    PlotBackendProvider,
    RecentExportedProvider,
    RecentImportedProvider,
    SetupImportProvider,
    SetupRestoreHistoryProvider,
    StatusPollProvider,
)


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


# ---------------------------------------------------------------------------
# Shared stubs for new-provider tests
# ---------------------------------------------------------------------------


class _FakeAppFull:
    """App stub covering the full set of attributes needed by the new providers."""

    def __init__(self, *, last_measurement=None) -> None:
        self.settings = SimpleNamespace(
            plot_backend="image",
            cursor_marker_style="default",
            setup_restore_history=[],
            recent_exported_measurements=[],
            recent_imported_measurements=[],
        )
        self.settings_manager = SimpleNamespace(save_calls=[])
        self.settings_manager.save = lambda s: self.settings_manager.save_calls.append(
            s
        )
        self.last_measurement = last_measurement
        self.call_after_refresh_calls: list = []
        self._update_plot_type_calls = 0
        self._update_results_calls: list = []
        self._refresh_tools_plot_calls = 0
        self._import_setup_calls = 0
        self._restore_setup_calls: list[str] = []
        self._open_recent_calls: list[str] = []

    def call_after_refresh(self, callback) -> None:
        self.call_after_refresh_calls.append(callback)

    def _update_plot_type_options(self) -> None:
        self._update_plot_type_calls += 1

    def _update_results(self, freqs, sparams, output_path) -> None:
        self._update_results_calls.append(output_path)

    def _refresh_tools_plot(self) -> None:
        self._refresh_tools_plot_calls += 1

    def action_import_setup_from_measurement_output(self) -> None:
        self._import_setup_calls += 1

    def action_restore_setup_from_path(self, path: str) -> None:
        self._restore_setup_calls.append(path)

    def action_open_recent_measurement(self, path: str) -> None:
        self._open_recent_calls.append(path)


class _FakeScreenFull:
    def __init__(self, app: _FakeAppFull) -> None:
        self.app = app
        self.focused = None


# ---------------------------------------------------------------------------
# PlotBackendProvider
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestPlotBackendProvider:
    def test_apply_updates_setting_and_saves(self) -> None:
        """_apply must update plot_backend and persist via settings_manager."""
        app = _FakeAppFull()
        provider = PlotBackendProvider(cast(Screen[object], _FakeScreenFull(app)))

        provider._apply("terminal")

        assert app.settings.plot_backend == "terminal"
        assert app._update_plot_type_calls == 1
        assert len(app.settings_manager.save_calls) == 1
        assert app.settings_manager.save_calls[0].plot_backend == "terminal"

    def test_apply_schedules_refresh_when_measurement_loaded(self) -> None:
        """With a loaded measurement _apply should queue two call_after_refresh callbacks."""
        measurement = {"freqs": [], "sparams": {}, "output_path": "/tmp/x.s2p"}
        app = _FakeAppFull(last_measurement=measurement)
        provider = PlotBackendProvider(cast(Screen[object], _FakeScreenFull(app)))

        provider._apply("terminal")

        assert len(app.call_after_refresh_calls) == 2

    def test_apply_no_refresh_without_measurement(self) -> None:
        """Without a loaded measurement no call_after_refresh should be scheduled."""
        app = _FakeAppFull(last_measurement=None)
        provider = PlotBackendProvider(cast(Screen[object], _FakeScreenFull(app)))

        provider._apply("terminal")

        assert app.call_after_refresh_calls == []


# ---------------------------------------------------------------------------
# CursorMarkerProvider
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestCursorMarkerProvider:
    def test_apply_updates_setting_and_saves(self) -> None:
        """_apply must update cursor_marker_style and persist via settings_manager."""
        app = _FakeAppFull()
        provider = CursorMarkerProvider(cast(Screen[object], _FakeScreenFull(app)))

        provider._apply("circle")

        assert app.settings.cursor_marker_style == "circle"
        assert len(app.settings_manager.save_calls) == 1
        assert app.settings_manager.save_calls[0].cursor_marker_style == "circle"

    def test_apply_schedules_refresh_when_measurement_loaded(self) -> None:
        """With a loaded measurement _apply should queue call_after_refresh for the plot."""
        measurement = {"freqs": [], "sparams": {}, "output_path": "/tmp/x.s2p"}
        app = _FakeAppFull(last_measurement=measurement)
        provider = CursorMarkerProvider(cast(Screen[object], _FakeScreenFull(app)))

        provider._apply("circle")

        assert len(app.call_after_refresh_calls) == 1
        # Invoke the scheduled callback and verify it reaches _refresh_tools_plot.
        app.call_after_refresh_calls[0]()
        assert app._refresh_tools_plot_calls == 1

    def test_apply_no_refresh_without_measurement(self) -> None:
        """Without a loaded measurement no call_after_refresh should be scheduled."""
        app = _FakeAppFull(last_measurement=None)
        provider = CursorMarkerProvider(cast(Screen[object], _FakeScreenFull(app)))

        provider._apply("circle")

        assert app.call_after_refresh_calls == []


# ---------------------------------------------------------------------------
# SetupImportProvider
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestSetupImportProvider:
    def test_apply_invokes_import_action(self) -> None:
        """_apply must call action_import_setup_from_measurement_output on the app."""
        app = _FakeAppFull()
        provider = SetupImportProvider(cast(Screen[object], _FakeScreenFull(app)))

        provider._apply()

        assert app._import_setup_calls == 1


# ---------------------------------------------------------------------------
# Path-history providers
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestPathHistoryProviders:
    @pytest.mark.asyncio
    async def test_setup_restore_discover_yields_history_paths(self) -> None:
        """SetupRestoreHistoryProvider.discover should yield one hit per history entry."""
        app = _FakeAppFull()
        app.settings.setup_restore_history = ["/a/setup.json", "/b/setup.json"]
        provider = SetupRestoreHistoryProvider(
            cast(Screen[object], _FakeScreenFull(app))
        )

        hits = [hit async for hit in provider.discover()]

        assert len(hits) == 2
        labels = [h.text for h in hits]
        assert "/a/setup.json" in labels
        assert "/b/setup.json" in labels

    @pytest.mark.asyncio
    async def test_setup_restore_action_calls_restore(self) -> None:
        """The action yielded by SetupRestoreHistoryProvider must call action_restore_setup_from_path."""
        app = _FakeAppFull()
        app.settings.setup_restore_history = ["/a/setup.json"]
        provider = SetupRestoreHistoryProvider(
            cast(Screen[object], _FakeScreenFull(app))
        )

        hits = [hit async for hit in provider.discover()]
        hits[0].command()

        assert app._restore_setup_calls == ["/a/setup.json"]

    @pytest.mark.asyncio
    async def test_recent_exported_action_calls_open_recent(self) -> None:
        """The action yielded by RecentExportedProvider must call action_open_recent_measurement."""
        app = _FakeAppFull()
        app.settings.recent_exported_measurements = ["/exports/run1.s2p"]
        provider = RecentExportedProvider(cast(Screen[object], _FakeScreenFull(app)))

        hits = [hit async for hit in provider.discover()]
        hits[0].command()

        assert app._open_recent_calls == ["/exports/run1.s2p"]

    @pytest.mark.asyncio
    async def test_recent_imported_action_calls_open_recent(self) -> None:
        """The action yielded by RecentImportedProvider must call action_open_recent_measurement."""
        app = _FakeAppFull()
        app.settings.recent_imported_measurements = ["/imports/run2.s2p"]
        provider = RecentImportedProvider(cast(Screen[object], _FakeScreenFull(app)))

        hits = [hit async for hit in provider.discover()]
        hits[0].command()

        assert app._open_recent_calls == ["/imports/run2.s2p"]

    @pytest.mark.asyncio
    async def test_discover_yields_nothing_for_empty_history(self) -> None:
        """Providers with no history entries should yield no hits."""
        app = _FakeAppFull()
        provider = SetupRestoreHistoryProvider(
            cast(Screen[object], _FakeScreenFull(app))
        )

        hits = [hit async for hit in provider.discover()]

        assert hits == []
