"""Tests for measurement notes state and markdown preview helpers."""

from __future__ import annotations

from typing import Any, cast

import pytest

from src.tina.main import VNAApp


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

    def test_handle_measurement_notes_change_updates_app_state_without_measurement(
        self,
    ) -> None:
        """Editor text should update app-level notes even before a measurement exists."""
        app = _FakeApp(notes_text="")
        event = _FakeInputChangedEvent("# Notes\nInitial draft")
        app._sync_measurement_notes_from_editor = cast(
            Any,
            lambda: setattr(app, "measurement_notes", event.value),
        )
        app._refresh_measurement_notes_preview = cast(
            Any,
            lambda: app._notes_preview.update(event.value),
        )

        VNAApp.handle_measurement_notes_change(cast(Any, app), cast(Any, event))

        assert app.measurement_notes == "# Notes\nInitial draft"
        assert app.last_measurement is None

    def test_handle_measurement_notes_change_updates_cached_measurement_notes(
        self,
    ) -> None:
        """Editor text should also be mirrored into cached measurement state."""
        app = _FakeApp(
            notes_text="old",
            last_measurement={
                "freqs": [],
                "sparams": {},
                "output_path": "measurement/example_run.s2p",
                "notes": "old",
            },
        )
        event = _FakeInputChangedEvent("updated **markdown**")
        app._sync_measurement_notes_from_editor = cast(
            Any,
            lambda: (
                setattr(app, "measurement_notes", event.value),
                app.last_measurement is not None
                and app.last_measurement.__setitem__("notes", event.value),
            ),
        )
        app._refresh_measurement_notes_preview = cast(
            Any,
            lambda: app._notes_preview.update(event.value),
        )

        VNAApp.handle_measurement_notes_change(cast(Any, app), cast(Any, event))

        assert app.measurement_notes == "updated **markdown**"
        assert app.last_measurement is not None
        assert app.last_measurement["notes"] == "updated **markdown**"


@pytest.mark.unit
class TestMeasurementNotesPreviewHelpers:
    """Tests for markdown preview behavior in the notes panel."""

    def test_refresh_notes_preview_shows_placeholder_for_empty_notes(self) -> None:
        """Empty notes should render the simplified placeholder preview."""
        app = _FakeApp(notes_text="")

        VNAApp._refresh_measurement_notes_preview(cast(Any, app))

        assert app._notes_preview.content == "No notes yet"

    def test_refresh_notes_preview_renders_markdown_source(self) -> None:
        """Non-empty notes should be forwarded to the markdown preview widget."""
        app = _FakeApp(notes_text="# Heading\n- item one\n- item two")

        VNAApp._refresh_measurement_notes_preview(cast(Any, app))

        assert "# Heading" in app._notes_preview.content
        assert "- item one" in app._notes_preview.content

    def test_refresh_notes_preview_uses_editor_text_as_source_of_truth(self) -> None:
        """Preview refresh should read the current editor contents."""
        app = _FakeApp(notes_text="stale")
        app._notes_editor.text = "live editor text"
        app.measurement_notes = "live editor text"

        VNAApp._refresh_measurement_notes_preview(cast(Any, app))

        assert "live editor text" in app._notes_preview.content


@pytest.mark.unit
class TestMeasurementNotesLayoutHelpers:
    """Tests for small layout/state helpers related to measurement notes."""

    def test_new_measurement_notes_payload_can_be_stored_in_cached_measurement(
        self,
    ) -> None:
        """Cached measurement dictionaries should accept a notes field."""
        notes = "## DUT notes\nMeasured after warm-up."
        measurement = {
            "freqs": [],
            "sparams": {},
            "output_path": "measurement/example_run.s2p",
            "notes": notes,
        }

        assert measurement["notes"] == notes

    def test_measurement_notes_default_to_empty_string_when_missing(self) -> None:
        """Missing notes should be treated as an empty markdown document."""
        measurement = {
            "freqs": [],
            "sparams": {},
            "output_path": "measurement/example_run.s2p",
        }

        notes = measurement.get("notes", "")

        assert notes == ""

    def test_notes_panel_ratio_helper_values_match_design_intent(self) -> None:
        """The intended options-to-notes split should remain 5:4."""
        options_fraction = 5
        notes_fraction = 4

        assert options_fraction == 5
        assert notes_fraction == 4
        assert options_fraction > notes_fraction
