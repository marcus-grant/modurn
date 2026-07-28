"""Direct-URL source: download an archive from any plain HTTP(S) link.

The easy, fully-automatic half of a modding-openmw.com list -- everything
hosted on GitHub/GitLab/ModDB/etc. that needs no login and isn't behind
Cloudflare's bot wall. No browser required, so this runs headless and is
resumable-by-skip (an already-downloaded file is reused).

stdlib only (urllib) to keep the dependency surface small.
"""

from __future__ import annotations

import shutil
import urllib.parse
import urllib.request
from pathlib import Path

from ..models import Mod
from .base import FetchedFile, ModSource, SourceError

_USER_AGENT = "modurn/0.1 (+https://github.com/marcus-grant/modurn)"


def filename_from_response(content_disposition: str | None, url: str) -> str:
    """Pick a filename: prefer Content-Disposition, else the URL basename."""
    if content_disposition:
        # e.g. attachment; filename="Mod-1.2.zip"  (also handles filename*=)
        for part in content_disposition.split(";"):
            part = part.strip()
            for key in ("filename*=", "filename="):
                if part.lower().startswith(key):
                    value = part[len(key):].strip().strip('"')
                    # RFC 5987: filename*=UTF-8''Mod%20Name.zip
                    if "''" in value:
                        value = value.split("''", 1)[1]
                    value = urllib.parse.unquote(value)
                    if value:
                        return Path(value).name
    # Fall back to the basename of the URL *path* (ignoring host and query).
    tail = Path(urllib.parse.urlparse(url).path).name
    return tail or "download.bin"


class UrlSource(ModSource):
    kind = "url"

    def fetch(self, mod: Mod, dest_dir: Path) -> list[FetchedFile]:
        assert mod.url is not None  # guaranteed by model validation
        dest_dir.mkdir(parents=True, exist_ok=True)
        req = urllib.request.Request(mod.url, headers={"User-Agent": _USER_AGENT})
        try:
            with urllib.request.urlopen(req) as resp:  # noqa: S310 - user-provided URL
                filename = filename_from_response(
                    resp.headers.get("Content-Disposition"), resp.geturl()
                )
                target = dest_dir / filename
                if target.exists() and target.stat().st_size > 0:
                    return [FetchedFile(path=target, from_cache=True, meta={"url": mod.url})]
                part = target.with_name(target.name + ".part")
                with open(part, "wb") as fh:
                    shutil.copyfileobj(resp, fh)
                part.replace(target)
        except OSError as exc:
            raise SourceError(f"mod {mod.name!r}: failed to download {mod.url}: {exc}") from exc
        return [FetchedFile(path=target, from_cache=False, meta={"url": mod.url})]

    def close(self) -> None:  # pragma: no cover - nothing to release
        pass
