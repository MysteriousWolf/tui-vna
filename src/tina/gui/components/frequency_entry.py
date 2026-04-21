"""
Reusable FrequencyEntry component for TINA tools.

This component encapsulates:
- a frequency `Input` (with configurable unit)
- previous / next extrema navigation buttons
- toggles for "minima mode" and "smoothing mode" (modifiers fallback)

Note: this widget does not emit custom Textual Message subclasses. The
application should listen for `Input.Changed` on the inner input ID and
`Button.Pressed` on the stable button IDs to react to user actions.

IDs and CSS classes are deliberately configurable via constructor to allow
smooth migration into existing UI (for example the old `#input_tools_cursor1`
widget can be replaced by a FrequencyEntry instance with `input_id="input_tools_cursor1"`).

Notes:
- Alt/Ctrl modifier handling was found unreliable across environments. Instead
  explicit toggle buttons are provided for minima/smoothing modes.
- The component does not itself access measurement data or perform extrema
  detection. It only provides the UI; the app (or a containing controller)
  should perform search and call `set_frequency_hz()` to update the input after snapping.
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.widgets import Button, Input, Label, Static

# Unit multipliers for converting displayed unit -> Hz
_UNIT_MULTIPLIERS = {"Hz": 1.0, "kHz": 1e3, "MHz": 1e6, "GHz": 1e9}


class FrequencyEntry(Static):
    """
    FrequencyEntry widget composed of:
      [Label] [Input] [Prev Button] [Next Button] [Minima Toggle] [Smooth Toggle]

    Constructor kwargs:
      input_id: id for the Input widget (default "input_frequency")
      prev_id: id for prev-extrema button
      next_id: id for next-extrema button
      minima_toggle_id: id for minima-mode toggle button
      smooth_toggle_id: id for smoothing-mode toggle button
      label: optional label text displayed to the left of the input
      freq_unit: visible/default unit for the input ("MHz" by default)

    Events:
      FrequencyEntry.FrequencyChanged(self, hz: Optional[float])
      FrequencyEntry.ExtremaNavigate(self, direction: int, minima: bool, smoothing: bool)
      FrequencyEntry.ModeChanged(self, minima: bool, smoothing: bool)
    """

    # FrequencyChanged message class removed — FrequencyEntry no longer emits
    # custom textual Message subclasses. Consumers should listen to the stable
    # Input/Button widget IDs instead.

    # ExtremaNavigate message class removed — navigation requests are signalled
    # via Button.Pressed events on the prev/next buttons (stable IDs).

    # ModeChanged message class removed — mode changes are reflected on the
    # toggle buttons themselves and are intended to be handled by Button.Pressed
    # handlers in the application.

    def __init__(
        self,
        *,
        input_id: str = "input_frequency",
        prev_id: str = "btn_freq_prev",
        next_id: str = "btn_freq_next",
        minima_toggle_id: str = "btn_freq_minima",
        smooth_toggle_id: str = "btn_freq_smooth",
        label: str = "",
        freq_unit: str = "MHz",
        classes: str | None = None,
        **kwargs,
    ) -> None:
        # Forward the provided `classes` value to the Static superclass so that
        # instances of FrequencyEntry receive the intended CSS classes (for
        # example 'plot-controls' when mounted in the Tools panel).
        super().__init__(classes=classes, **kwargs)
        self.input_id = input_id
        self.prev_id = prev_id
        self.next_id = next_id
        self.minima_toggle_id = minima_toggle_id
        self.smooth_toggle_id = smooth_toggle_id
        self.label_text = label
        self.freq_unit = freq_unit if freq_unit in _UNIT_MULTIPLIERS else "MHz"

        # Mode state
        self._minima_mode: bool = False
        self._smoothing_mode: bool = False

        # Last parsed Hz (None if invalid or blank)
        self._last_hz: float | None = None

    def compose(self) -> ComposeResult:
        """Build the child widgets."""
        # The inner row owns alignment and sizing. Do NOT add the global
        # 'plot-controls' class here because that class has broad selectors
        # (e.g. `.plot-controls > Button`) which can inadvertently target the
        # component's internal Buttons. Keep the row-scoped class so component
        # tcss can authoritatively control the footprint.
        with Horizontal(classes="freq-entry-row"):
            if self.label_text:
                yield Label(self.label_text, classes="freq-label")
            yield Input(
                id=self.input_id,
                placeholder=f"Frequency ({self.freq_unit})",
                classes="freq-input",
            )
            btn_prev = Button(
                "◀",
                id=self.prev_id,
                # Keep classes minimal: plot-control-button, semantic id, and variant
                classes="plot-control-button narrow prev-button variant-primary",
                variant="primary",
                flat=True,
            )
            yield btn_prev
            btn_next = Button(
                "▶",
                id=self.next_id,
                classes="plot-control-button narrow next-button variant-primary",
                variant="primary",
                flat=True,
            )
            yield btn_next
            # initialize visual state from local mode flags so sandbox shows correct mode
            minima_label = "▼" if self._minima_mode else "▲"
            # Use a static 'warning' variant for minima toggle (visual identity),
            # but do not change variant on toggle events — icon shows state.
            btn_minima = Button(
                minima_label,
                id=self.minima_toggle_id,
                # Variant class should match the Button.variant value
                classes="plot-control-button narrow minima-toggle variant-warning",
                variant="warning",
                flat=True,
            )
            yield btn_minima
            smooth_label = "∿" if self._smoothing_mode else "⎍"
            # Use a static 'success' variant for smoothing toggle (visual identity).
            btn_smooth = Button(
                smooth_label,
                id=self.smooth_toggle_id,
                classes="plot-control-button narrow smooth-toggle variant-success",
                variant="success",
                flat=True,
            )
            yield btn_smooth

    def on_mount(self) -> None:
        """Debugging aid: log classes of this component and its buttons on mount.

        This helps confirm that the tools-compact class and the tools-frequency-button
        classes are present when the component is mounted inside the app (so
        component-scoped tcss rules can apply). Remove when debugging is complete.
        """
        # Debug logging removed - left intentionally in earlier iterations to
        # verify runtime class forwarding. Keeping the hook here but no-op to
        # avoid noisy logs in normal runs.
        return

    # Public API ------------------------------------------------------------

    def set_freq_unit(self, unit: str) -> None:
        """Set visible unit for parsing/placeholder. Unit must be one of Hz/kHz/MHz/GHz."""
        if unit in _UNIT_MULTIPLIERS:
            self.freq_unit = unit
            try:
                inp = self.query_one(f"#{self.input_id}", Input)
                inp.placeholder = f"Frequency ({self.freq_unit})"
            except Exception:
                pass

    def set_frequency_hz(self, hz: float | None) -> None:
        """Update the input display from a frequency in Hz. Pass None to clear."""
        try:
            inp = self.query_one(f"#{self.input_id}", Input)
        except Exception:
            return
        if hz is None:
            inp.value = ""
            self._last_hz = None
        else:
            mult = _UNIT_MULTIPLIERS.get(self.freq_unit, 1e6)
            # Show value using a reasonable number of decimals
            display_val = f"{hz / mult:.6f}".rstrip("0").rstrip(".")
            inp.value = display_val
            self._last_hz = hz

    def get_frequency_hz(self) -> float | None:
        """Return the last parsed Hz value or None."""
        return self._last_hz

    def set_minima_mode(self, enabled: bool) -> None:
        """Set minima mode toggle state."""
        self._minima_mode = bool(enabled)
        self._update_toggle_visual(self.minima_toggle_id, self._minima_mode)
        # Mode change is local to this widget; the application should observe
        # the toggle button presses (Button.Pressed on toggle IDs) instead.

    def set_smoothing_mode(self, enabled: bool) -> None:
        """Set smoothing mode toggle state."""
        self._smoothing_mode = bool(enabled)
        self._update_toggle_visual(self.smooth_toggle_id, self._smoothing_mode)
        # Mode change is local to this widget; the application should observe
        # the toggle button presses instead of custom messages.

    # Internal helpers -----------------------------------------------------

    def _parse_input_value_to_hz(self, raw: str) -> float | None:
        """Parse the input string into Hz, honoring current unit. Returns None on invalid/blank."""
        try:
            s = raw.strip()
            if not s:
                return None
            mult = _UNIT_MULTIPLIERS.get(self.freq_unit, 1e6)
            return float(s) * mult
        except Exception:
            return None

    def _update_toggle_visual(self, btn_id: str, active: bool) -> None:
        """Update toggle labels only — do not change button variants or add active classes.

        We use the button icon (triangle / sine / no-sine) to indicate the logical
        state; visual color identity is provided by the static button variant set
        at compose time (and by app-level theming). Avoid changing variant or
        classes here so toggling does not alter color/size unexpectedly.
        """
        try:
            btn = self.query_one(f"#{btn_id}", Button)
            # Update label for known toggles and reflect active state with a
            # semantic class so CSS selectors matching .--active can apply.
            # We intentionally do not change the Button.variant here.
            if btn_id == self.minima_toggle_id:
                btn.label = "▼" if active else "▲"
                btn.set_class("--active", bool(active))
            elif btn_id == self.smooth_toggle_id:
                btn.label = "∿" if active else "⎍"
                btn.set_class("--active", bool(active))
        except Exception:
            pass

    # Event handlers -------------------------------------------------------

    def on_input_changed(self, event: Input.Changed) -> None:
        """Handle input changes and forward parsed Hz to the app when appropriate.

        This widget keeps an internal `_last_hz` parsed value as before, but when
        the input uses the legacy IDs used by the tools panel (for example
        `input_tools_cursor1` / `input_tools_cursor2`) we forward the parsed Hz to
        the application state (`app._tools_cursor{n}_hz`) and schedule the same
        debounced refresh that the rest of the tools UI uses.
        """
        # Only handle changes for our input
        if event.input.id != self.input_id:
            return
        hz = self._parse_input_value_to_hz(event.value or "")
        self._last_hz = hz

        # Forward to application-level cursor state when this FrequencyEntry is
        # acting as a tools cursor input (legacy IDs like input_tools_cursor1/2).
        try:
            app = getattr(self, "app", None)
            if app is not None and self.input_id in (
                "input_tools_cursor1",
                "input_tools_cursor2",
            ):
                # Determine cursor index (1 or 2) from the id suffix
                cursor_index = 1 if self.input_id.endswith("1") else 2
                try:
                    setattr(app, f"_tools_cursor{cursor_index}_hz", hz)
                except Exception:
                    # Best-effort: ignore if app state can't be set
                    pass

                # Debounced refresh: mirror the same behavior used elsewhere in tools logic
                try:
                    # Stop an existing timer if present
                    if getattr(app, "_tools_input_timer", None) is not None:
                        try:
                            app._tools_input_timer.stop()
                        except Exception:
                            pass
                    # Schedule the delayed refresh used by the tools tab
                    app._tools_input_timer = app.set_timer(
                        0.2, app._delayed_tools_refresh
                    )
                except Exception:
                    # If the app doesn't expose the expected timer API, ignore silently
                    pass
        except Exception:
            # Defensive: do not let widget-level forwarding raise to the caller
            pass

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle navigation and toggle button presses."""
        btn = event.button
        btn_id = btn.id

        if btn_id == self.prev_id:
            # Request previous extrema
            # Prev pressed — application should handle Button.Pressed on the
            # prev button ID and perform extrema navigation.
            return

        if btn_id == self.next_id:
            # Request next extrema
            # Next pressed — application should handle Button.Pressed on the
            # next button ID and perform extrema navigation.
            return

        if btn_id == self.minima_toggle_id:
            # Toggle minima mode
            self._minima_mode = not self._minima_mode
            self._update_toggle_visual(self.minima_toggle_id, self._minima_mode)
            # Toggle handled locally; application observes the Button.Pressed event
            return

        if btn_id == self.smooth_toggle_id:
            # Toggle smoothing mode
            self._smoothing_mode = not self._smoothing_mode
            self._update_toggle_visual(self.smooth_toggle_id, self._smoothing_mode)
            # Toggle handled locally; application observes the Button.Pressed event
            return

    # Convenience: allow keyboard Enter to emit FrequencyChanged as final commit
    def key_enter(
        self,
    ) -> None:  # textual will call this if key binding is present in parent
        """Treat Enter as a final commit of the input value.

        Parse the current inner Input value into Hz, update the widget's
        internal `_last_hz`, and forward the value to the application state in
        the same way `on_input_changed` does (so pressing Enter behaves like
        editing the legacy tools inputs).
        """
        try:
            inp = self.query_one(f"#{self.input_id}", Input)
        except Exception:
            return
        hz = self._parse_input_value_to_hz(inp.value or "")
        self._last_hz = hz

        # Forward the committed value to the application if this is a legacy tools input
        try:
            app = getattr(self, "app", None)
            if app is not None and self.input_id in (
                "input_tools_cursor1",
                "input_tools_cursor2",
            ):
                cursor_index = 1 if self.input_id.endswith("1") else 2
                try:
                    setattr(app, f"_tools_cursor{cursor_index}_hz", hz)
                except Exception:
                    pass
                try:
                    if getattr(app, "_tools_input_timer", None) is not None:
                        try:
                            app._tools_input_timer.stop()
                        except Exception:
                            pass
                    app._tools_input_timer = app.set_timer(
                        0.2, app._delayed_tools_refresh
                    )
                except Exception:
                    pass
        except Exception:
            pass
        # Emit nothing else — Input.Changed on the inner Input is the supported hook.
