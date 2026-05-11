"""Unit tests for BackgroundJobsMixin compatibility shim."""

import pytest

from tina.gui.mixins.background_jobs import BackgroundJobsMixin
from tina.gui.mixins._types import GUIAppTypingMixin


class TestBackgroundJobsMixin:
    @pytest.mark.unit
    def test_is_subclass_of_gui_app_typing_mixin(self):
        """BackgroundJobsMixin must subclass GUIAppTypingMixin for the compat shim to work."""
        assert issubclass(BackgroundJobsMixin, GUIAppTypingMixin)
