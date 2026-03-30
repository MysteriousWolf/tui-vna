"""
Entry point wrapper that shows a startup progress bar while loading heavy dependencies.

Pre-importing modules before tina.main is loaded ensures they are already in
sys.modules when main.py's module-level imports run, making those lookups instant.
"""


def main() -> None:
    """Show a startup progress bar while pre-loading heavy dependencies, then launch the app."""
    import sys

    # Skip bar for --help/-h (output would be garbled) and --now (CLI mode)
    skip_bar = any(a in sys.argv[1:] for a in ("--help", "-h", "--now"))

    if skip_bar:
        from .main import main as _main

        _main()
        return

    from rich.progress import BarColumn, Progress, TaskProgressColumn, TextColumn

    _steps: list[tuple[str, str]] = [
        ("numpy", "numpy"),
        ("matplotlib", "matplotlib"),
        ("skrf", "scikit-rf"),
        ("pyvisa", "pyvisa"),
        ("textual", "textual"),
        ("tina", "tina"),
    ]

    _main = None

    with Progress(
        BarColumn(bar_width=40),
        TaskProgressColumn(),
        TextColumn("[cyan]Loading {task.description}[/cyan]"),
        transient=True,
    ) as progress:
        task = progress.add_task("...", total=len(_steps))

        progress.update(task, description="numpy")
        import numpy as _np  # noqa: F401

        progress.advance(task)

        progress.update(task, description="matplotlib")
        import matplotlib as _mpl  # noqa: F401

        _mpl.use("Agg")
        import matplotlib.pyplot as _plt  # noqa: F401

        progress.advance(task)

        progress.update(task, description="scikit-rf")
        import skrf as _rf  # noqa: F401

        progress.advance(task)

        progress.update(task, description="pyvisa")
        import pyvisa as _visa  # noqa: F401

        progress.advance(task)

        progress.update(task, description="textual")
        import textual as _textual  # noqa: F401
        import textual.app  # noqa: F401
        import textual.binding  # noqa: F401
        import textual.command  # noqa: F401
        import textual.containers  # noqa: F401
        import textual.screen  # noqa: F401
        import textual.widgets  # noqa: F401

        progress.advance(task)

        progress.update(task, description="tina")
        from .main import main as _main

        progress.advance(task)

    _main()
