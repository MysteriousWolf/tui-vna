"""
One-time migration from the legacy hp-e5071b config directory to tina.

Shipped until v0.3.0. On first launch after upgrading, this module
detects the old ~/.config/hp-e5071b/ folder, merges settings.json and
update_state.json into the new YAML format under ~/.config/tina/, then
removes the old directory.

The migration is silently skipped on any error so it never blocks startup.
"""

import json
import shutil
from dataclasses import fields
from pathlib import Path

from platformdirs import user_config_dir

_OLD_APP_NAME = "hp-e5071b"
_NEW_APP_NAME = "tina"


def migrate_legacy_config() -> str | None:
    """Migrate settings from the legacy hp-e5071b directory if present.

    Returns a human-readable log message when migration ran, None otherwise.
    Does nothing (and returns None) if the new config already exists.
    """
    old_dir = Path(user_config_dir(_OLD_APP_NAME))
    new_dir = Path(user_config_dir(_NEW_APP_NAME))

    if not old_dir.exists():
        return None

    new_settings_file = new_dir / "settings.yaml"

    # New config already present — just clean up the orphaned old directory.
    if new_settings_file.exists():
        _try_remove(old_dir)
        return None

    try:
        merged: dict = {}

        # Read old settings.json
        old_settings = old_dir / "settings.json"
        if old_settings.exists():
            try:
                with open(old_settings, encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, dict):
                    merged.update(data)
            except (OSError, json.JSONDecodeError, ValueError):
                pass

        # Read old update_state.json and fold into merged dict
        old_state = old_dir / "update_state.json"
        if old_state.exists():
            try:
                with open(old_state, encoding="utf-8") as f:
                    state = json.load(f)
                if isinstance(state, dict):
                    merged["last_acknowledged_version"] = state.get(
                        "last_acknowledged_version", ""
                    )
                    merged["notified_prerelease"] = state.get("notified_prerelease", "")
            except (OSError, json.JSONDecodeError, ValueError):
                pass

        # Import here to avoid circular imports at module level
        from .settings import AppSettings, SettingsManager

        valid = {f.name for f in fields(AppSettings)}
        filtered = {k: v for k, v in merged.items() if k in valid}

        try:
            settings = AppSettings(**filtered)
        except (TypeError, ValueError):
            settings = AppSettings()

        sm = SettingsManager()
        sm.save(settings)

    except Exception:
        # Migration must never crash the app
        return None

    _try_remove(old_dir)
    return (
        f"Migrated settings from ~/.config/{_OLD_APP_NAME} "
        f"to ~/.config/{_NEW_APP_NAME}"
    )


def _try_remove(path: Path) -> None:
    """Remove a directory tree, ignoring all errors."""
    try:
        shutil.rmtree(path)
    except OSError:
        pass
