"""Configuration manager for Inthezon MCP — profiles, accounts, defaults."""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

CONFIG_DIR = Path.home() / ".inthezon"
CONFIG_FILE = CONFIG_DIR / "config.json"

DEFAULT_DEFAULTS = {
    "date_range_days": 30,
    "limit": 100,
    "group_by": "day",
}


def _detect_database_url() -> str:
    """Try to read DATABASE_URL from environment or backend/.env."""
    url = os.getenv("MCP_DATABASE_URL") or os.getenv("DATABASE_URL")
    if url:
        return url
    # Try backend/.env
    env_path = Path(__file__).resolve().parent.parent / "backend" / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            key = key.strip()
            val = val.strip().strip('"').strip("'")
            if key == "DATABASE_URL":
                return val
    return "postgresql+asyncpg://localhost:5432/inthezon"


def _make_default_config() -> dict:
    return {
        "active_profile": "local",
        "profiles": {
            "local": {
                "database_url": _detect_database_url(),
                "selected_account_ids": [],
                "defaults": dict(DEFAULT_DEFAULTS),
            }
        },
    }


def load_config() -> dict:
    """Load config from ~/.inthezon/config.json, creating defaults if missing."""
    if CONFIG_FILE.exists():
        try:
            return json.loads(CONFIG_FILE.read_text())
        except (json.JSONDecodeError, OSError):
            pass
    config = _make_default_config()
    save_config(config)
    return config


def save_config(config: dict) -> None:
    """Atomically write config to disk."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=CONFIG_DIR, suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(config, f, indent=2)
            f.write("\n")
        os.replace(tmp, CONFIG_FILE)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def get_active_profile() -> tuple[str, dict]:
    """Return (name, profile_data) for the active profile."""
    config = load_config()
    name = config.get("active_profile", "local")
    profiles = config.get("profiles", {})
    if name not in profiles:
        name = next(iter(profiles), "local")
    return name, profiles.get(name, {})


def get_active_database_url() -> str | None:
    """Shortcut: database_url from the active profile."""
    _, profile = get_active_profile()
    return profile.get("database_url") or None


def get_selected_account_ids() -> list[str]:
    """Return selected account IDs from the active profile (empty = all)."""
    _, profile = get_active_profile()
    return profile.get("selected_account_ids", [])


def get_defaults() -> dict:
    """Return defaults dict from the active profile."""
    _, profile = get_active_profile()
    return {**DEFAULT_DEFAULTS, **profile.get("defaults", {})}


def set_active_profile(name: str) -> None:
    """Switch active profile."""
    config = load_config()
    if name not in config.get("profiles", {}):
        raise ValueError(f"Profile '{name}' does not exist")
    config["active_profile"] = name
    save_config(config)


def upsert_profile(name: str, database_url: str) -> None:
    """Create or update a profile."""
    config = load_config()
    profiles = config.setdefault("profiles", {})
    if name in profiles:
        profiles[name]["database_url"] = database_url
    else:
        profiles[name] = {
            "database_url": database_url,
            "selected_account_ids": [],
            "defaults": dict(DEFAULT_DEFAULTS),
        }
    save_config(config)


def delete_profile(name: str) -> None:
    """Delete a profile. Refuses to delete the active one."""
    config = load_config()
    if config.get("active_profile") == name:
        raise ValueError("Cannot delete the active profile. Switch first.")
    config.get("profiles", {}).pop(name, None)
    save_config(config)


def update_selected_accounts(ids: list[str]) -> None:
    """Save selected account IDs for the active profile."""
    config = load_config()
    name = config.get("active_profile", "local")
    config.setdefault("profiles", {}).setdefault(name, {})["selected_account_ids"] = ids
    save_config(config)


def update_defaults(defaults: dict) -> None:
    """Save defaults for the active profile."""
    config = load_config()
    name = config.get("active_profile", "local")
    profile = config.setdefault("profiles", {}).setdefault(name, {})
    profile["defaults"] = {**DEFAULT_DEFAULTS, **profile.get("defaults", {}), **defaults}
    save_config(config)
