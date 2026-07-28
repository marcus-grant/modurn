"""Tests for the network-free Nexus helpers: parsing + the resume ledger.

The browser flow itself can't be unit-tested without Nexus, but these pieces --
which decide *what* to download and *whether to skip* -- are pure and must stay
correct so an interrupted travel session resumes instead of re-downloading.
"""

from __future__ import annotations

from pathlib import Path

from modurn.sources.nexus_parse import (
    DownloadLedger,
    extract_nexus_mods_from_html,
    parse_file_id,
)


def test_parse_file_id():
    assert parse_file_id("https://www.nexusmods.com/morrowind/mods/19510?tab=files&file_id=7702") == 7702
    assert parse_file_id("/morrowind/mods/1/?file_id=42&nmm=1") == 42
    assert parse_file_id("no file id here") is None
    assert parse_file_id(None) is None


def test_extract_nexus_mods_dedupes_and_orders():
    html = """
    <a href="https://www.nexusmods.com/morrowind/mods/19510">Morrowind Code Patch</a>
    <a href="/morrowind/mods/45096?tab=description">Patch for Purists</a>
    <a href="https://www.nexusmods.com/morrowind/mods/19510?tab=files">MCP files</a>
    <a href="https://www.nexusmods.com/skyrimspecialedition/mods/266">unrelated</a>
    """
    refs = extract_nexus_mods_from_html(html)
    slugs = [r.slug for r in refs]
    assert slugs == ["morrowind/19510", "morrowind/45096", "skyrimspecialedition/266"]


def test_ledger_resume_only_counts_files_still_on_disk(tmp_path: Path):
    ledger_path = tmp_path / ".modurn-downloads.json"
    ledger = DownloadLedger.load(ledger_path)

    assert not ledger.has("morrowind/19510", 7702)

    # Record without the file present -> not "done" (protects against a wiped cache).
    ledger.record("morrowind/19510", 7702, "mcp.7z")
    assert not ledger.has("morrowind/19510", 7702)

    # Create the file -> now it counts as done and survives a reload.
    (tmp_path / "mcp.7z").write_text("bytes")
    assert ledger.has("morrowind/19510", 7702)

    reloaded = DownloadLedger.load(ledger_path)
    assert reloaded.has("morrowind/19510", 7702)
    assert reloaded.filename_for("morrowind/19510", 7702) == "mcp.7z"
    # Distinct file id of same mod is independent.
    assert not reloaded.has("morrowind/19510", 9999)
