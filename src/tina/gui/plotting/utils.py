"""Utility helpers for GUI plotting and display formatting."""

from __future__ import annotations

from pathlib import Path


def truncate_path_intelligently(path_str: str, max_width: int) -> str:
    """
    Intelligently truncate a file path to fit within a given width.

    Strategy:
    1. If path fits, return as-is
    2. Progressively drop folders from the left
    3. Try showing only first letter of remaining folders
    4. Try showing only filename
    5. Truncate filename with ellipsis

    Args:
        path_str: The full path string.
        max_width: Maximum character width.

    Returns:
        Truncated path string.
    """
    # Account for the 📁 emoji (2 wide chars) + space = 3 chars
    if max_width <= 3:
        return ""

    effective_width = max_width - 3

    if len(path_str) <= effective_width:
        return path_str

    path = Path(path_str)
    parts = list(path.parts)

    if len(parts) <= 1:
        filename = path.name
        if len(filename) > effective_width and effective_width > 3:
            return filename[: effective_width - 3] + "..."
        return filename[:effective_width]

    for i in range(1, len(parts) - 1):
        truncated = ".../" + "/".join(parts[i:])
        if len(truncated) <= effective_width:
            return truncated

    if len(parts) > 1:
        root = "/" if parts[0] in ("", "/") else ""
        middle_parts = parts[1:-1] if root else parts[:-1]
        middle = "/".join(p[0] for p in middle_parts)
        abbreviated = root + (middle + "/" if middle else "") + parts[-1]
        if len(abbreviated) <= effective_width:
            return abbreviated

        abbreviated_with_ellipsis = (
            ".../"
            + "/".join(p[0] for p in parts[1:-1])
            + ("/" if len(parts) > 2 else "")
            + parts[-1]
        )
        if len(abbreviated_with_ellipsis) <= effective_width:
            return abbreviated_with_ellipsis

    filename = path.name
    if len(filename) <= effective_width:
        return filename

    if effective_width > 3:
        return filename[: effective_width - 3] + "..."
    return filename[:effective_width]
