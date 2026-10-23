from __future__ import annotations

import os
import sys
from pathlib import Path


def data_dir() -> Path:
    override = os.environ.get("TAMIGO_INTEL_HOME")
    if override:
        path = Path(override)
    elif sys.platform == "darwin":
        path = Path.home() / "Library" / "Application Support" / "TamigoIntel"
    else:
        path = Path.home() / ".local" / "share" / "tamigo-intel"
    path.mkdir(parents=True, exist_ok=True)
    return path


def db_path() -> Path:
    return data_dir() / "tamigo.sqlite"


def config_path() -> Path:
    return data_dir() / "config.json"


def backup_dir() -> Path:
    path = data_dir() / "backups"
    path.mkdir(parents=True, exist_ok=True)
    return path
