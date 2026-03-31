"""Tests for update checker utilities."""

from unittest.mock import MagicMock, patch

from tina.utils.update_checker import (
    _LOREM_FALLBACK,
    ReleaseInfo,
    _fetch_lorem_paragraphs,
    _format_fake_version_section,
    fetch_test_update_data,
    get_changelogs_since,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_release(
    tag: str, body: str = "", prerelease: bool = False, draft: bool = False
) -> dict:
    return {
        "tag_name": tag,
        "body": body,
        "prerelease": prerelease,
        "draft": draft,
        "html_url": f"https://github.com/example/repo/releases/tag/{tag}",
    }


# ---------------------------------------------------------------------------
# get_changelogs_since
# ---------------------------------------------------------------------------


class TestGetChangelogsSince:
    def test_returns_empty_on_fetch_error(self):
        with patch("tina.utils.update_checker._fetch_releases", side_effect=OSError):
            assert get_changelogs_since("0.1.0", "0.2.0") == ""

    def test_returns_empty_when_no_releases_in_range(self):
        releases = [_make_release("v0.1.0", "old")]
        with patch("tina.utils.update_checker._fetch_releases", return_value=releases):
            assert get_changelogs_since("0.1.0", "0.2.0") == ""

    def test_combines_versions_oldest_first(self):
        releases = [
            _make_release("v0.3.0", "Third"),
            _make_release("v0.2.0", "Second"),
            _make_release("v0.1.0", "First"),
        ]
        with patch("tina.utils.update_checker._fetch_releases", return_value=releases):
            result = get_changelogs_since("0.1.0", "0.3.0")

        assert result.index("0.2.0") < result.index("0.3.0")
        assert "Second" in result
        assert "Third" in result
        assert "First" not in result  # since_version is exclusive

    def test_skips_prereleases(self):
        releases = [
            _make_release("v0.2.0", "Stable"),
            _make_release("v0.2.1b1", "Beta", prerelease=True),
        ]
        with patch("tina.utils.update_checker._fetch_releases", return_value=releases):
            result = get_changelogs_since("0.1.0", "0.3.0")

        assert "Stable" in result
        assert "Beta" not in result

    def test_skips_drafts(self):
        releases = [
            _make_release("v0.2.0", "Real"),
            _make_release("v0.2.5", "Draft", draft=True),
        ]
        with patch("tina.utils.update_checker._fetch_releases", return_value=releases):
            result = get_changelogs_since("0.1.0", "0.3.0")

        assert "Real" in result
        assert "Draft" not in result

    def test_sections_separated_by_hr(self):
        releases = [_make_release("v0.2.0", "A"), _make_release("v0.3.0", "B")]
        with patch("tina.utils.update_checker._fetch_releases", return_value=releases):
            result = get_changelogs_since("0.1.0", "0.3.0")

        assert "---" in result

    def test_version_headers_included(self):
        releases = [_make_release("v0.2.0", "body")]
        with patch("tina.utils.update_checker._fetch_releases", return_value=releases):
            result = get_changelogs_since("0.1.0", "0.2.0")

        assert "## v0.2.0" in result


# ---------------------------------------------------------------------------
# fetch_test_update_data
# ---------------------------------------------------------------------------


class TestFetchTestUpdateData:
    def _patched(self, paragraphs=None):
        if paragraphs is None:
            paragraphs = list(_LOREM_FALLBACK)
        return patch(
            "tina.utils.update_checker._fetch_lorem_paragraphs",
            return_value=paragraphs,
        )

    def test_returns_three_items(self):
        with self._patched():
            result = fetch_test_update_data("0.1.3")
        assert len(result) == 3

    def test_welcome_is_string(self):
        with self._patched():
            welcome, _, _ = fetch_test_update_data("0.1.3")
        assert isinstance(welcome, str)
        assert len(welcome) > 0

    def test_stable_release_not_prerelease(self):
        with self._patched():
            _, stable, _ = fetch_test_update_data("0.1.3")
        assert isinstance(stable, ReleaseInfo)
        assert stable.is_prerelease is False

    def test_prerelease_is_prerelease(self):
        with self._patched():
            _, _, pre = fetch_test_update_data("0.1.3")
        assert isinstance(pre, ReleaseInfo)
        assert pre.is_prerelease is True

    def test_stable_version_is_higher(self):
        with self._patched():
            _, stable, _ = fetch_test_update_data("0.1.3")
        from packaging.version import Version

        assert Version(stable.version) > Version("0.1.3")

    def test_welcome_contains_current_version(self):
        with self._patched():
            welcome, _, _ = fetch_test_update_data("0.1.3")
        assert "0.1.3" in welcome

    def test_falls_back_when_fetch_fails(self):
        with patch(
            "tina.utils.update_checker._fetch_lorem_paragraphs",
            return_value=list(_LOREM_FALLBACK),
        ):
            welcome, stable, pre = fetch_test_update_data("0.1.3")
        assert isinstance(welcome, str)
        assert isinstance(stable, ReleaseInfo)
        assert isinstance(pre, ReleaseInfo)


# ---------------------------------------------------------------------------
# _fetch_lorem_paragraphs fallback
# ---------------------------------------------------------------------------


class TestFetchLoremParagraphs:
    def test_returns_fallback_on_network_error(self):
        with patch("tina.utils.update_checker.urlopen", side_effect=OSError):
            result = _fetch_lorem_paragraphs(3)
        assert len(result) == 3
        assert all(isinstance(p, str) and len(p) > 0 for p in result)

    def test_returns_requested_count_on_success(self):
        fake_body = "Para one.\n\nPara two.\n\nPara three."
        mock_resp = MagicMock()
        mock_resp.read.return_value = fake_body.encode()
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch("tina.utils.update_checker.urlopen", return_value=mock_resp):
            result = _fetch_lorem_paragraphs(3)
        assert result == ["Para one.", "Para two.", "Para three."]


# ---------------------------------------------------------------------------
# _format_fake_version_section
# ---------------------------------------------------------------------------


class TestFormatFakeVersionSection:
    def test_contains_version_header(self):
        result = _format_fake_version_section("1.2.3", ["Some sentence here."])
        assert "## v1.2.3" in result

    def test_sentences_become_bullets(self):
        result = _format_fake_version_section(
            "1.0.0", ["First sentence. Second sentence."]
        )
        assert "- First sentence." in result
        assert "- Second sentence." in result
