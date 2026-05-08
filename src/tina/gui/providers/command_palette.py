"""Command palette providers for GUI settings shortcuts."""

from __future__ import annotations

from functools import partial
from typing import TYPE_CHECKING, Protocol, cast

from textual.command import Hit, Hits, Provider
from textual.widgets import Select

if TYPE_CHECKING:
    from tina.config.settings import AppSettings, SettingsManager


class _VNAAppProtocol(Protocol):
    """Protocol describing the VNA app attributes used by command providers."""

    settings: AppSettings
    settings_manager: SettingsManager
    connected: bool
    last_measurement: dict | None

    def _start_status_polling(self, value: int) -> None:
        """Restart status polling with the given interval."""

    def _update_plot_type_options(self) -> None:
        """Refresh plot type options after backend changes."""

    def _update_results(self, freqs, sparams, output_path):
        """Refresh the measurement results view."""

    def _refresh_tools_plot(self) -> None:
        """Refresh the tools plot."""

    def action_import_setup_from_measurement_output(self) -> None:
        """Import only setup state from a measurement output."""

    def action_restore_setup_from_path(self, path: str) -> None:
        """Restore setup state from a specific file path."""

    def action_open_recent_measurement(self, path: str) -> None:
        """Open a recent measurement from a specific file path."""


_POLL_OPTIONS = [
    ("Status poll: Off", 0),
    ("Status poll: 1 second", 1),
    ("Status poll: 2 seconds", 2),
    ("Status poll: 5 seconds", 5),
    ("Status poll: 10 seconds", 10),
    ("Status poll: 30 seconds", 30),
]

_BACKEND_OPTIONS = [
    ("Plot backend: Terminal", "terminal"),
    ("Plot backend: Image", "image"),
]

_CURSOR_MARKER_OPTIONS = [
    ("Cursor marker: ▼ (arrow down)", "▼"),
    ("Cursor marker: ✕ (cross)", "✕"),
    ("Cursor marker: ○ (circle)", "○"),
]

_SETUP_IMPORT_COMMAND = "Import setup from measurement output"


class StatusPollProvider(Provider):
    """Command palette provider for changing the status bar poll interval."""

    async def discover(self) -> Hits:
        """Yield all available poll-interval options unconditionally."""
        for label, value in _POLL_OPTIONS:
            yield Hit(
                1.0,
                label,
                partial(self._apply, value),
                help="Set status bar refresh interval",
            )

    async def search(self, query: str) -> Hits:
        """Yield poll-interval options whose labels match *query*."""
        matcher = self.matcher(query)
        for label, value in _POLL_OPTIONS:
            score = matcher.match(label)
            if score > 0:
                yield Hit(score, matcher.highlight(label), partial(self._apply, value))

    def _apply(self, value: int) -> None:
        """
        Set the application's status poll interval and restart polling if connected.

        Parameters:
            value: Poll interval in seconds.
        """
        app = cast(_VNAAppProtocol, self.app)
        app.settings.status_poll_interval = value
        self.app.query_one("#sb_poll_interval", Select).value = value
        app.settings_manager.save(app.settings)
        if app.connected:
            app._start_status_polling(value)


class PlotBackendProvider(Provider):
    """Command palette provider for switching the global plot backend."""

    async def discover(self) -> Hits:
        """Yield all backend options unconditionally."""
        for label, value in _BACKEND_OPTIONS:
            yield Hit(
                1.0,
                label,
                partial(self._apply, value),
                help="Set plot rendering backend",
            )

    async def search(self, query: str) -> Hits:
        """
        Yield backend options whose labels match the provided query.

        Parameters:
            query: Substring or pattern to match against backend option labels.
        """
        matcher = self.matcher(query)
        for label, value in _BACKEND_OPTIONS:
            score = matcher.match(label)
            if score > 0:
                yield Hit(score, matcher.highlight(label), partial(self._apply, value))

    def _apply(self, value: str) -> None:
        """
        Set the application's global plot backend and refresh plot-related UI.

        Parameters:
            value: Plot backend identifier, e.g. "terminal" or "image".
        """
        app = cast(_VNAAppProtocol, self.app)
        app.settings.plot_backend = value
        app._update_plot_type_options()
        app.settings_manager.save(app.settings)
        if app.last_measurement is not None:
            self.app.call_after_refresh(
                app._update_results,
                app.last_measurement["freqs"],
                app.last_measurement["sparams"],
                app.last_measurement["output_path"],
            )
            self.app.call_after_refresh(app._refresh_tools_plot)


