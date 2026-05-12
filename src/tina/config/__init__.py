"""Configuration package exports."""

from . import constants
from .constants import *  # noqa: F401, F403  # backward-compatibility re-export
from .migration import migrate_legacy_config
from .settings import AppSettings, SettingsManager

__all__ = [
    "AppSettings",
    "SettingsManager",
    "constants",
    "migrate_legacy_config",
    *getattr(constants, "__all__", [name for name in dir(constants) if name.isupper()]),
]
