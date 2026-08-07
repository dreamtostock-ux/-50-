from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

import yaml


_ENV = re.compile(r"\$\{([A-Z0-9_]+)(?::-([^}]*))?\}")


def _expand_env(value: Any) -> Any:
    if isinstance(value, str):
        return _ENV.sub(lambda m: os.getenv(m.group(1), m.group(2) or ""), value)
    if isinstance(value, dict):
        return {k: _expand_env(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_expand_env(v) for v in value]
    return value


def load_config(path: str | Path) -> dict[str, Any]:
    config_path = Path(path).resolve()
    with config_path.open("r", encoding="utf-8") as handle:
        config = _expand_env(yaml.safe_load(handle))
    config["_config_dir"] = str(config_path.parent)
    config["runtime"]["port"] = int(config["runtime"]["port"])
    return config


def resolve_path(config: dict[str, Any], path: str) -> Path:
    candidate = Path(path)
    return candidate if candidate.is_absolute() else Path(config["_config_dir"]) / candidate
