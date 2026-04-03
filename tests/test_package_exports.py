"""Tests for package-level exports and loader behavior."""

from __future__ import annotations

import importlib
import sys
from unittest.mock import Mock, patch

import pytest


@pytest.mark.unit
def test_gui_package_exports_names_without_eager_main_import():
    """The GUI package should advertise app entry points without importing them eagerly."""
    gui = importlib.import_module("tina.gui")

    assert "VNAApp" in gui.__all__
    assert "run_gui" in gui.__all__
    assert "main" in gui.__all__


@pytest.mark.unit
def test_gui_app_module_exports_names_without_eager_main_import():
    """The dedicated GUI app module should advertise app symbols lazily."""
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
            loader.main()

    fake_main.assert_called_once_with()


@pytest.mark.unit
def test_loader_skips_progress_bar_for_now_flag():
    """The loader should delegate directly to tina.main in CLI mode."""
    loader = importlib.import_module("tina._loader")
    fake_main = Mock()

    with patch.object(sys, "argv", ["tina", "--now"]):
        with patch("tina.main.main", fake_main):
            loader.main()

    fake_main.assert_called_once_with()


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
