"""Load and validate a modlist YAML file into a `ModList`."""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import ValidationError

from .models import ModList


class ModListError(Exception):
    """Raised when a modlist file cannot be read or fails validation."""


def load_modlist(path: str | Path) -> ModList:
    p = Path(path).expanduser()
    if not p.is_file():
        raise ModListError(f"modlist not found: {p}")

    try:
        raw = yaml.safe_load(p.read_text())
    except yaml.YAMLError as exc:  # pragma: no cover - message passthrough
        raise ModListError(f"{p}: invalid YAML: {exc}") from exc

    if not isinstance(raw, dict):
        raise ModListError(f"{p}: expected a top-level mapping, got {type(raw).__name__}")

    try:
        return ModList.model_validate(raw)
    except ValidationError as exc:
        # pydantic's rendering is already good; just prefix with the file.
        raise ModListError(f"{p}: {exc}") from exc
