"""Local filesystem source.

The simplest possible backend and, not coincidentally, the one that makes the
whole pipeline testable without a network or a browser. Point a mod at an
archive or a directory you already have and modurn treats it exactly like a
"downloaded" mod.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from ..models import Mod
from .base import FetchedFile, ModSource, SourceError


class LocalSource(ModSource):
    kind = "local"

    def fetch(self, mod: Mod, dest_dir: Path) -> list[FetchedFile]:
        assert mod.path is not None  # guaranteed by model validation
        src = mod.path
        if not src.exists():
            raise SourceError(f"mod {mod.name!r}: local path does not exist: {src}")

        # Directories are used in place (no copy) -- extraction handles dirs.
        if src.is_dir():
            return [FetchedFile(path=src, from_cache=True, meta={"local_dir": str(src)})]

        dest_dir.mkdir(parents=True, exist_ok=True)
        target = dest_dir / src.name
        if target.exists() and target.stat().st_size == src.stat().st_size:
            return [FetchedFile(path=target, from_cache=True, meta={"local_file": str(src)})]

        shutil.copy2(src, target)
        return [FetchedFile(path=target, from_cache=False, meta={"local_file": str(src)})]

    def close(self) -> None:  # pragma: no cover - nothing to release
        pass
