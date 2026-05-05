"""Worker-message mixin compatibility shims."""

from __future__ import annotations

from ._types import GUIAppTypingMixin


class WorkerMessagesMixin(GUIAppTypingMixin):
    """Compatibility shim for legacy worker-message helpers."""

    pass
