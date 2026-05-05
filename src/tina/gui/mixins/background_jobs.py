"""Background job and export mixin compatibility shims."""

from __future__ import annotations

from ._types import GUIAppTypingMixin


class BackgroundJobsMixin(GUIAppTypingMixin):
    """Compatibility shim for legacy background-job helpers."""

    pass
