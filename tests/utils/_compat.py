"""Test-compatibility shim for monkeypatched tina.main globals."""

from __future__ import annotations


def resolve_main_compat_attr(name: str, default: object) -> object:
    """Resolve a top-level tina.main attribute that tests may have replaced."""
    try:
        import tina.main as main_module

        return getattr(main_module, name, default)
    except (ImportError, AttributeError):
        return default