class CursorMarkerProvider(Provider):
    """Command palette provider for selecting the cursor marker symbol."""

    async def discover(self) -> Hits:
        """
        Provide command-palette hits for each available cursor marker option.

        Each yielded hit, when applied, sets the cursor marker style used in the
        Tools tab.
        """
        for label, value in _CURSOR_MARKER_OPTIONS:
            yield Hit(
                1.0,
                label,
                partial(self._apply, value),
                help="Set cursor marker style for Tools tab",
            )

    async def search(self, query: str) -> Hits:
        """
        Yield cursor marker options whose labels match the given query.

        Parameters:
            query: Search query used to score and highlight option labels.
        """
        matcher = self.matcher(query)
        for label, value in _CURSOR_MARKER_OPTIONS:
            score = matcher.match(label)
            if score > 0:
                yield Hit(score, matcher.highlight(label), partial(self._apply, value))

    def _apply(self, value: str) -> None:
        """
        Apply the selected cursor marker style to the application settings.

        Parameters:
            value: Cursor marker symbol to apply.
        """
        app = cast(_VNAAppProtocol, self.app)
        app.settings.cursor_marker_style = value
        app.settings_manager.save(app.settings)
        if app.last_measurement is not None:
            self.app.call_after_refresh(app._refresh_tools_plot)


class SetupImportProvider(Provider):
    """Command palette provider for setup-only restoration from measurement outputs."""

    async def discover(self) -> Hits:
        """Yield the setup-only import command unconditionally."""
        yield Hit(
            1.0,
            _SETUP_IMPORT_COMMAND,
            self._apply,
            help="Restore only the Setup tab from an exported measurement file",
        )

    async def search(self, query: str) -> Hits:
        """Yield the setup-only import command when it matches *query*."""
        matcher = self.matcher(query)
        score = matcher.match(_SETUP_IMPORT_COMMAND)
        if score > 0:
            yield Hit(
                score,
                matcher.highlight(_SETUP_IMPORT_COMMAND),
                self._apply,
                help="Restore only the Setup tab from an exported measurement file",
            )

    def _apply(self) -> None:
        """Trigger setup-only import from a measurement output file."""
        app = cast(_VNAAppProtocol, self.app)
        app.action_import_setup_from_measurement_output()


class _PathHistoryProvider(Provider):
    """Base provider for MRU path-history command sources."""

    SETTING_NAME: str = ""

    def _get_action(self, _app: _VNAAppProtocol, _path: str):
        """Return the action callable for a given path hit.

        Subclasses must override this to return a callable that will be invoked
        when the user selects the hit in the command palette.
        """
        raise NotImplementedError

    async def discover(self) -> Hits:
        """Yield one hit per path in the configured settings list."""
        app = cast(_VNAAppProtocol, self.app)
        for path in getattr(app.settings, self.SETTING_NAME, []) or []:
            yield Hit(1.0, path, self._get_action(app, path))

    async def search(self, query: str) -> Hits:
        """Yield paths matching *query* from the configured settings list."""
        matcher = self.matcher(query)
        app = cast(_VNAAppProtocol, self.app)
        for path in getattr(app.settings, self.SETTING_NAME, []) or []:
            score = matcher.match(path)
            if score > 0:
                yield Hit(score, matcher.highlight(path), self._get_action(app, path))


class SetupRestoreHistoryProvider(_PathHistoryProvider):
    """Provide MRU entries for restoring setups from previous imports."""

    SETTING_NAME = "setup_restore_history"

    def _get_action(self, app: _VNAAppProtocol, path: str):
        """Return an action that restores a saved setup from the given path."""
        return partial(app.action_restore_setup_from_path, path)


class RecentExportedProvider(_PathHistoryProvider):
    """Provide MRU entries for recently exported measurements."""

    SETTING_NAME = "recent_exported_measurements"

    def _get_action(self, app: _VNAAppProtocol, path: str):
        """Return an action that opens a recently exported measurement from the given path."""
        return partial(app.action_open_recent_measurement, path)


class RecentImportedProvider(_PathHistoryProvider):
    """Provide MRU entries for recently imported measurements."""

    SETTING_NAME = "recent_imported_measurements"

    def _get_action(self, app: _VNAAppProtocol, path: str):
        """Return an action that opens a recently imported measurement from the given path."""
        return partial(app.action_open_recent_measurement, path)
