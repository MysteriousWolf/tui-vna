"""Tests for package-level exports and loader behavior."""

from __future__ import annotations

import importlib
import sys
from contextlib import contextmanager
from types import ModuleType
from unittest.mock import Mock, patch

import pytest


@contextmanager
def _evict_module(*names: str):
    """Temporarily remove named modules from sys.modules and restore them afterward.

    Also restores the submodule attribute on parent packages so that
    ``sys.modules["tina"].gui`` stays consistent with ``sys.modules["tina.gui"]``.
    """
    saved = {n: sys.modules.pop(n, None) for n in names}
    # Record the current submodule attribute on each parent package.
    parent_state: list[tuple[object, str, object]] = []
    for name in names:
        dot = name.rfind(".")
        if dot != -1:
            parent_name, attr = name[:dot], name[dot + 1 :]
            parent = sys.modules.get(parent_name)
            if parent is not None:
                parent_state.append((parent, attr, getattr(parent, attr, None)))
    try:
        yield
    finally:
        for name, module in saved.items():
            sys.modules.pop(name, None)
            if module is not None:
                sys.modules[name] = module
        # Restore parent submodule attributes so later imports stay consistent.
        for parent, attr, original_val in parent_state:
            if original_val is not None:
                setattr(parent, attr, original_val)
            else:
                try:
                    delattr(parent, attr)
                except AttributeError:
                    pass


@pytest.mark.unit
def test_version_resolved_from_package_metadata():
    """__version__ should reflect the installed package version when metadata is available."""
    with _evict_module("tina"):
        with patch("importlib.metadata.version", return_value="1.2.3"):
            tina = importlib.import_module("tina")
    assert tina.__version__ == "1.2.3"


@pytest.mark.unit
def test_version_falls_back_to_pep440_dev_when_package_not_found():
    """__version__ should fall back to '0.0.0.dev0' when the package is not installed."""
    from importlib.metadata import PackageNotFoundError

    with _evict_module("tina"):
        with patch(
            "importlib.metadata.version", side_effect=PackageNotFoundError("tui-vna")
        ):
            tina = importlib.import_module("tina")
    assert tina.__version__ == "0.0.0.dev0"


@pytest.mark.unit
def test_gui_package_exports_names_without_eager_main_import():
    """The GUI package should advertise app entry points without importing them eagerly."""
    with _evict_module("tina.gui"):
        gui = importlib.import_module("tina.gui")

        assert "VNAApp" in gui.__all__
        assert "run_gui" in gui.__all__
        assert "main" in gui.__all__
        assert "VNAApp" not in gui.__dict__
        assert "__all__" in gui.__dir__()


@pytest.mark.unit
def test_gui_package_lazy_exports_resolve_through_getattr():
    """The GUI package should only resolve exports when accessed."""
    with _evict_module("tina.gui"):
        gui = importlib.import_module("tina.gui")
        fake_main = ModuleType("tina.main")
        setattr(fake_main, "VNAApp", object())
        setattr(fake_main, "run_gui", object())
        setattr(fake_main, "main", object())

        with patch.dict(sys.modules, {"tina.main": fake_main}):
            assert gui.VNAApp is fake_main.VNAApp
            assert gui.run_gui is fake_main.run_gui
            assert gui.main is fake_main.main


@pytest.mark.unit
def test_gui_app_module_exports_names_without_eager_main_import():
    """The dedicated GUI app module should advertise app symbols lazily."""
    with _evict_module("tina.gui.app"):
        gui_app = importlib.import_module("tina.gui.app")
        assert "VNAApp" in gui_app.__all__
        assert "run_gui" in gui_app.__all__
        assert "main" in gui_app.__all__


@pytest.mark.unit
def test_loader_skips_progress_bar_for_help_flag():
    """The loader should delegate directly to tina.main for help output."""
    loader = importlib.import_module("tina._loader")
    fake_main = Mock()

    with patch.object(sys, "argv", ["tina", "--help"]):
        with patch("tina.main.main", fake_main):
            with patch("rich.progress.Progress") as mock_progress:
                loader.main()

    fake_main.assert_called_once_with()
    mock_progress.assert_not_called()


@pytest.mark.unit
def test_loader_skips_progress_bar_for_now_flag():
    """The loader should delegate directly to tina.main in CLI mode."""
    loader = importlib.import_module("tina._loader")
    fake_main = Mock()

    with patch.object(sys, "argv", ["tina", "--now"]):
        with patch("tina.main.main", fake_main):
            with patch("rich.progress.Progress") as mock_progress:
                loader.main()

    fake_main.assert_called_once_with()
    mock_progress.assert_not_called()


@pytest.mark.unit
def test_loader_uses_progress_bar_and_executes_all_steps():
    """The loader should run all preload steps before launching the app."""
    loader = importlib.import_module("tina._loader")
    fake_main = Mock()
    executed_steps: list[str] = []

    class FakeProgress:
        """Minimal progress stub that records task updates."""

        def __init__(self, *args, **kwargs):
            self.args = args
            self.kwargs = kwargs
            self.descriptions: list[str] = []
            self.advanced = 0

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def add_task(self, description: str, total: int):
            self.initial_description = description
            self.total = total
            return "task-id"

        def update(self, task, description: str):
            assert task == "task-id"
            self.descriptions.append(description)

        def advance(self, task):
            assert task == "task-id"
            self.advanced += 1

    def make_step(name: str):
        def _step():
            executed_steps.append(name)

        return _step

    with patch.object(sys, "argv", ["tina"]):
        with patch.object(
            loader,
            "_IMPORT_STEPS",
            (
                ("numpy", make_step("numpy")),
                ("matplotlib", make_step("matplotlib")),
                ("scikit-rf", make_step("scikit-rf")),
            ),
        ):
            with patch.object(loader, "_import_tina_main", return_value=fake_main):
                with patch("rich.progress.Progress", FakeProgress):
                    loader.main()

    assert executed_steps == ["numpy", "matplotlib", "scikit-rf"]
    assert fake_main.call_count == 1
