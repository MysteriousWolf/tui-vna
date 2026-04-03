"""Status footer component for the TINA GUI."""

from typing import TYPE_CHECKING

from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.widgets import Footer, Static

if TYPE_CHECKING:
    from ...worker import StatusResult

# Short human-readable names for common SCPI error codes (IEEE 488.2 / SCPI 1999).
_SCPI_ERROR_NAMES: dict[str, str] = {
    "+0": "OK",
    "0": "OK",
    "-100": "CMD",
    "-113": "UNDEF",
    "-222": "RANGE",
    "-224": "ILLEGAL",
    "-310": "SYS",
    "-350": "QUEUE",
    "-400": "QUERY",
    "-420": "UNTMN",
    "-430": "DEADLK",
}


def _scpi_mnemonic(cmd: str) -> str:
    """Return a compact display mnemonic for a SCPI command.

    Strips parameter values (text after a space), trailing ``?``, and any
    channel-number suffix on the first node (e.g. ``SENS1`` → removed so
    ``SENS1:CORR:STAT?`` becomes ``CORR:STAT``).
    """
    base = cmd.split(" ")[0].rstrip("?")
    parts = base.split(":")
    if parts and parts[0] and parts[0][-1].isdigit():
        parts = parts[1:]
    return ":".join(parts) or base


_ALL_SB_STATE_CLASSES = (
    "--stale",
    "--state-ok",
    "--state-off",
    "--smo-on",
    "--trig-INT",
    "--trig-MAN",
    "--trig-EXT",
    "--trig-BUS",
)

_SB_ITEMS = ("sb_cal", "sb_smooth", "sb_ifbw", "sb_power", "sb_trigger")


