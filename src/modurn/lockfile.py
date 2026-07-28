"""The modurn lockfile: a record of what `apply` actually did.

Written next to the modlist as `modurn.lock` (JSON). It makes `apply`
idempotent and reversible: we know exactly which mods, files, data dirs and
plugins were installed for a profile, so a future `remove`/`sync` can undo or
diff without re-scraping anything. Intentionally plain JSON -- easy to inspect,
diff in git, and evolve.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

LOCK_VERSION = 1


@dataclass
class LockedMod:
    name: str
    source: str
    data_dir: str
    plugins: list[str] = field(default_factory=list)
    files: list[str] = field(default_factory=list)          # fetched filenames
    nexus_file_ids: list[int] = field(default_factory=list)


@dataclass
class Lock:
    profile: str
    version: int = LOCK_VERSION
    save: str | None = None
    mods: list[LockedMod] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "version": self.version,
            "profile": self.profile,
            "save": self.save,
            "mods": [asdict(m) for m in self.mods],
        }


def lock_path_for(modlist_path: str | Path) -> Path:
    return Path(modlist_path).expanduser().with_name("modurn.lock")


def write_lock(lock: Lock, path: str | Path) -> Path:
    p = Path(path).expanduser()
    p.write_text(json.dumps(lock.to_dict(), indent=2) + "\n")
    return p


def read_lock(path: str | Path) -> Lock | None:
    p = Path(path).expanduser()
    if not p.is_file():
        return None
    data = json.loads(p.read_text())
    mods = [LockedMod(**m) for m in data.get("mods", [])]
    return Lock(
        profile=data["profile"],
        version=data.get("version", LOCK_VERSION),
        save=data.get("save"),
        mods=mods,
    )
