#!/usr/bin/env python3
"""Minimal harness to visually inspect FrequencyEntry alignment.

This script mounts a tiny Textual app that composes a Measurement-style
plot-controls row and two side-by-side FrequencyEntry instances so the
developer can run it locally and inspect the temporary debug CSS classes.

This is intentionally minimal and not part of the test suite.
"""

from textual.app import App, ComposeResult
from textual.containers import Horizontal
from textual.widgets import Static

from tina.gui.components.frequency_entry import FrequencyEntry


class DebugAlignmentApp(App):
    CSS_PATHS = [
        "src/tina/gui/styles/frequency_entry.tcss",
    ]

    def compose(self) -> ComposeResult:
        # Top row: mimic measurement plot-controls with a couple of buttons
        with Horizontal(classes="plot-controls"):
            yield Static("Plot Controls:")
            yield Static(classes="spacer")
            yield Static("↻ Reset", classes="panel-button dbg-btn")
            yield Static("✓ Apply", classes="panel-button dbg-btn")

        # Two FrequencyEntry instances side-by-side for comparison
        with Horizontal():
            yield FrequencyEntry(
                input_id="dbg_input_1",
                label="C1",
                classes="plot-controls",
            )
            yield FrequencyEntry(
                input_id="dbg_input_2",
                label="C2",
                classes="plot-controls",
            )


if __name__ == "__main__":
    DebugAlignmentApp().run()
