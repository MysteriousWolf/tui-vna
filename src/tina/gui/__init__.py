"""GUI package exports for the TINA Textual application.

This package keeps its top-level app exports lazy so importing GUI subpackages
from ``tina.main`` does not create a circular import back into ``tina.main``.
"""

from __future__ import annotations

from typing import Any

VNAApp = None
run_gui = None
main = None

__all__ = ["VNAApp", "run_gui", "main"]


def __getattr__(name: str) -> Any:
    """Lazily resolve GUI app entry points from ``tina.main``."""
    if name in __all__:
        from ..main import VNAApp, main, run_gui

        exports = {
            "VNAApp": VNAApp,
            "run_gui": run_gui,
            "main": main,
        }
        return exports[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> list[str]:
    """Expose lazy exports in interactive introspection."""
    return sorted(__all__)
