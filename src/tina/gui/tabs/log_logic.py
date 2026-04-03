"""Log formatting, filtering, and display helpers for the TINA GUI."""

from __future__ import annotations

from datetime import datetime

from rich.markup import escape as rich_escape
from textual.widgets import Checkbox, RichLog

LOG_FILTER_IDS: dict[str, str] = {
    "tx": "#check_log_tx",
    "rx": "#check_log_rx",
    "info": "#check_log_info",
    "progress": "#check_log_progress",
    "success": "#check_log_success",
    "error": "#check_log_error",
    "debug": "#check_log_debug",
    "poll": "#check_log_poll",
}


def build_style_map(app) -> dict[str, tuple[str, str]]:
    """Build the level→(icon, style) map from current Textual theme variables."""
    variables = app.get_css_variables()
    color_tx = variables.get("accent", "#ffa62b")
    color_rx = variables.get("secondary", "#0178D4")
    color_success = variables.get("success", "#4EBF71")
    color_error = variables.get("error", "#ba3c5b")
    return {
        "tx": ("↑", color_tx),
        "rx": ("↓", color_rx),
        "tx/poll": ("↑~", f"dim {color_tx}"),
        "rx/poll": ("↓~", f"dim {color_rx}"),
        "tx/debug": ("↑•", "dim"),
        "rx/debug": ("↓•", "dim"),
        "info": ("i", "default"),
        "success": ("✓", f"bold {color_success}"),
        "error": ("✗", f"bold {color_error}"),
        "progress": ("⋯", "dim italic"),
        "debug": ("•", "dim"),
    }


def format_log_entry(app, entry: dict) -> str:
    """Render a stored log entry to Rich markup."""
    if app._cached_style_map is None:
        app._cached_style_map = build_style_map(app)
    icon, style = app._cached_style_map.get(entry["level"], ("•", "default"))
    safe_message = rich_escape(entry["message"])
    return f"[dim]{entry['timestamp']}[/dim] [{style}]{icon}[/] {safe_message}"


def should_show_log(app, level: str) -> bool:
    """Return True if *level* passes all active log filter checkboxes."""
    try:
        if "/" in level:
            primary, secondary = level.split("/", 1)
            primary_id = LOG_FILTER_IDS.get(primary)
            secondary_id = LOG_FILTER_IDS.get(secondary)
            primary_ok = (
                app.query_one(primary_id, Checkbox).value if primary_id else True
            )
            secondary_ok = (
                app.query_one(secondary_id, Checkbox).value if secondary_id else True
            )
            return primary_ok and secondary_ok

        checkbox_id = LOG_FILTER_IDS.get(level)
        if checkbox_id:
            return app.query_one(checkbox_id, Checkbox).value
        return True
    except Exception:
        return True


def refresh_log_display(app) -> None:
    """Rebuild log display from stored entries using current theme colors and filters."""
    log_content = app.query_one("#log_content", RichLog)
    log_content.clear()
    for entry in app.log_messages:
        if should_show_log(app, entry["level"]):
            log_content.write(format_log_entry(app, entry))
    log_content.scroll_end(animate=False)


def log_message(app, message: str, level: str = "info") -> None:
    """Add a message to the stored log and visible log widget if enabled."""
    log_entry = {
        "timestamp": datetime.now().strftime("%H:%M:%S"),
        "level": level,
        "message": message,
    }
    app.log_messages.append(log_entry)

    if should_show_log(app, level):
        log_content = app.query_one("#log_content", RichLog)
        log_content.write(format_log_entry(app, log_entry))
        log_content.scroll_end(animate=False)


def handle_log_filter_change(app) -> None:
    """Refresh the visible log when any log filter checkbox changes."""
    refresh_log_display(app)


def copy_log(app) -> None:
    """Copy visible log entries as plain text to the system clipboard."""
    style_map = app._cached_style_map or build_style_map(app)
    lines = [
        f"{entry['timestamp']} {style_map.get(entry['level'], ('•', ''))[0]} {entry['message']}"
        for entry in app.log_messages
        if should_show_log(app, entry["level"])
    ]
    app.copy_to_clipboard("\n".join(lines))
    app.notify("Log copied to clipboard", timeout=2)
