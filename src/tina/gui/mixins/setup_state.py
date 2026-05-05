"""Setup-state mixin compatibility shims."""

from __future__ import annotations

from ._types import GUIAppTypingMixin


class SetupStateMixin(GUIAppTypingMixin):
    """Compatibility shim for legacy setup-state helpers."""

    pass
