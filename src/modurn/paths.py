"""Default filesystem locations for modurn's own state.

Kept in one place so a future move to a proper config system is a single-file
change. Honors XDG on Linux; falls back sanely elsewhere.
"""

from __future__ import annotations

import os
from pathlib import Path


def state_dir() -> Path:
    """Where modurn stores its session/state (auth, profiles registry)."""
    override = os.environ.get("MODURN_STATE_DIR")
    if override:
        return Path(override).expanduser()
    base = os.environ.get("XDG_DATA_HOME") or (Path.home() / ".local" / "share")
    return Path(base).expanduser() / "modurn"


def nexus_auth_state() -> Path:
    return state_dir() / "nexus-auth.json"


def profiles_file() -> Path:
    return state_dir() / "profiles.json"
