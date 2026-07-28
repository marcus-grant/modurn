"""Source registry.

Adding a backend = write one module in this package and add one line to
`_BUILDERS`. That is the whole extension story.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from .base import FetchedFile, ModSource, SourceError

# Lazily-built so importing the registry never imports Playwright.
_BUILDERS: dict[str, Callable[["SourceContext"], ModSource]] = {}


class SourceContext:
    """Shared config the CLI hands to source builders (auth paths, flags)."""

    def __init__(self, nexus_auth_state: Path, headless: bool = True):
        self.nexus_auth_state = nexus_auth_state
        self.headless = headless


def _build_local(_: SourceContext) -> ModSource:
    from .local import LocalSource

    return LocalSource()


def _build_nexus(ctx: SourceContext) -> ModSource:
    from .nexus import NexusSource

    return NexusSource(auth_state=ctx.nexus_auth_state, headless=ctx.headless)


_BUILDERS["local"] = _build_local
_BUILDERS["nexus"] = _build_nexus


def available_sources() -> list[str]:
    return sorted(_BUILDERS)


def get_source(kind: str, ctx: SourceContext) -> ModSource:
    try:
        return _BUILDERS[kind](ctx)
    except KeyError:
        raise SourceError(
            f"unknown source {kind!r}. Available: {', '.join(available_sources())}"
        ) from None


__all__ = [
    "FetchedFile",
    "ModSource",
    "SourceError",
    "SourceContext",
    "available_sources",
    "get_source",
]
