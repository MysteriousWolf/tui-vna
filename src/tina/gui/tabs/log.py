"""Log tab composition helpers for the TINA GUI."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Container, Horizontal
from textual.widgets import Checkbox, RichLog, Static


def compose_log_tab() -> ComposeResult:
    """Compose the Log tab UI.

    Yields a filter panel followed by the main log display.

    Key widget IDs:
    - ``#check_log_tx``, ``#check_log_rx``, ``#check_log_info``,
      ``#check_log_progress``, ``#check_log_success``, ``#check_log_error`` –
      primary filter checkboxes (``Checkbox``); toggling any triggers log re-filter.
    - ``#check_log_debug``, ``#check_log_poll`` – secondary filter checkboxes.
    - ``#log_content`` – the ``RichLog`` widget that holds rendered log lines;
      callers write to it via ``log_logic`` helpers and read from it when copying.
    """
    with Container(classes="panel") as panel:
        panel.border_title = "Filter"
        with Horizontal(classes="filter-row"):
            yield Checkbox("↑ TX", id="check_log_tx", value=True)
            yield Checkbox("↓ RX", id="check_log_rx", value=True)
            yield Checkbox("i Info", id="check_log_info", value=True)
            yield Checkbox("⋯ Busy", id="check_log_progress", value=True)
            yield Checkbox("✓ Good", id="check_log_success", value=True)
            yield Checkbox("✗ Bad", id="check_log_error", value=True)
            yield Static("", classes="filter-spacer")
            yield Checkbox(
                "• Debug",
                id="check_log_debug",
                value=False,
                classes="secondary-filter",
            )
            yield Checkbox(
                "~ Poll",
                id="check_log_poll",
                value=False,
                classes="secondary-filter",
            )

    log_area = RichLog(id="log_content", markup=True, highlight=False, wrap=False)
    log_area.border_title = "Log  [@click='app.copy_log'][$background on $primary] ⎘ [/][/]"
    yield log_area
