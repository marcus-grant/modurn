"""End-to-end-ish tests for the network-free half of the pipeline.

These cover the parts a user relies on every run and that must never silently
break: YAML validation, local install + plugin/data-dir detection, and the
idempotent, reversible openmw.cfg managed block.
"""

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from modurn.install import install_mod
from modurn.modlist import ModListError, load_modlist
from modurn.openmw_cfg import (
    CfgEntry,
    remove_profile_block,
    write_profile_block,
)
from modurn.sources.local import LocalSource
from modurn.models import Mod


def _make_zip(path: Path, files: dict[str, str]) -> Path:
    with zipfile.ZipFile(path, "w") as zf:
        for name, content in files.items():
            zf.writestr(name, content)
    return path


def test_local_install_flat_archive(tmp_path: Path):
    archive = _make_zip(
        tmp_path / "mod.zip",
        {"Foo.esp": "x", "Textures/tex.dds": "y"},
    )
    mod = Mod(name="Foo Mod", source="local", path=archive)
    fetched = LocalSource().fetch(mod, tmp_path / "dl")
    installed = install_mod(
        "Foo Mod", [f.path for f in fetched], tmp_path / "mods"
    )
    assert installed.plugins == ["Foo.esp"]
    assert (installed.data_dir / "Foo.esp").is_file()


def test_local_install_unwraps_single_top_folder(tmp_path: Path):
    archive = _make_zip(
        tmp_path / "mod.zip",
        {"WrapperDir/Bar.omwaddon": "x", "WrapperDir/Meshes/m.nif": "y"},
    )
    installed = install_mod(
        "Bar", [archive], tmp_path / "mods"
    )
    # data_dir should be unwrapped to the folder that actually holds the plugin.
    assert installed.plugins == ["Bar.omwaddon"]
    assert installed.data_dir.name == "WrapperDir"


def test_cfg_block_is_idempotent_and_reversible(tmp_path: Path):
    cfg = tmp_path / "openmw.cfg"
    cfg.write_text('content=Morrowind.esm\ndata="/usr/share/games/morrowind"\n')

    entry = CfgEntry(data_dirs=["/mods/foo"], content=["Foo.esp"])
    write_profile_block(cfg, "demo", entry)
    write_profile_block(cfg, "demo", entry)  # apply twice

    text = cfg.read_text()
    # User's original lines preserved.
    assert "content=Morrowind.esm" in text
    # Our block appears exactly once despite two applies.
    assert text.count("## >>> modurn:demo") == 1
    assert text.count("content=Foo.esp") == 1
    # Backup captured the pristine original.
    assert (tmp_path / "openmw.cfg.bak").read_text().count("modurn") == 0

    changed = remove_profile_block(cfg, "demo")
    assert changed
    assert "modurn:demo" not in cfg.read_text()
    assert "content=Morrowind.esm" in cfg.read_text()


def test_two_profiles_coexist(tmp_path: Path):
    cfg = tmp_path / "openmw.cfg"
    write_profile_block(cfg, "a", CfgEntry(["/a"], ["A.esp"]))
    write_profile_block(cfg, "b", CfgEntry(["/b"], ["B.esp"]))
    text = cfg.read_text()
    assert "modurn:a" in text and "modurn:b" in text
    # Rewriting a leaves b intact.
    write_profile_block(cfg, "a", CfgEntry(["/a2"], ["A2.esp"]))
    text = cfg.read_text()
    assert "content=A2.esp" in text
    assert "content=B.esp" in text
    assert text.count("content=A.esp") == 0


def test_modlist_validation_errors(tmp_path: Path):
    bad = tmp_path / "bad.yaml"
    bad.write_text(
        "game:\n"
        "  config: ~/x/openmw.cfg\n"
        "  mods_dir: ~/x/mods\n"
        "mods:\n"
        "  - name: NoSource\n"          # nexus source but missing `nexus:`
    )
    with pytest.raises(ModListError):
        load_modlist(bad)


def test_modlist_roundtrip(tmp_path: Path):
    good = tmp_path / "good.yaml"
    good.write_text(
        "game:\n"
        "  config: ~/x/openmw.cfg\n"
        "  mods_dir: ~/x/mods\n"
        "profile: demo\n"
        "mods:\n"
        "  - name: MCP\n"
        "    nexus: morrowind/19510\n"
        "    files: [7702]\n"
        "  - name: Local\n"
        "    source: local\n"
        "    path: ~/x/mod.zip\n"
    )
    ml = load_modlist(good)
    assert ml.profile == "demo"
    assert ml.mods[0].nexus_mod_id == 19510
    assert ml.enabled_mods[0].name == "MCP"
