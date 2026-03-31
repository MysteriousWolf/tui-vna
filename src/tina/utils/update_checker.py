"""GitHub release update checker."""

import json
from dataclasses import dataclass
from urllib.error import URLError
from urllib.request import Request, urlopen

from packaging.version import Version

GITHUB_RELEASES_URL = "https://api.github.com/repos/MysteriousWolf/tui-vna/releases"


@dataclass
class ReleaseInfo:
    """Parsed metadata for a single GitHub release."""

    version: str
    is_prerelease: bool
    changelog: str
    html_url: str


# --- Test data ---------------------------------------------------------------

_LOREM_FALLBACK = [
    "Pellentesque habitant morbi tristique senectus et netus. "
    "Quisque porta volutpat erat. Donec aliquet.",
    "Curabitur pretium tincidunt lacus. Nulla gravida orci a odio. "
    "Nullam varius. Nulla facilisi.",
    "Fusce fermentum. Nullam varius nulla facilisi. "
    "Cras ornare tristique elit. Vivamus egestas.",
    "Morbi lectus risus, iaculis vel, suscipit quis, luctus non, massa. "
    "Fusce ac turpis quis ligula lacinia aliquet.",
    "Vestibulum ante ipsum primis in faucibus orci luctus et ultrices. "
    "Posuere cubilia curae. Nulla dapibus dolor vel est.",
    "Aliquam erat volutpat. Nam dui mi, tincidunt quis, accumsan porttitor, "
    "facilisis luctus, metus. Phasellus ultrices nulla quis nibh.",
]


def _fetch_lorem_paragraphs(count: int) -> list[str]:
    """Fetch plain-text lorem ipsum paragraphs from loripsum.net."""
    url = f"https://loripsum.net/api/{count}/short/plaintext"
    try:
        req = Request(url, headers={"User-Agent": "tina-vna"})
        with urlopen(req, timeout=5) as resp:
            text = resp.read().decode().strip()
        paras = [p.strip() for p in text.split("\n\n") if p.strip()]
        if paras:
            return paras
    except (URLError, OSError, ValueError):
        pass
    return list(_LOREM_FALLBACK[:count])


def _format_fake_version_section(version: str, paragraphs: list[str]) -> str:
    """Format a fake changelog section for one version."""
    section_headers = ["### New Features", "### Improvements", "### Bug Fixes"]
    lines = [f"## v{version}", ""]
    for i, para in enumerate(paragraphs):
        lines.append(section_headers[i % len(section_headers)])
        sentences = [
            s.strip() for s in para.replace("\n", " ").split(". ") if s.strip()
        ]
        for sentence in sentences:
            lines.append(f"- {sentence.rstrip('.')}.")
        lines.append("")
    return "\n".join(lines).rstrip()


def fetch_test_update_data(
    current_version: str,
) -> "tuple[str, ReleaseInfo, ReleaseInfo]":
    """Return fake (welcome_changelog, stable_release, prerelease_release) for UI testing.

    Content is fetched from loripsum.net and falls back to static text on failure.
    """
    paragraphs = _fetch_lorem_paragraphs(6)

    try:
        current = Version(current_version)
        major, minor, patch = current.major, current.minor, current.micro
    except Exception:
        major, minor, patch = 0, 1, 0

    v_prev = f"{major}.{minor}.{max(0, patch - 1)}"
    v_stable = f"{major}.{minor + 1}.0"
    v_pre = f"{major}.{minor + 1}.1b1"

    welcome = (
        _format_fake_version_section(v_prev, paragraphs[0:2])
        + "\n\n---\n\n"
        + _format_fake_version_section(current_version, paragraphs[2:4])
    )

    stable = ReleaseInfo(
        version=v_stable,
        is_prerelease=False,
        changelog=_format_fake_version_section(v_stable, paragraphs[4:5]),
        html_url="https://github.com/MysteriousWolf/tui-vna/releases",
    )
    pre = ReleaseInfo(
        version=v_pre,
        is_prerelease=True,
        changelog=(
            f"Pre-release **v{v_pre}** includes experimental features "
            f"that are not yet ready for production use.\n\n"
            f"{paragraphs[5] if len(paragraphs) > 5 else paragraphs[0]}\n\n"
            f"[View on GitHub](https://github.com/MysteriousWolf/tui-vna/releases)"
        ),
        html_url="https://github.com/MysteriousWolf/tui-vna/releases",
    )
    return welcome, stable, pre


# --- GitHub API --------------------------------------------------------------


def _fetch_releases() -> list[dict]:
    """Fetch all releases from the GitHub API and return them as a list of dicts."""
    req = Request(
        GITHUB_RELEASES_URL,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "tina-vna",
        },
    )
    with urlopen(req, timeout=5) as resp:
        return json.loads(resp.read().decode())


def get_changelogs_since(since_version: str, up_to_version: str) -> str:
    """Return combined changelog for all stable releases after since_version
    up to and including up_to_version, oldest-first.

    Returns an empty string if nothing is found or the request fails.
    """
    try:
        releases = _fetch_releases()
    except (URLError, OSError, ValueError):
        return ""

    try:
        since = Version(since_version)
        up_to = Version(up_to_version)
    except Exception:
        return ""

    entries: list[tuple[Version, str, str]] = []  # (ver, tag_str, body)
    for release in releases:
        if release.get("draft") or release.get("prerelease"):
            continue
        tag = release.get("tag_name", "").lstrip("v").strip()
        try:
            v = Version(tag)
        except Exception:
            continue
        if v.is_prerelease:
            continue
        if since < v <= up_to:
            body = release.get("body") or ""
            entries.append((v, tag, body))

    if not entries:
        return ""

    entries.sort(key=lambda e: e[0])
    sections = []
    for v, tag, body in entries:
        header = f"## v{tag}"
        sections.append(f"{header}\n\n{body}" if body else header)
    return "\n\n---\n\n".join(sections)


def get_update_info(
    current_version: str,
) -> tuple["ReleaseInfo | None", "ReleaseInfo | None"]:
    """Check GitHub for newer releases.

    Returns (stable_update, prerelease_update). Each is None if no newer
    release of that type exists.
    """
    try:
        releases = _fetch_releases()
    except (URLError, OSError, ValueError):
        return None, None

    try:
        current = Version(current_version)
    except Exception:
        return None, None

    latest_stable: ReleaseInfo | None = None
    latest_pre: ReleaseInfo | None = None

    for release in releases:
        if release.get("draft"):
            continue
        tag = release.get("tag_name", "").lstrip("v").strip()
        try:
            v = Version(tag)
        except Exception:
            continue

        if v <= current:
            continue

        is_pre = release.get("prerelease", False) or v.is_prerelease
        info = ReleaseInfo(
            version=tag,
            is_prerelease=is_pre,
            changelog=release.get("body") or "",
            html_url=release.get("html_url", ""),
        )
        if not is_pre and (latest_stable is None or v > Version(latest_stable.version)):
            latest_stable = info
        elif is_pre and (latest_pre is None or v > Version(latest_pre.version)):
            latest_pre = info

    return latest_stable, latest_pre
