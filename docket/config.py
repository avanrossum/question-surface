"""Per-user settings.

Settings that belong to the person rather than to a questionnaire or a project.
Today that is the gate — how many questions send an agent to the surface instead
of into a chat message — which has to be per-user because the right number
depends on how someone works.

The file is the source of truth. Because a skill is static text an agent reads
rather than a program that can look things up, `install.sh` also writes the
current gate into a pointer line in the user's global `CLAUDE.md`, so the number
is in context without costing a tool call. `config set` rewrites that line, which
is why setting the gate goes through this module rather than an editor.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

DEFAULTS: dict = {
    # Questions at or above this count go through the surface. 0 disables the
    # floor entirely, leaving the skill's judgement guidance and nothing else.
    "gate": 5,
    # Minutes `serve` waits for a submission before giving up. 0 waits forever.
    "timeout_minutes": 120,
}

VALID_KEYS = tuple(DEFAULTS)


def config_dir() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME") or (Path.home() / ".config")
    return Path(base) / "docket"


def config_path() -> Path:
    return config_dir() / "config.json"


def load() -> dict:
    """Current settings, defaults filled in. A corrupt file reads as defaults."""
    settings = dict(DEFAULTS)
    path = config_path()
    if path.exists():
        try:
            stored = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return settings
        if isinstance(stored, dict):
            for key, value in stored.items():
                if key in DEFAULTS:
                    settings[key] = value
    return settings


def get(key: str):
    return load().get(key, DEFAULTS.get(key))


def set_value(key: str, value: int) -> Path:
    """Persist one setting. Returns the file written."""
    if key not in DEFAULTS:
        raise KeyError(f"unknown setting {key!r} — known: {', '.join(VALID_KEYS)}")
    settings = load()
    settings[key] = value
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(settings, indent=2) + "\n", encoding="utf-8")
    return path


def gate_sentence(gate: int | None = None) -> str:
    """The one line the installer keeps in the user's global CLAUDE.md."""
    gate = load()["gate"] if gate is None else gate
    if not gate:
        return (
            "The Docket: no fixed question count triggers the surface — "
            "use the `docket` skill's judgement guidance."
        )
    return (
        f"The Docket: {gate} or more questions for the user go through the "
        f"`docket` skill, never a numbered list in chat. Fewer than {gate} "
        "also go through it when the answers would benefit from exposition, "
        "detailed answer choices, or open-ended interaction."
    )
