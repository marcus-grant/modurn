"""The ModSource seam.

This is the one abstraction the whole project is bet on. Every backend --
Nexus-via-browser today, Nexus-API or a homelab server or a MOMW-list
importer tomorrow -- implements `ModSource.fetch`: given a mod entry, put the
raw archive(s)/dir(s) somewhere on disk and return where.

Everything downstream (extraction, cfg writing, profiles, the lockfile) is
written against `FetchedFile` and never against a specific backend. Adding a
backend later should mean writing one new file in this package and one line
in the registry -- nothing else in the codebase should need to change.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol, runtime_checkable

from ..models import Mod


@dataclass
class FetchedFile:
    """One archive or directory a source produced for a mod."""

    path: Path
    # True when the source reused a previously downloaded file instead of
    # fetching again. Lets the CLI report cache hits honestly.
    from_cache: bool = False
    # Free-form provenance for the lockfile (e.g. nexus file id, url).
    meta: dict = field(default_factory=dict)


class SourceError(Exception):
    """A backend failed to resolve or fetch a mod."""


@runtime_checkable
class ModSource(Protocol):
    """Resolve a mod entry into files on disk.

    Implementations must be cheap to construct; expensive/stateful setup
    (launching a browser, opening a session) should be lazy or handled with a
    context manager so `plan` can run without ever touching the network.
    """

    kind: str

    def fetch(self, mod: Mod, dest_dir: Path) -> list[FetchedFile]:
        """Download/locate the files for `mod`, placing them under `dest_dir`.

        Returns one `FetchedFile` per archive/dir. Should be idempotent: if the
        expected file already exists in `dest_dir`, reuse it and mark it cached.
        """
        ...

    def close(self) -> None:
        """Release any held resources. Default no-op for simple sources."""
