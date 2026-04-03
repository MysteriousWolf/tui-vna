"""Update notification modal screens for the TINA GUI."""

from __future__ import annotations

import webbrowser

from textual import on
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Label, Markdown, Static


class UpdateNotificationScreen(ModalScreen):
    """Reusable modal for update-related notifications."""

    CSS_PATH = ["gui/styles/update_dialogs.tcss"]

    BINDINGS = [
        ("escape", "close", "Close"),
    ]

    def __init__(
        self,
        title: str,
        body: str,
        button_label: str,
        button_variant: str = "primary",
        badge: str | None = None,
        badge_class: str | None = None,
        welcome: bool = False,
    ) -> None:
        """Initialise the notification screen with title, markdown body, and button config."""
        super().__init__()
        self._title = title
        self._body = body or "_No changelog provided._"
        self._button_label = button_label
        self._button_variant = button_variant
        self._badge = badge
        self._badge_class = badge_class
        if welcome:
            self.add_class("--welcome")

    def compose(self) -> ComposeResult:
        """Compose the modal layout: title row, scrollable body, and dismiss button."""
        with Vertical(id="notif-dialog"):
            with Horizontal(id="notif-header"):
                yield Label(self._title, id="notif-title")
                if self._badge:
                    yield Label(
                        f" {self._badge} ",
                        id="notif-badge",
                        classes=self._badge_class or "",
                    )
            with VerticalScroll(id="notif-body"):
                yield Markdown(self._body)
            with Horizontal(id="notif-footer"):
                yield Button(
                    self._button_label,
                    variant=self._button_variant,
                    id="btn-notif-dismiss",
                    classes="notif-btn",
                    flat=True,
                )
                yield Static(id="footer-spacer")
                yield Button(
                    "View on GitHub",
                    variant="primary",
                    id="btn-notif-github",
                    classes="notif-btn",
                    flat=True,
                )

    @on(Button.Pressed, "#btn-notif-github")
    def open_github_release(self) -> None:
        """Open the latest releases page in the system browser."""
        webbrowser.open("https://github.com/MysteriousWolf/tui-vna/releases/latest")

    def action_close(self) -> None:
        """Close the notification modal."""
        self.dismiss()

    @on(Button.Pressed, "#btn-notif-dismiss")
    def dismiss_notification(self) -> None:
        """Dismiss the modal screen."""
        self.dismiss()


def build_update_screen(release_info) -> UpdateNotificationScreen:
    """Create an update notification screen configured for the given release information."""
    rel = release_info
    if rel.is_prerelease:
        intro = f"A new pre-release **v{rel.version}** is available.\n\n"
        body = intro + (
            rel.changelog if rel.changelog else f"[View on GitHub]({rel.html_url})"
        )
        badge, badge_class = "PRE-RELEASE", "badge-pre"
    else:
        body = rel.changelog or "_No changelog provided._"
        badge, badge_class = "STABLE", "badge-stable"
    return UpdateNotificationScreen(
        title=f"Update available:  v{rel.version}",
        body=body,
        button_label="Dismiss",
        badge=badge,
        badge_class=badge_class,
    )


def build_welcome_screen(version: str, changelog: str) -> UpdateNotificationScreen:
    """Build an update notification screen for the post-update welcome."""
    return UpdateNotificationScreen(
        title=f"Thanks for updating to v{version}!",
        body=changelog,
        button_label="Got it!",
        button_variant="success",
        welcome=True,
    )
