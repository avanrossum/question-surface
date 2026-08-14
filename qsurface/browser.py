"""Locating and driving a headless browser.

The client-side half of this tool is real logic — conditional visibility, rank
seeding, progress counting, draft restore — and none of it is reachable from the
Python suite. Both bugs found in the first review were in `assets/app.js`.

Rather than take on a JavaScript toolchain and break the no-build-step
constraint, the checks drive a browser that is already on the machine and skip
cleanly when there isn't one. That trade is deliberate: a check that sometimes
skips is worth more than a dependency that makes the tool un-runnable in a year.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

MAC_CANDIDATES = (
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
)
PATH_CANDIDATES = (
    "google-chrome",
    "google-chrome-stable",
    "chromium",
    "chromium-browser",
    "microsoft-edge",
)


def find_chrome() -> str:
    """Path to a Chromium-family browser, or "" if none is installed."""
    for name in PATH_CANDIDATES:
        found = shutil.which(name)
        if found:
            return found
    for candidate in MAC_CANDIDATES:
        if Path(candidate).exists():
            return candidate
    return ""


def dump_dom(page: Path, chrome: str = "", budget_ms: int = 4000) -> str:
    """Load a local page, let its scripts run, and return the resulting DOM."""
    chrome = chrome or find_chrome()
    if not chrome:
        raise RuntimeError("no Chromium-family browser found")
    result = subprocess.run(
        [
            chrome,
            "--headless",
            "--disable-gpu",
            "--no-sandbox",
            f"--virtual-time-budget={budget_ms}",
            "--dump-dom",
            page.resolve().as_uri(),
        ],
        capture_output=True,
        text=True,
        timeout=90,
    )
    return result.stdout


def drive(html: str, script: str, tmp_dir: Path, chrome: str = "") -> dict[str, str]:
    """Run `script` against a rendered page and collect what it reports.

    The script reports by appending `@@key=value` lines to the document. Values
    come back through the DOM, so they are read as text rather than parsed as
    JavaScript — a harness that lies is a harness that passes.
    """
    page = tmp_dir / "driven.html"
    page.write_text(html.replace("</body>", f"<script>{script}</script>\n</body>"), "utf-8")
    dom = dump_dom(page, chrome=chrome)

    results: dict[str, str] = {}
    for line in dom.splitlines():
        marker = line.find("@@")
        while marker != -1:
            rest = line[marker + 2 :]
            end = rest.find("<")
            field = rest if end == -1 else rest[:end]
            if "=" in field:
                key, _, value = field.partition("=")
                results[key.strip()] = value.strip()
            marker = line.find("@@", marker + 2)
    return results
