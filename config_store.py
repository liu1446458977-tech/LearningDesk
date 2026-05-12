"""JSON settings: API base URL, key, model."""

from __future__ import annotations

import json
from pathlib import Path

from db import app_data_dir


def settings_path() -> Path:
    return app_data_dir() / "settings.json"


DEFAULT_MODEL = "gpt-4o-mini"


def load_settings() -> dict:
    p = settings_path()
    if not p.exists():
        return {
            "api_base_url": "",
            "api_key": "",
            "model": DEFAULT_MODEL,
            "window_geometry": "520x720+80+80",
            "always_on_top": True,
        }
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {
            "api_base_url": "",
            "api_key": "",
            "model": DEFAULT_MODEL,
            "window_geometry": "520x720+80+80",
            "always_on_top": True,
        }
    data.setdefault("api_base_url", "")
    data.setdefault("api_key", "")
    data.setdefault("model", DEFAULT_MODEL)
    data.setdefault("window_geometry", "520x720+80+80")
    data.setdefault("always_on_top", True)
    return data


def save_settings(data: dict) -> None:
    p = settings_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
