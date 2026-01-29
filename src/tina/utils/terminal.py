"""
Terminal detection and configuration utilities.

Provides functions to detect terminal emulator capabilities,
including font family and size detection.
"""

import json
import os
import platform
import re
import subprocess
from pathlib import Path


def get_terminal_font() -> tuple[str, float | None]:
    """
    Detect the terminal's font family and size by parsing its config file.

    Uses TERM_PROGRAM environment variable to identify the terminal emulator,
    then reads its configuration file to extract the font family and size.
    Falls back to ('monospace', None).

    Supported terminals: Ghostty, Kitty, Alacritty, WezTerm, iTerm2,
    Windows Terminal.

    Returns:
        Tuple of (font_family, font_size_pt)
    """
    try:
        import matplotlib.font_manager as fm

        available_fonts = {f.name for f in fm.fontManager.ttflist}
    except ImportError:
        available_fonts = set()

    term = os.environ.get("TERM_PROGRAM", "").lower()
    home = Path.home()
    font_name = None
    font_size = None

    def _parse_ghostty_config() -> None:
        nonlocal font_name, font_size
        cfg = home / ".config" / "ghostty" / "config"
        if cfg.exists():
            for line in cfg.read_text().splitlines():
                line = line.strip()
                if line.startswith("#"):
                    continue
                if line.startswith("font-family") and not font_name:
                    font_name = line.split("=", 1)[1].strip().strip("\"'")
                elif line.startswith("font-size") and not font_size:
                    try:
                        font_size = float(line.split("=", 1)[1].strip().strip("\"'"))
                    except ValueError:
                        pass
            # Ghostty default font-size is 13
            if not font_size:
                font_size = 13.0

    try:
        if "ghostty" in term:
            _parse_ghostty_config()

        elif "kitty" in term:
            # ~/.config/kitty/kitty.conf:
            #   font_family Font Name
            #   font_size 12.0
            cfg = home / ".config" / "kitty" / "kitty.conf"
            if cfg.exists():
                for line in cfg.read_text().splitlines():
                    line = line.strip()
                    if line.startswith("font_family") and not font_name:
                        font_name = line.split(None, 1)[1].strip().strip("\"'")
                    elif line.startswith("font_size") and not font_size:
                        try:
                            font_size = float(line.split(None, 1)[1].strip())
                        except (ValueError, IndexError):
                            pass

        elif "alacritty" in term:
            # ~/.config/alacritty/alacritty.toml or alacritty.yml
            for name in ("alacritty.toml", "alacritty.yml"):
                cfg = home / ".config" / "alacritty" / name
                if cfg.exists():
                    text = cfg.read_text()
                    if name.endswith(".toml"):
                        m = re.search(
                            r'\[font\.normal\]\s*\n\s*family\s*=\s*["\']([^"\']+)',
                            text,
                        )
                        if m:
                            font_name = m.group(1)
                        m = re.search(
                            r"\[font\]\s*\n(?:.*\n)*?\s*size\s*=\s*([\d.]+)", text
                        )
                        if m:
                            font_size = float(m.group(1))
                    else:
                        m = re.search(
                            r'font:\s*\n\s*normal:\s*\n\s*family:\s*["\']?([^\n"\']+)',
                            text,
                        )
                        if m:
                            font_name = m.group(1).strip()
                        m = re.search(r"font:\s*\n(?:.*\n)*?\s*size:\s*([\d.]+)", text)
                        if m:
                            font_size = float(m.group(1))
                    if font_name:
                        break

        elif "wezterm" in term:
            # ~/.config/wezterm/wezterm.lua or ~/.wezterm.lua:
            #   font = wezterm.font("Font Name")
            #   font_size = 12.0
            for cfg in (
                home / ".config" / "wezterm" / "wezterm.lua",
                home / ".wezterm.lua",
            ):
                if cfg.exists():
                    text = cfg.read_text()
                    m = re.search(
                        r'font\s*=\s*wezterm\.font\s*\(\s*["\']([^"\']+)', text
                    )
                    if m:
                        font_name = m.group(1)
                    m = re.search(r"font_size\s*=\s*([\d.]+)", text)
                    if m:
                        font_size = float(m.group(1))
                    if font_name:
                        break

        elif "iterm" in term:
            # macOS: defaults read com.googlecode.iterm2
            if platform.system() == "Darwin":
                result = subprocess.run(
                    ["defaults", "read", "com.googlecode.iterm2", "Normal Font"],
                    capture_output=True,
                    text=True,
                    timeout=2,
                )
                if result.returncode == 0:
                    # Output like: "HackNF-Regular 13"
                    raw = result.stdout.strip()
                    parts = raw.rsplit(" ", 1)
                    font_name = parts[0].replace("-Regular", "")
                    if len(parts) == 2:
                        try:
                            font_size = float(parts[1])
                        except ValueError:
                            pass

        elif platform.system() == "Windows":
            # Windows Terminal: settings.json
            local_app = os.environ.get("LOCALAPPDATA", "")
            if local_app:
                wt_dir = Path(local_app) / "Packages"
                if wt_dir.exists():
                    for pkg in wt_dir.iterdir():
                        if "WindowsTerminal" in pkg.name:
                            settings = pkg / "LocalState" / "settings.json"
                            if settings.exists():
                                data = json.loads(settings.read_text())
                                profiles = data.get("profiles", {})
                                defaults = profiles.get("defaults", {})
                                font_cfg = defaults.get("font", {})
                                face = font_cfg.get("face")
                                if face:
                                    font_name = face
                                size = font_cfg.get("size")
                                if size:
                                    font_size = float(size)
                                break

        # Fallback: if TERM_PROGRAM didn't match, try detecting from config files
        if not font_name:
            _parse_ghostty_config()

    except Exception:
        pass

    # Resolve font name against available fonts
    resolved_name = "monospace"
    if font_name and available_fonts:
        # Exact match first
        if font_name in available_fonts:
            resolved_name = font_name
        else:
            # Fuzzy match: try case-insensitive, then substring matching
            lower_name = font_name.lower()
            for af in available_fonts:
                if af.lower() == lower_name:
                    resolved_name = af
                    break
            else:
                # Substring: pick the shortest available name that contains
                # the config name (or vice versa) to find the closest match
                candidates = [
                    af
                    for af in available_fonts
                    if lower_name in af.lower() or af.lower() in lower_name
                ]
                if candidates:
                    resolved_name = min(candidates, key=len)

    return resolved_name, font_size
