"""Update notification modal screens for the TINA GUI."""

from __future__ import annotations

import webbrowser
from typing import Literal, cast

from textual import on
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Label, Markdown, Static

ButtonVariantName = Literal["default", "primary", "success", "warning", "error"]
DEFAULT_GITHUB_RELEASES_URL = "https://github.com/MysteriousWolf/tui-vna/releases"
DEFAULT_GITHUB_RELEASE_URL = "https://github.com/MysteriousWolf/tui-vna/releases/latest"


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
        button_variant: ButtonVariantName = "primary",
        badge: str | None = None,
        badge_class: str | None = None,
        github_url: str | None = None,
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
        self._github_url = github_url or DEFAULT_GITHUB_RELEASE_URL
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
                    variant=cast(ButtonVariantName, self._button_variant),
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
        """Open the relevant GitHub release page in the system browser."""
        webbrowser.open(self._github_url)

    def action_close(self) -> None:
        """Close the notification modal."""
        self.dismiss()

    @on(Button.Pressed, "#btn-notif-dismiss")
    def dismiss_notification(self) -> None:
        """Dismiss the modal screen."""
        self.dismiss()


def _build_release_url(version: str, fallback_url: str | None = None) -> str:
    """Return the specific GitHub release URL when the release tag is known."""
    normalized_version = version.strip()
    if normalized_version:
        tag = (
            normalized_version
            if normalized_version.startswith("v")
            else f"v{normalized_version}"
        )
        return f"{DEFAULT_GITHUB_RELEASES_URL}/tag/{tag}"
    if fallback_url:
        return fallback_url
    return DEFAULT_GITHUB_RELEASE_URL


def build_update_screen(release_info) -> UpdateNotificationScreen:
    """Create an update notification screen configured for the given release information."""
    rel = release_info
    release_url = _build_release_url(rel.version, rel.html_url or None)
    if rel.is_prerelease:
        intro = f"A new pre-release **v{rel.version}** is available.\n\n"
        body = intro + (
            rel.changelog if rel.changelog else f"[View on GitHub]({release_url})"
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
        github_url=release_url,
    )


def build_welcome_screen(version: str, changelog: str) -> UpdateNotificationScreen:
    """Build an update notification screen for the post-update welcome."""
    release_url = _build_release_url(version)
    return UpdateNotificationScreen(
        title=f"Thanks for updating to v{version}!",
        body=changelog,
        button_label="Got it!",
        button_variant="success",
        github_url=release_url,
        welcome=True,
    )
