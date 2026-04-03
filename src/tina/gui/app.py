"""Lazy GUI application entry points for the TINA Textual interface."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..main import VNAApp, main, run_gui
else:
    VNAApp = None
    run_gui = None
    main = None

__all__ = ["VNAApp", "run_gui", "main"]


def __getattr__(name: str) -> Any:
    """Resolve GUI app exports lazily to avoid circular imports with ``tina.main``."""
    if name in __all__:
        from .. import main as main_module

        return getattr(main_module, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
