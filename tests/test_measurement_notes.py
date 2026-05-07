"""Tests for measurement notes state and markdown preview helpers."""

from __future__ import annotations

from typing import Any, cast

import pytest

from tina.main import VNAApp


class _FakeInputChangedEvent:
    """Minimal event object compatible with the implemented notes handler."""

    def __init__(self, value: str) -> None:
        self.value = value


class _FakeTextArea:
    """Minimal text-area-like object exposing a text attribute."""

    def __init__(self, text: str = "") -> None:
        self.text = text


class _FakeMarkdown:
    """Minimal markdown-like widget that records updated content."""

    def __init__(self) -> None:
        self.content = ""

    def update(self, content: str) -> None:
        """Store the latest rendered markdown content."""
        self.content = content


class _FakeApp:
    """Minimal app stub for exercising measurement-notes helpers."""

    def __init__(
        self,
        *,
        notes_text: str = "",
        last_measurement: dict[str, Any] | None = None,
    ) -> None:
        self.measurement_notes = notes_text
        self.last_measurement = last_measurement
        self._notes_editor = _FakeTextArea(notes_text)
        self._notes_preview = _FakeMarkdown()
        self._sync_measurement_notes_from_editor = lambda: None
        self._refresh_measurement_notes_preview = lambda: None

    def query_one(self, selector: str, _widget_type=None):
        """Return minimal widget stubs for selectors used by notes helpers."""
        if selector == "#measurement_notes_editor":
            return self._notes_editor
        if selector == "#measurement_notes_preview":
            return self._notes_preview
        raise AssertionError(f"Unexpected selector: {selector}")


@pytest.mark.unit
class TestMeasurementNotesState:
    """Tests for measurement-notes state synchronization."""

    def test_sync_measurement_notes_from_editor_updates_app_state_without_measurement(
        self,
    ) -> None:
        """Sync should copy editor text into app state without requiring measurement data."""
        app = _FakeApp(notes_text="")
        app._notes_editor.text = "# Notes\nInitial draft"

        VNAApp._sync_measurement_notes_from_editor(cast(Any, app))

        assert app.measurement_notes == "# Notes\nInitial draft"
        assert app.last_measurement is None

    def test_sync_measurement_notes_from_editor_updates_cached_measurement_notes(
        self,
    ) -> None:
        """Sync should mirror editor text into cached measurement notes when present."""
        app = _FakeApp(
            notes_text="old",
            last_measurement={
                "freqs": [],
                "sparams": {},
                "output_path": "measurement/example_run.s2p",
                "notes": "old",
            },
        )
        app._notes_editor.text = "updated **markdown**"

        VNAApp._sync_measurement_notes_from_editor(cast(Any, app))

        assert app.measurement_notes == "updated **markdown**"
        assert app.last_measurement is not None
        assert app.last_measurement["notes"] == "updated **markdown**"

    def test_handle_measurement_notes_change_uses_sync_and_preview_helpers(
        self,
    ) -> None:
        """Change handler should delegate to the sync and preview helpers in order."""
        app = _FakeApp(notes_text="")
        calls: list[str] = []
        app._sync_measurement_notes_from_editor = cast(
            Any, lambda: calls.append("sync")
        )
        app._refresh_measurement_notes_preview = cast(
            Any, lambda: calls.append("preview")
        )

        VNAApp.handle_measurement_notes_change(
            cast(Any, app), cast(Any, _FakeInputChangedEvent("ignored"))
        )

        assert calls == ["sync", "preview"]

    def test_load_measurement_notes_into_editor_prefers_cached_measurement_notes(
        self,
    ) -> None:
        """Loading should prefer cached measurement notes over stale app state."""
        app = _FakeApp(
            notes_text="stale app notes",
            last_measurement={
                "freqs": [],
                "sparams": {},
                "output_path": "measurement/example_run.s2p",
                "notes": "cached measurement notes",
            },
        )
        app._refresh_measurement_notes_preview = cast(
            Any, lambda: VNAApp._refresh_measurement_notes_preview(cast(Any, app))
        )

        VNAApp._load_measurement_notes_into_editor(cast(Any, app))

        assert app.measurement_notes == "cached measurement notes"
        assert app._notes_editor.text == "cached measurement notes"
        assert app._notes_preview.content == "cached measurement notes"

    def test_load_measurement_notes_into_editor_preserves_app_notes_when_missing(
        self,
    ) -> None:
        """Loading should keep current app notes when cached measurement notes are absent."""
        app = _FakeApp(
            notes_text="draft from app state",
            last_measurement={
                "freqs": [],
                "sparams": {},
                "output_path": "measurement/example_run.s2p",
            },
        )
        app._refresh_measurement_notes_preview = cast(
            Any, lambda: VNAApp._refresh_measurement_notes_preview(cast(Any, app))
        )

        VNAApp._load_measurement_notes_into_editor(cast(Any, app))

        assert app.measurement_notes == "draft from app state"
        assert app._notes_editor.text == "draft from app state"
        assert app._notes_preview.content == "draft from app state"


@pytest.mark.unit
class TestMeasurementNotesPreviewHelpers:
    """Tests for markdown preview behavior in the notes panel."""

    def test_refresh_notes_preview_shows_placeholder_for_empty_notes(self) -> None:
        """Empty notes should render the simplified placeholder preview."""
        app = _FakeApp(notes_text="")
        app._notes_editor.text = "   "

        VNAApp._refresh_measurement_notes_preview(cast(Any, app))

        assert app._notes_preview.content == "No notes yet"
        assert app.measurement_notes == "   "

    def test_refresh_notes_preview_renders_markdown_source(self) -> None:
        """Non-empty notes should be forwarded to the markdown preview widget."""
        app = _FakeApp(notes_text="# Heading\n- item one\n- item two")
        app._notes_editor.text = "# Heading\n- item one\n- item two"

        VNAApp._refresh_measurement_notes_preview(cast(Any, app))

        assert app._notes_preview.content == "# Heading\n- item one\n- item two"
        assert app.measurement_notes == "# Heading\n- item one\n- item two"

    def test_refresh_notes_preview_uses_editor_text_as_source_of_truth(self) -> None:
        """Preview refresh should read the current editor contents."""
        app = _FakeApp(notes_text="stale")
        app._notes_editor.text = "live editor text"
        app.measurement_notes = "stale"

        VNAApp._refresh_measurement_notes_preview(cast(Any, app))

        assert app.measurement_notes == "live editor text"
        assert app._notes_preview.content == "live editor text"

    def test_refresh_notes_preview_updates_cached_measurement_notes(self) -> None:
        """Preview refresh should keep cached measurement notes aligned with editor text."""
        app = _FakeApp(
            notes_text="old",
            last_measurement={
                "freqs": [],
                "sparams": {},
                "output_path": "measurement/example_run.s2p",
                "notes": "old",
            },
        )
        app._notes_editor.text = "latest note"

        VNAApp._refresh_measurement_notes_preview(cast(Any, app))

        assert app.last_measurement is not None
        assert app.last_measurement["notes"] == "latest note"
        assert app._notes_preview.content == "latest note"
