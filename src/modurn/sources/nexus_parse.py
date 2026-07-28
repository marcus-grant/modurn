"""Pure parsing/ledger helpers for the Nexus source.

Deliberately separated from the Playwright code so this logic is unit-testable
without a browser: file-id extraction, mod-link enumeration (for importing a
modding-openmw.com list), and the resume ledger that lets an interrupted
download session pick up where it left off -- the whole point on flaky travel
bandwidth.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

_FILE_ID_RE = re.compile(r"file_id=(\d+)")
# Matches links to a Nexus mod page, absolute or relative: /<game>/mods/<id>
_MOD_LINK_RE = re.compile(r"(?:nexusmods\.com)?/(?P<game>[a-z0-9]+)/mods/(?P<id>\d+)")


@dataclass(frozen=True)
class NexusModRef:
    game: str
    mod_id: int

    @property
    def slug(self) -> str:
        return f"{self.game}/{self.mod_id}"


def parse_file_id(href_or_url: str | None) -> int | None:
    """Pull a Nexus file_id out of any href/url that carries one."""
    if not href_or_url:
        return None
    m = _FILE_ID_RE.search(href_or_url)
    return int(m.group(1)) if m else None


def extract_nexus_mods_from_html(html: str) -> list[NexusModRef]:
    """Enumerate distinct Nexus mod links in document order.

    Used to turn a modding-openmw.com list page (loaded in the user's
    already-authenticated browser, which is not Cloudflare-blocked like our
    server-side fetches are) into a modurn modlist.
    """
    seen: set[tuple[str, int]] = set()
    out: list[NexusModRef] = []
    for m in _MOD_LINK_RE.finditer(html):
        key = (m.group("game"), int(m.group("id")))
        if key in seen:
            continue
        seen.add(key)
        out.append(NexusModRef(game=key[0], mod_id=key[1]))
    return out


class DownloadLedger:
    """Records which (mod, file_id) pairs have already been downloaded.

    Persisted as JSON alongside the downloads so a re-run skips finished files
    instead of re-fetching. Pure/deterministic: no browser needed to test it.
    """

    def __init__(self, path: Path, entries: dict[str, str] | None = None):
        self.path = Path(path)
        # key "game/modid#fileid" -> saved filename
        self._entries: dict[str, str] = dict(entries or {})

    @staticmethod
    def _key(mod_slug: str, file_id: int) -> str:
        return f"{mod_slug}#{file_id}"

    @classmethod
    def load(cls, path: Path) -> "DownloadLedger":
        path = Path(path)
        if path.is_file():
            return cls(path, json.loads(path.read_text()))
        return cls(path, {})

    def has(self, mod_slug: str, file_id: int) -> bool:
        key = self._key(mod_slug, file_id)
        filename = self._entries.get(key)
        if filename is None:
            return False
        # Only count it done if the file is actually still on disk.
        return (self.path.parent / filename).is_file()

    def record(self, mod_slug: str, file_id: int, filename: str) -> None:
        self._entries[self._key(mod_slug, file_id)] = filename
        self.save()

    def filename_for(self, mod_slug: str, file_id: int) -> str | None:
        return self._entries.get(self._key(mod_slug, file_id))

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self._entries, indent=2, sort_keys=True) + "\n")
