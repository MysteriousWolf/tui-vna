"""Unit tests for BackgroundJobsMixin compatibility shim."""

import pytest

from tina.gui.mixins._types import GUIAppTypingMixin
from tina.gui.mixins.background_jobs import BackgroundJobsMixin
from tina.gui.mixins.import_export import ImportExportMixin
from tina.gui.mixins.notes import NotesMixin
from tina.gui.mixins.results_plot import ResultsPlotMixin
from tina.gui.mixins.setup_state import SetupStateMixin
from tina.gui.mixins.tools_tab import ToolsTabMixin
from tina.gui.mixins.worker_messages import WorkerMessagesMixin


class TestBackgroundJobsMixin:
    @pytest.mark.unit
    @pytest.mark.parametrize(
        "mixin",
        [
            BackgroundJobsMixin,
            NotesMixin,
            ToolsTabMixin,
            ImportExportMixin,
            SetupStateMixin,
            WorkerMessagesMixin,
            ResultsPlotMixin,
        ],
    )
    def test_is_subclass_of_gui_app_typing_mixin(self, mixin):
        """Each mixin must subclass GUIAppTypingMixin for the compat shim to work."""
        assert issubclass(mixin, GUIAppTypingMixin)
