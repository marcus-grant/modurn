"""Turn fetched archives into installed mods on disk.

Responsibilities kept deliberately small and backend-agnostic:
  * unpack an archive (or use a directory in place) into the mods dir,
  * find the plugin files (.esp/.esm/.omwaddon/.omwgame) so the cfg writer can
    add `content=` lines,
  * find the directory that should become a `data=` entry.

OpenMW's data layout is flat: a `data=` path should be a folder containing the
game's top-level asset dirs (Meshes/, Textures/, ...) and/or plugin files.
Many Nexus archives wrap everything in a single top-level folder; we unwrap
that common case so the resulting `data=` path is correct.
"""

from __future__ import annotations

import zipfile
from dataclasses import dataclass, field
from pathlib import Path

PLUGIN_SUFFIXES = {".esp", ".esm", ".omwaddon", ".omwgame"}
# Top-level dirs that mark a folder as an OpenMW data directory.
_DATA_MARKER_DIRS = {
    "meshes", "textures", "icons", "sound", "music", "bookart", "fonts",
    "splash", "video", "distantland", "mwscript", "shaders",
}


class InstallError(Exception):
    pass


@dataclass
class InstalledMod:
    name: str
    data_dir: Path            # the path that becomes a `data=` line
    plugins: list[str] = field(default_factory=list)  # filenames, order preserved
    source_files: list[str] = field(default_factory=list)


def _extract_archive(archive: Path, dest: Path) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    suffix = archive.suffix.lower()

    if suffix == ".zip":
        with zipfile.ZipFile(archive) as zf:
            zf.extractall(dest)
        return

    if suffix == ".7z":
        try:
            import py7zr  # noqa: WPS433
        except ImportError as exc:  # pragma: no cover
            raise InstallError("py7zr is required to extract .7z archives") from exc
        with py7zr.SevenZipFile(archive, mode="r") as zf:
            zf.extractall(dest)
        return

    if suffix == ".rar":
        try:
            import rarfile  # noqa: WPS433
        except ImportError as exc:
            raise InstallError(
                "extracting .rar needs the optional 'rar' extra: pip install 'modurn[rar]' "
                "(and the system `unrar` binary)"
            ) from exc
        with rarfile.RarFile(archive) as rf:  # pragma: no cover - needs unrar
            rf.extractall(dest)
        return

    raise InstallError(f"unsupported archive type: {archive.name}")


def _looks_like_data_dir(path: Path) -> bool:
    for child in path.iterdir():
        if child.is_dir() and child.name.lower() in _DATA_MARKER_DIRS:
            return True
        if child.is_file() and child.suffix.lower() in PLUGIN_SUFFIXES:
            return True
    return False


def _resolve_data_dir(extracted_root: Path, data_subdir: str | None) -> Path:
    """Find the folder that should become the `data=` entry."""
    if data_subdir:
        candidate = extracted_root / data_subdir
        if not candidate.is_dir():
            raise InstallError(f"data_subdir {data_subdir!r} not found under {extracted_root}")
        return candidate

    if _looks_like_data_dir(extracted_root):
        return extracted_root

    # Common case: a single wrapper folder. Unwrap it (recursively, shallowly).
    entries = [p for p in extracted_root.iterdir() if not p.name.startswith(".")]
    dirs = [p for p in entries if p.is_dir()]
    if len(entries) == 1 and dirs:
        return _resolve_data_dir(dirs[0], None)

    # Fall back to the extracted root; better an explicit-but-wrong path the
    # user can override with data_subdir than a silent guess deeper in.
    return extracted_root


def _find_plugins(data_dir: Path) -> list[str]:
    plugins = [
        p.name
        for p in sorted(data_dir.iterdir())
        if p.is_file() and p.suffix.lower() in PLUGIN_SUFFIXES
    ]
    return plugins


def install_mod(
    name: str,
    fetched_paths: list[Path],
    mods_dir: Path,
    data_subdir: str | None = None,
    content_override: list[str] | None = None,
) -> InstalledMod:
    """Install one mod from its fetched archive(s)/dir(s)."""
    mods_dir = Path(mods_dir).expanduser()
    target = mods_dir / _safe_dirname(name)

    if not fetched_paths:
        raise InstallError(f"mod {name!r}: nothing was fetched to install")

    # Fresh install each time keeps `apply` deterministic and idempotent.
    if target.exists():
        _rmtree(target)
    target.mkdir(parents=True, exist_ok=True)

    source_files: list[str] = []
    for fetched in fetched_paths:
        source_files.append(fetched.name)
        if fetched.is_dir():
            _copytree(fetched, target)
        else:
            _extract_archive(fetched, target)

    data_dir = _resolve_data_dir(target, data_subdir)
    plugins = content_override if content_override else _find_plugins(data_dir)

    return InstalledMod(
        name=name,
        data_dir=data_dir,
        plugins=plugins,
        source_files=source_files,
    )


# -- small fs helpers (kept local; not worth a utils module yet) -----------

def _safe_dirname(name: str) -> str:
    return "".join(c if c.isalnum() or c in "-_. " else "_" for c in name).strip()


def _rmtree(path: Path) -> None:
    import shutil

    shutil.rmtree(path)


def _copytree(src: Path, dst: Path) -> None:
    import shutil

    shutil.copytree(src, dst, dirs_exist_ok=True)
