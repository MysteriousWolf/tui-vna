"""Command palette providers for GUI settings shortcuts."""

from __future__ import annotations

from functools import partial

from textual.command import Hit, Hits, Provider
from textual.widgets import Select

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
        app = self.app
        app.settings.status_poll_interval = value
        app.query_one("#sb_poll_interval", Select).value = value
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
        app = self.app
        app.settings.plot_backend = value
        app._update_plot_type_options()
        app.settings_manager.save(app.settings)
        if app.last_measurement is not None:
            app.call_after_refresh(
                app._update_results,
                app.last_measurement["freqs"],
                app.last_measurement["sparams"],
                app.last_measurement["output_path"],
            )
            app.call_after_refresh(app._refresh_tools_plot)


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
        app = self.app
        app.settings.cursor_marker_style = value
        app.settings_manager.save(app.settings)
        if app.last_measurement is not None:
            app.call_after_refresh(app._refresh_tools_plot)
