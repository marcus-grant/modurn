"""Profile <-> save associations.

A thin registry, separate from any single modlist, that remembers which save a
profile is tied to and where that profile's modlist/lock live. This is the
seed of the future "switch profile, switch save" workflow (roadmap M2); for
now it just records the links so the data is captured from day one.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional

from .paths import profiles_file


@dataclass
class ProfileRecord:
    name: str
    modlist: Optional[str] = None   # path to the modlist yaml
    lock: Optional[str] = None      # path to modurn.lock
    save: Optional[str] = None      # path to the associated .omwsave


def _load(path: Path) -> dict[str, ProfileRecord]:
    if not path.is_file():
        return {}
    data = json.loads(path.read_text())
    return {name: ProfileRecord(**rec) for name, rec in data.items()}


def _save(records: dict[str, ProfileRecord], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({n: asdict(r) for n, r in records.items()}, indent=2) + "\n")


def all_profiles(path: Optional[Path] = None) -> dict[str, ProfileRecord]:
    return _load(path or profiles_file())


def upsert_profile(record: ProfileRecord, path: Optional[Path] = None) -> None:
    path = path or profiles_file()
    records = _load(path)
    existing = records.get(record.name)
    if existing:
        # Merge: only overwrite fields that were provided.
        for f in ("modlist", "lock", "save"):
            val = getattr(record, f)
            if val is not None:
                setattr(existing, f, val)
        records[record.name] = existing
    else:
        records[record.name] = record
    _save(records, path)


def get_profile(name: str, path: Optional[Path] = None) -> Optional[ProfileRecord]:
    return _load(path or profiles_file()).get(name)
