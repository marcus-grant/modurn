"""Read and safely rewrite openmw.cfg.

modurn only owns a *block* of the file, delimited by markers keyed on the
profile name. Everything outside the markers -- the user's hand-written
settings, other tools' lines -- is preserved byte for byte. Applying a profile
replaces just that block, so the operation is idempotent and trivially
reversible (delete the block). A `.bak` is written before the first change.

    ## >>> modurn:PROFILE (managed - do not edit inside) >>>
    data="..."
    content=Foo.esp
    ## <<< modurn:PROFILE <<<
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path


def _begin(profile: str) -> str:
    return f"## >>> modurn:{profile} (managed - do not edit inside) >>>"


def _end(profile: str) -> str:
    return f"## <<< modurn:{profile} <<<"


@dataclass
class CfgEntry:
    data_dirs: list[str]      # absolute paths for data= lines
    content: list[str]        # plugin filenames for content= lines


def _strip_managed_block(lines: list[str], profile: str) -> list[str]:
    begin, end = _begin(profile), _end(profile)
    out: list[str] = []
    skipping = False
    for line in lines:
        stripped = line.rstrip("\n")
        if stripped == begin:
            skipping = True
            continue
        if stripped == end:
            skipping = False
            continue
        if not skipping:
            out.append(line)
    return out


def render_block(profile: str, entry: CfgEntry) -> str:
    lines = [_begin(profile)]
    for data in entry.data_dirs:
        lines.append(f'data="{data}"')
    for plugin in entry.content:
        lines.append(f"content={plugin}")
    lines.append(_end(profile))
    return "\n".join(lines) + "\n"


def write_profile_block(
    cfg_path: Path,
    profile: str,
    entry: CfgEntry,
    backup: bool = True,
) -> Path:
    """Insert/replace modurn's managed block for `profile` in openmw.cfg.

    Returns the cfg path. Creates the file (and a first-run `.bak`) if needed.
    """
    cfg_path = Path(cfg_path).expanduser()
    cfg_path.parent.mkdir(parents=True, exist_ok=True)

    original = cfg_path.read_text() if cfg_path.is_file() else ""

    if backup and cfg_path.is_file():
        bak = cfg_path.with_suffix(cfg_path.suffix + ".bak")
        if not bak.exists():  # keep the pristine pre-modurn copy
            shutil.copy2(cfg_path, bak)

    kept = _strip_managed_block(original.splitlines(keepends=True), profile)
    body = "".join(kept)
    if body and not body.endswith("\n"):
        body += "\n"

    new_text = body + render_block(profile, entry)
    cfg_path.write_text(new_text)
    return cfg_path


def remove_profile_block(cfg_path: Path, profile: str) -> bool:
    """Delete a profile's managed block. Returns True if anything changed."""
    cfg_path = Path(cfg_path).expanduser()
    if not cfg_path.is_file():
        return False
    original = cfg_path.read_text()
    kept = "".join(_strip_managed_block(original.splitlines(keepends=True), profile))
    if kept == original:
        return False
    cfg_path.write_text(kept)
    return True
