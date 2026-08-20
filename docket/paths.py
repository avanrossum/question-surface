"""Where questionnaires and responses live.

Decided by questionnaire (`ship-design`, 2026-08-14): they live in the project
being worked on, not next to the installed tool. A decision belongs in the
repository it is about, where it can be reviewed alongside the change it gates
and found by whoever clones that project a year later. Keeping them next to the
tool would pile every project's answers into one unrelated directory and lose
them if the clone were ever deleted.

There are two sources for a questionnaire and only one for a response:

- **Project questionnaires** — `<project>/.docket/questionnaires/`.
  Authored for that project. This is where `new` writes.
- **Bundled questionnaires** — the tool's own `questionnaires/`, shipped with
  the install. This is how `example` stays available everywhere without being
  copied into projects that only want to read it.
- **Responses** — always `<project>/.docket/responses/`. A response
  is a record about the project, so it is never written into the tool's
  directory, including when the questionnaire came from the bundle.
"""

from __future__ import annotations

import os
from pathlib import Path

# The single point of change if this directory is ever renamed.
STATE_DIR_NAME = ".docket"

TOOL_ROOT = Path(__file__).resolve().parent
BUNDLED_QUESTIONNAIRES = Path(__file__).resolve().parent / "questionnaires"

# Markers that mean "the root of a project" — checked in order at each level.
ROOT_MARKERS = (".git", ".hg", ".svn")


def project_root(start: Path | None = None) -> Path:
    """The project the caller is working in.

    The nearest enclosing repository, so that running the tool from a
    subdirectory writes to the same place as running it from the top. Falls
    back to the working directory when there is no repository, which keeps the
    tool usable in a scratch directory.
    """
    if override := os.environ.get("DOCKET_PROJECT"):
        return Path(override).expanduser().resolve()
    current = (start or Path.cwd()).resolve()
    for candidate in (current, *current.parents):
        if any((candidate / marker).exists() for marker in ROOT_MARKERS):
            return candidate
    return current


def state_dir(start: Path | None = None) -> Path:
    return project_root(start) / STATE_DIR_NAME


def questionnaires_dir(start: Path | None = None) -> Path:
    """Where project questionnaires live, and where `new` writes."""
    return state_dir(start) / "questionnaires"


def responses_dir(start: Path | None = None) -> Path:
    return state_dir(start) / "responses"


def search_path(start: Path | None = None) -> list[Path]:
    """Directories searched for a questionnaire, project first.

    Project first so a local questionnaire can shadow a bundled one of the same
    name — otherwise the tool's own `example` would be unreachable to override.
    """
    project = questionnaires_dir(start)
    if project.resolve() == BUNDLED_QUESTIONNAIRES.resolve():
        return [project]
    return [project, BUNDLED_QUESTIONNAIRES]
