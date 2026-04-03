"""
Entry point wrapper that shows a startup progress bar while loading heavy dependencies.

Pre-importing modules before tina.main is loaded ensures they are already in
sys.modules when main.py's module-level imports run, making those lookups instant.
"""

from __future__ import annotations

from collections.abc import Callable


def _import_numpy() -> None:
    """Preload NumPy."""
    import numpy as _np  # noqa: F401


def _import_matplotlib() -> None:
    """Preload Matplotlib and force the non-interactive backend."""
    import matplotlib as _mpl  # noqa: F401

    _mpl.use("Agg")
    import matplotlib.pyplot as _plt  # noqa: F401


def _import_skrf() -> None:
    """Preload scikit-rf."""
    import skrf as _rf  # noqa: F401


def _import_pyvisa() -> None:
    """Preload PyVISA."""
    import pyvisa as _visa  # noqa: F401


def _import_textual() -> None:
    """Preload Textual modules used during app startup."""
    import textual as _textual  # noqa: F401
    import textual.app  # noqa: F401
    import textual.binding  # noqa: F401
    import textual.command  # noqa: F401
    import textual.containers  # noqa: F401
    import textual.screen  # noqa: F401
    import textual.widgets  # noqa: F401


def _import_tina_main() -> Callable[[], object]:
    """Import and return the main TINA entry point."""
    from .main import main as app_main

    return app_main


_IMPORT_STEPS: tuple[tuple[str, Callable[[], None]], ...] = (
    ("numpy", _import_numpy),
    ("matplotlib", _import_matplotlib),
    ("scikit-rf", _import_skrf),
    ("pyvisa", _import_pyvisa),
    ("textual", _import_textual),
)


def main() -> None:
    """Show a startup progress bar while pre-loading heavy dependencies, then launch the app."""
    import sys

    # Skip bar for --help/-h (output would be garbled) and --now (CLI mode)
    skip_bar = any(arg in sys.argv[1:] for arg in ("--help", "-h", "--now"))

    if skip_bar:
        from .main import main as app_main

        app_main()
        return

    from rich.progress import BarColumn, Progress, TaskProgressColumn, TextColumn

    total_steps = len(_IMPORT_STEPS) + 1  # final step imports tina.main itself

    with Progress(
        BarColumn(bar_width=40),
        TaskProgressColumn(),
        TextColumn("[cyan]Loading {task.description}[/cyan]"),
        transient=True,
    ) as progress:
        task = progress.add_task("...", total=total_steps)

        for description, import_step in _IMPORT_STEPS:
            progress.update(task, description=description)
            import_step()
            progress.advance(task)

        progress.update(task, description="tina")
        app_main = _import_tina_main()
        progress.advance(task)

    app_main()
