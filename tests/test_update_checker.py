"""Focused regression tests for update flow fixes."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from tina.gui.modals.update_notification import (
    DEFAULT_GITHUB_RELEASE_LATEST_URL,
    DEFAULT_GITHUB_RELEASES_LIST_URL,
    build_update_screen,
    build_welcome_screen,
)
from tina.utils.update_checker import ReleaseInfo, _fetch_releases


def _mock_urlopen_payload(payload: object) -> MagicMock:
    """Return a context-manager MagicMock simulating a urllib response.

    Args:
        payload: Any JSON-serialisable object; encoded to bytes and returned by
            ``response.read()``.

    Returns:
        A ``MagicMock`` configured as a context manager whose ``__enter__``
        returns itself and whose ``read()`` yields the JSON-encoded bytes of
        *payload*.
    """
    response = MagicMock()
    response.read.return_value = json.dumps(payload).encode()
    response.__enter__.return_value = response
    response.__exit__.return_value = False
    return response


@pytest.mark.parametrize("payload", [{}, "oops", None])
def test_fetch_releases_rejects_non_list_payloads(payload: object) -> None:
    """The GitHub API payload must be a JSON list of release objects."""
    with patch(
        "tina.utils.update_checker.urlopen",
        return_value=_mock_urlopen_payload(payload),
    ):
        with pytest.raises(ValueError, match="payload must be a list"):
            _fetch_releases()


def test_update_modal_opens_release_specific_url() -> None:
    """The modal should use the API-provided html_url when present."""
    api_url = f"{DEFAULT_GITHUB_RELEASES_LIST_URL}/tag/v1.2.3"
    release = ReleaseInfo(
        version="1.2.3",
        is_prerelease=False,
        changelog="Bug fixes.",
        html_url=api_url,
    )
    screen = build_update_screen(release)

    with patch("tina.gui.modals.update_notification.webbrowser.open") as open_browser:
        screen.open_github_release()

    open_browser.assert_called_once_with(api_url)


def test_update_modal_constructs_tag_url_when_html_url_absent() -> None:
    """Without an API-provided URL, the modal should construct a tag URL from the version."""
    release = ReleaseInfo(
        version="1.2.3",
        is_prerelease=False,
        changelog="Bug fixes.",
        html_url="",
    )
    screen = build_update_screen(release)

    with patch("tina.gui.modals.update_notification.webbrowser.open") as open_browser:
        screen.open_github_release()

    open_browser.assert_called_once_with(
        f"{DEFAULT_GITHUB_RELEASES_LIST_URL}/tag/v1.2.3"
    )


def test_update_modal_falls_back_when_release_url_missing() -> None:
    """The update modal should fall back safely when no release URL is present."""
    release = ReleaseInfo(
        version="",
        is_prerelease=False,
        changelog="Bug fixes.",
        html_url="",
    )
    screen = build_update_screen(release)

    with patch("tina.gui.modals.update_notification.webbrowser.open") as open_browser:
        screen.open_github_release()

    open_browser.assert_called_once_with(DEFAULT_GITHUB_RELEASE_LATEST_URL)


@pytest.mark.parametrize(
    "version,html_url,expected",
    [
        # Version present → tag URL regardless of html_url
        ("1.2.3", "", f"{DEFAULT_GITHUB_RELEASES_LIST_URL}/tag/v1.2.3"),
        # Version absent, html_url present → html_url used as fallback
        (
            "",
            "https://github.com/MysteriousWolf/tui-vna/releases/tag/v0.9.0",
            "https://github.com/MysteriousWolf/tui-vna/releases/tag/v0.9.0",
        ),
    ],
)
def test_update_modal_fallback_isolates_missing_field(
    version: str, html_url: str, expected: str
) -> None:
    """open_github_release should use version tag URL or html_url individually."""
    release = ReleaseInfo(
        version=version,
        is_prerelease=False,
        changelog="Bug fixes.",
        html_url=html_url,
    )
    screen = build_update_screen(release)

    with patch("tina.gui.modals.update_notification.webbrowser.open") as open_browser:
        screen.open_github_release()

    open_browser.assert_called_once_with(expected)


@pytest.mark.parametrize("version", ["1.2.3", "v1.2.3"])
def test_update_modal_title_uses_single_leading_v(version: str) -> None:
    """Update titles should normalize plain and prefixed versions to one leading v."""
    release = ReleaseInfo(
        version=version,
        is_prerelease=False,
        changelog="Bug fixes.",
        html_url="https://github.com/MysteriousWolf/tui-vna/releases/latest",
    )

    screen = build_update_screen(release)

    assert screen._title == "Update available: v1.2.3"


@pytest.mark.parametrize("version", ["1.2.3", "v1.2.3"])
def test_welcome_modal_title_uses_single_leading_v(version: str) -> None:
    """Welcome titles should normalize plain and prefixed versions to one leading v."""
    screen = build_welcome_screen(version, "Thanks for updating.")

    assert screen._title == "Thanks for updating to v1.2.3!"
