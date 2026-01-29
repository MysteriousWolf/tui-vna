"""
Path handling utilities for the terminal UI.

Provides intelligent path truncation and display functions.
"""

from pathlib import Path


def truncate_path_intelligently(path_str: str, max_width: int) -> str:
    """
    Intelligently truncate a file path to fit within a given width.

    Strategy:
    1. If path fits, return as-is
    2. Progressively drop folders from the left (e.g., /a/b/c/file.txt -> .../b/c/file.txt -> .../c/file.txt)
    3. Try showing only first letter of remaining folders
    4. Try showing only filename (no folders)
    5. Truncate filename with ellipsis

    Args:
        path_str: The full path string
        max_width: Maximum character width

    Returns:
        Truncated path string
    """
    # Account for the 📁 emoji (2 chars) + space in the UI
    effective_width = max_width - 2

    if len(path_str) <= effective_width:
        return path_str

    path = Path(path_str)
    parts = list(path.parts)

    if len(parts) <= 1:
        # Just a filename, truncate with ellipsis
        filename = path.name
        if len(filename) > effective_width and effective_width > 3:
            return filename[: effective_width - 3] + "..."
        return filename[:effective_width]

    # Strategy 2: Progressively drop folders from the left
    for i in range(1, len(parts) - 1):
        truncated = ".../" + "/".join(parts[i:])
        if len(truncated) <= effective_width:
            return truncated

    # Strategy 3: First letter of remaining folders + full filename
    if len(parts) > 1:
        abbreviated = "/".join(p[0] for p in parts[:-1]) + "/" + parts[-1]
        if len(abbreviated) <= effective_width:
            return abbreviated
        # Try with ellipsis prefix
        abbreviated_with_ellipsis = (
            ".../"
            + "/".join(p[0] for p in parts[1:-1])
            + ("/" if len(parts) > 2 else "")
            + parts[-1]
        )
        if len(abbreviated_with_ellipsis) <= effective_width:
            return abbreviated_with_ellipsis

    # Strategy 4: Just the filename
    filename = path.name
    if len(filename) <= effective_width:
        return filename

    # Strategy 5: Truncate filename with ellipsis
    if effective_width > 3:
        return filename[: effective_width - 3] + "..."
    else:
        return filename[:effective_width]