class StatusFooter(Footer):
    """Textual Footer with VNA status items appended after the key bindings."""

    DEFAULT_CSS = Footer.DEFAULT_CSS + """
    StatusFooter #sb_spacer {
        width: 1fr;
        height: 1;
    }
    StatusFooter #sb_status_container {
        width: auto;
        height: 1;
        padding: 0 1 0 0;
    }
    StatusFooter .sb-item {
        width: auto;
        height: 1;
        padding: 0 1;
        content-align: left middle;
        background: $panel-lighten-1;
    }
    StatusFooter .sb-sep {
        width: 1;
        height: 1;
    }
    StatusFooter .sb-item.--stale {
        background: $panel-lighten-1;
        color: $text-muted;
        text-style: dim;
    }
    StatusFooter .sb-item.--state-ok  { background: $success;   color: $background; }
    StatusFooter .sb-item.--state-off { background: $error;     color: $background; }
    StatusFooter .sb-item.--smo-on    { background: $accent;    color: $background; }
    StatusFooter .sb-item.--trig-INT  { background: $primary;   color: $background; }
    StatusFooter .sb-item.--trig-MAN  { background: $warning;   color: $background; }
    StatusFooter .sb-item.--trig-EXT  { background: $secondary; color: $background; }
    StatusFooter .sb-item.--trig-BUS  { background: $success;   color: $background; }
    StatusFooter #sb_debug_group {
        display: none;
        width: auto;
        height: 1;
    }
    StatusFooter #sb_debug_group.--visible {
        display: block;
    }
    """

    # Initial placeholder text shown before first poll
    _PLACEHOLDERS: dict[str, str] = {
        "sb_cal": "CAL",
        "sb_smooth": "SMTH",
        "sb_ifbw": "IFBW",
        "sb_power": "PWR",
        "sb_trigger": "TRIG",
    }

    def __init__(self, **kwargs):
        """Initialise state stores for chip text/class and debug chip visibility."""
        super().__init__(**kwargs)
        # (text, css_class) — class "" means no coloured background
        self._sb_state: dict[str, tuple[str, str]] = {
            k: (self._PLACEHOLDERS[k], "--stale") for k in _SB_ITEMS
        }
        # Debug chip state — persists across Footer recomposes
        self._debug_visible: bool = False
        self._debug_chip_state: tuple[str, str] = ("ERR OK", "--state-ok")

    def compose(self) -> ComposeResult:
        """Build footer: key bindings (left), debug chip, spacer, status chips (right)."""
        yield from super().compose()  # q Quit leftmost; ^p palette docked right
        # Debug error chip — left-aligned next to q Quit, hidden until debug active.
        # Classes are set from stored state so recomposes (triggered by Footer
        # internals on focus changes) preserve visibility and chip content.
        debug_text, debug_css = self._debug_chip_state
        grp_classes = "--visible" if self._debug_visible else ""
        with Horizontal(id="sb_debug_group", classes=grp_classes):
            yield Static(" ", classes="sb-sep")
            yield Static(
                debug_text,
                id="sb_lasterr",
                classes=f"sb-item {debug_css}".strip(),
            )
        yield Static("", id="sb_spacer")  # pushes status items to the right
        with Horizontal(id="sb_status_container"):
            for i, item_id in enumerate(_SB_ITEMS):
                if i > 0:
                    yield Static(" ", classes="sb-sep")
                text, css_class = self._sb_state[item_id]
                yield Static(text, id=item_id, classes=f"sb-item {css_class}".strip())

    def _set_item(self, item_id: str, text: str, css_class: str = "") -> None:
        """Update a single status chip's text and CSS class in state and in the DOM."""
        self._sb_state[item_id] = (text, css_class)
        try:
            w = self.query_one(f"#{item_id}", Static)
            w.update(text)
            w.remove_class(*_ALL_SB_STATE_CLASSES)
            if css_class:
                w.add_class(css_class)
        except Exception:
            pass

    def _apply_debug_chip(self) -> None:
        """Push stored debug chip state to the live widgets."""
        try:
            self.query_one("#sb_debug_group").set_class(
                self._debug_visible, "--visible"
            )
            # Only update chip content when visible — avoids a colour flash
            # when the group is being hidden (class change rendered before hide).
            if not self._debug_visible:
                return
            text, css_class = self._debug_chip_state
            chip = self.query_one("#sb_lasterr", Static)
            chip.update(text)
            chip.remove_class(*_ALL_SB_STATE_CLASSES)
            if css_class:
                chip.add_class(css_class)
        except Exception:
            pass

    def set_disconnected(self) -> None:
        """Mark all items as stale; preserve last-known text."""
        for item_id in _SB_ITEMS:
            text, _ = self._sb_state[item_id]
            self._sb_state[item_id] = (text, "--stale")
            try:
                w = self.query_one(f"#{item_id}", Static)
                w.remove_class(*_ALL_SB_STATE_CLASSES)
                w.add_class("--stale")
            except Exception:
                pass
        # Gray out debug chip while disconnected
        prev_text, _ = self._debug_chip_state
        self._debug_chip_state = (prev_text, "--stale")
        self._apply_debug_chip()

    def set_debug_mode(self, enabled: bool, connected: bool = True) -> None:
        """Show or hide the last-error debug chip."""
        self._debug_visible = enabled
        if not enabled:
            self._debug_chip_state = ("ERR OK", "--state-ok")
        elif not connected:
            self._debug_chip_state = ("ERR OK", "--stale")
        self._apply_debug_chip()

    def update_last_error(self, command: str, raw_error: str) -> None:
        """Update the debug error chip from a SYST:ERR? response.

        Args:
            command:   The SCPI command that preceded the SYST:ERR? check.
            raw_error: Stripped SYST:ERR? response, e.g. ``+0,"No error"``
                       or ``-113,"Undefined header"``.
        """
        if raw_error.startswith("+0") or raw_error.startswith("0,"):
            self._debug_chip_state = ("ERR OK", "--state-ok")
        else:
            code = raw_error.split(",")[0].strip()
            name = _SCPI_ERROR_NAMES.get(code, code)
            mnem = _scpi_mnemonic(command)
            self._debug_chip_state = (f"{mnem} {name}", "--state-off")
        self._apply_debug_chip()

    def update_status(self, result: "StatusResult") -> None:
        """Refresh all status chips from a fresh StatusResult."""
        # Calibration
        if result.cal_enabled is None:
            self._set_item("sb_cal", self._sb_state["sb_cal"][0], "--stale")
        elif result.cal_enabled:
            self._set_item("sb_cal", (result.cal_type or "CAL").strip(), "--state-ok")
        else:
            self._set_item("sb_cal", "CAL", "--state-off")

        # Smoothing
        if result.smoothing_enabled is None:
            self._set_item("sb_smooth", self._sb_state["sb_smooth"][0], "--stale")
        elif result.smoothing_enabled and result.smoothing_aperture is not None:
            self._set_item(
                "sb_smooth", f"SMTH {result.smoothing_aperture:.1f}%", "--smo-on"
            )
        else:
            self._set_item("sb_smooth", "SMTH", "--state-off")

        # IF bandwidth
        hz = result.if_bandwidth_hz
        if hz is None:
            self._set_item("sb_ifbw", self._sb_state["sb_ifbw"][0], "--stale")
        elif hz >= 1e6:
            self._set_item("sb_ifbw", f"{hz / 1e6:.3g} MHz")
        elif hz >= 1e3:
            self._set_item("sb_ifbw", f"{hz / 1e3:.3g} kHz")
        else:
            self._set_item("sb_ifbw", f"{hz:.3g} Hz")

        # Port power
        if result.port_power_dbm is None:
            self._set_item("sb_power", self._sb_state["sb_power"][0], "--stale")
        else:
            self._set_item("sb_power", f"{result.port_power_dbm:+.1f} dBm")

        # Trigger source
        if result.trigger_source is None:
            self._set_item("sb_trigger", self._sb_state["sb_trigger"][0], "--stale")
        else:
            src = result.trigger_source.strip().upper()
            css = f"--trig-{src}" if f"--trig-{src}" in _ALL_SB_STATE_CLASSES else ""
            self._set_item("sb_trigger", src, css)
