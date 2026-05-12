"""Unit tests for BackgroundJobsMixin compatibility shim."""

import pytest

from tina.gui.mixins._types import GUIAppTypingMixin
from tina.gui.mixins.background_jobs import BackgroundJobsMixin
from tina.gui.mixins.import_export import ImportExportMixin
from tina.gui.mixins.notes import NotesMixin
from tina.gui.mixins.setup_state import SetupStateMixin
from tina.gui.mixins.tools_tab import ToolsTabMixin
from tina.gui.mixins.worker_messages import WorkerMessagesMixin


class TestBackgroundJobsMixin:
    @pytest.mark.unit
    def test_is_subclass_of_gui_app_typing_mixin(self):
        """BackgroundJobsMixin must subclass GUIAppTypingMixin for the compat shim to work."""
        assert issubclass(BackgroundJobsMixin, GUIAppTypingMixin)
        assert issubclass(NotesMixin, GUIAppTypingMixin)
        assert issubclass(ToolsTabMixin, GUIAppTypingMixin)
        assert issubclass(ImportExportMixin, GUIAppTypingMixin)
        assert issubclass(SetupStateMixin, GUIAppTypingMixin)
        assert issubclass(WorkerMessagesMixin, GUIAppTypingMixin)
