"""Pydantic models that define the user-facing YAML schema.

These models *are* the contract with the user. Keeping validation here (with
pydantic's readable error messages) is what makes the YAML "user friendly":
a typo'd field or a missing path fails loudly with a pointer to the problem
rather than blowing up three layers deep during a download.

Nothing in here knows about Nexus, browsers, or archives on purpose. A mod
entry just describes *what* the user wants; the sources layer decides *how*
to get it.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


def _expand(value: object) -> object:
    """Expand ``~`` and env-style paths so users can write natural paths."""
    if value is None:
        return None
    return Path(str(value)).expanduser()


class GameConfig(BaseModel):
    """Where OpenMW lives and where modurn is allowed to write."""

    model_config = ConfigDict(extra="forbid")

    # Path to the openmw.cfg modurn should manage (its data=/content= lines).
    config: Path
    # Directory modurn owns for extracted mods, one subdir per mod.
    mods_dir: Path

    @field_validator("config", "mods_dir", mode="before")
    @classmethod
    def _expand_paths(cls, v: object) -> object:
        return _expand(v)


class Mod(BaseModel):
    """A single mod the user wants installed.

    ``source`` selects which backend resolves the bytes. The remaining fields
    are a loose superset across backends; each source reads only the fields it
    understands and validation below keeps the common mistakes honest.
    """

    model_config = ConfigDict(extra="forbid")

    name: str
    source: str = "nexus"
    enabled: bool = True

    # --- nexus source fields ---------------------------------------------
    # "morrowind/19510" -> game domain + mod id on nexusmods.com
    nexus: Optional[str] = None
    # Explicit Nexus *file* ids. Omit to let the source pick the main file.
    files: list[int] = Field(default_factory=list)

    # --- local source fields ---------------------------------------------
    # A pre-downloaded archive or an already-extracted directory.
    path: Optional[Path] = None

    # --- url source fields (direct downloads: GitHub/GitLab/ModDB/etc.) ---
    # A direct download link to an archive. No login, no Cloudflare -- the
    # easy, fully-automatic path for the non-Nexus mods in a list.
    url: Optional[str] = None

    # --- install hints (backend-agnostic) --------------------------------
    # Explicit plugin load order for this mod. If empty, modurn auto-detects
    # .esp/.esm/.omwaddon/.omwgame files and adds them in discovered order.
    content: list[str] = Field(default_factory=list)
    # Extra data= subdirectories inside the archive, if it is not flat.
    data_subdir: Optional[str] = None

    @field_validator("path", mode="before")
    @classmethod
    def _expand_path(cls, v: object) -> object:
        return _expand(v)

    @field_validator("nexus")
    @classmethod
    def _check_nexus_shape(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        if v.count("/") != 1 or v.startswith("/") or v.endswith("/"):
            raise ValueError(
                f"nexus must look like 'game/modid' (e.g. 'morrowind/19510'), got {v!r}"
            )
        return v

    @model_validator(mode="after")
    def _require_source_fields(self) -> "Mod":
        if self.source == "nexus" and not self.nexus:
            raise ValueError(f"mod {self.name!r}: source 'nexus' requires a 'nexus: game/modid' field")
        if self.source == "local" and not self.path:
            raise ValueError(f"mod {self.name!r}: source 'local' requires a 'path' field")
        if self.source == "url" and not self.url:
            raise ValueError(f"mod {self.name!r}: source 'url' requires a 'url' field")
        return self

    @property
    def nexus_game(self) -> Optional[str]:
        return self.nexus.split("/", 1)[0] if self.nexus else None

    @property
    def nexus_mod_id(self) -> Optional[int]:
        return int(self.nexus.split("/", 1)[1]) if self.nexus else None


class ModList(BaseModel):
    """The whole document a user hands to modurn."""

    model_config = ConfigDict(extra="forbid")

    game: GameConfig
    # Name of the profile this list represents (used for the managed cfg block
    # and for save association). Defaults to "default".
    profile: str = "default"
    # Optional save this profile is tied to, for later profile<->save workflows.
    save: Optional[Path] = None
    mods: list[Mod]

    @field_validator("save", mode="before")
    @classmethod
    def _expand_save(cls, v: object) -> object:
        return _expand(v)

    @property
    def enabled_mods(self) -> list[Mod]:
        return [m for m in self.mods if m.enabled]
