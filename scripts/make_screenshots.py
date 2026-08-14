#!/usr/bin/env python3
"""Regenerate the README screenshots.

The images in `docs/images/` are produced from the real renderer rather than
mocked up, so they cannot drift from what the tool actually looks like. Re-run
this after any change to `assets/app.css` or the renderer.

    python3 scripts/make_screenshots.py

Needs a Chromium-family browser. Writes PNGs into docs/images/.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from qsurface import browser, render, spec as spec_mod, store  # noqa: E402

OUT = ROOT / "docs" / "images"

# A questionnaire built to photograph well: one recommended fork with real
# tradeoffs, a conditional, a ranking, and a scale — the whole vocabulary in
# one screen without scrolling past anything dull.
DEMO = {
    "id": "demo",
    "title": "Session storage — architecture decisions",
    "intro": "Four decisions that gate the storage rewrite. Recommendations are marked; disagreeing with one is a useful answer.",
    "context_docs": ["docs/DISCOVERY.md", "ADR-014"],
    "sections": [
        {
            "title": "Storage model",
            "intro": "Where session state lives and what that commits us to.",
            "questions": [
                {
                    "type": "info",
                    "prompt": "Current sessions are held in process memory, so a deploy drops every signed-in user. Everything below assumes we are fixing that now rather than after the migration.",
                },
                {
                    "id": "backing-store",
                    "type": "single",
                    "prompt": "What backs the session store?",
                    "why": "Decides the failure mode when the store is unreachable, and whether sessions survive a deploy. Everything else on this form depends on it.",
                    "required": True,
                    "recommend": "redis",
                    "options": [
                        {
                            "value": "redis",
                            "label": "Redis",
                            "detail": "Survives deploys, sub-millisecond reads, one more service to operate and page on.",
                        },
                        {
                            "value": "postgres",
                            "label": "The existing Postgres",
                            "detail": "No new infrastructure. Adds write load to the database that is already the bottleneck.",
                        },
                        {
                            "value": "signed-cookie",
                            "label": "Signed cookies, no server state",
                            "detail": "Nothing to operate and nothing to lose. Revocation becomes hard and payload size is capped.",
                        },
                    ],
                },
                {
                    "id": "eviction",
                    "type": "single",
                    "prompt": "How do sessions expire?",
                    "why": "Only matters with a server-side store — a signed cookie carries its own expiry.",
                    "show_if": {"question": "backing-store", "not_equals": "signed-cookie"},
                    "options": [
                        {"value": "sliding", "label": "Sliding window", "detail": "Active users stay signed in indefinitely."},
                        {"value": "absolute", "label": "Absolute expiry", "detail": "Everyone re-authenticates on a fixed cadence."},
                    ],
                },
            ],
        },
        {
            "title": "Rollout",
            "questions": [
                {
                    "id": "priorities",
                    "type": "rank",
                    "prompt": "Order these by what matters most for the cutover.",
                    "why": "Where they conflict, this is the tiebreak I will apply without asking again.",
                    "options": [
                        {"value": "zero-downtime", "label": "Zero downtime"},
                        {"value": "revocable", "label": "Instant revocation"},
                        {"value": "simple-ops", "label": "Fewest moving parts"},
                    ],
                },
                {
                    "id": "confidence",
                    "type": "scale",
                    "prompt": "How settled is this direction?",
                    "why": "A low score means I plan for a reversal rather than building on it.",
                    "min": 1,
                    "max": 5,
                    "min_label": "Still exploring",
                    "max_label": "Locked",
                },
            ],
        },
    ],
}


def shot(chrome: str, html: str, name: str, size: str, theme: str = "light") -> None:
    # Pin the theme rather than inheriting it: headless Chrome reports a dark
    # prefers-color-scheme, so an unpinned "light" shot comes out dark.
    html = html.replace('<html lang="en">', f'<html lang="en" data-theme="{theme}">')
    with tempfile.TemporaryDirectory() as tmp:
        page = Path(tmp) / "page.html"
        page.write_text(html, encoding="utf-8")
        target = OUT / name
        subprocess.run(
            [
                chrome,
                "--headless",
                "--disable-gpu",
                "--no-sandbox",
                "--hide-scrollbars",
                "--virtual-time-budget=3000",
                f"--window-size={size}",
                f"--screenshot={target}",
                page.resolve().as_uri(),
            ],
            capture_output=True,
            check=True,
            timeout=90,
        )
        print(f"  wrote {target.relative_to(ROOT)}  ({size})")


def main() -> int:
    chrome = browser.find_chrome()
    if not chrome:
        print("no Chromium-family browser found — cannot render screenshots")
        return 1
    OUT.mkdir(parents=True, exist_ok=True)
    print(f"browser  {chrome}")

    spec = spec_mod.validate(json.loads(json.dumps(DEMO)))
    # Photograph the form mid-completion: an empty form shows the layout but
    # none of the behaviour — the revealed conditional, the recommendation the
    # respondent went against, and the progress readout are the point.
    draft = {
        "backing-store": {"value": "postgres", "unknown": False,
                          "notes": "one less service to run on-call for"},
        "eviction": {"value": "sliding", "unknown": False, "notes": ""},
        "priorities": {"value": ["simple-ops", "zero-downtime", "revocable"],
                       "unknown": False, "notes": "", "reordered": True},
        "confidence": {"value": 4, "unknown": False, "notes": ""},
    }
    # Rendered as served, not standalone, so the shot matches what a
    # respondent actually sees — including the close-on-submit control.
    html = render.render(spec, draft=draft, respondent="Alex")

    shot(chrome, html, "form-light.png", "1440,1250", theme="light")
    shot(chrome, html, "form-dark.png", "1440,1250", theme="dark")

    # The follow-up panel needs a prior response to show.
    prior_spec = spec_mod.validate(json.loads(json.dumps(DEMO)))
    prior = store.build_response(
        prior_spec,
        {
            "backing-store": {"value": "redis", "notes": "ops cost is acceptable"},
            "eviction": {"value": "sliding"},
            "confidence": {"unknown": True},
        },
    )
    follow = spec_mod.validate(
        {
            "id": "demo-round-two",
            "title": "Session storage — round two",
            "intro": "Follow-up after the spike. What the first round settled is shown above the questions.",
            "follows": "demo",
            "sections": [
                {
                    "title": "After the spike",
                    "questions": [
                        {
                            "id": "revisit",
                            "type": "single",
                            "prompt": "Does the benchmark change the storage choice?",
                            "why": "The spike measured p99 under the real session size.",
                            "options": [
                                {"value": "no", "label": "No — proceed as decided"},
                                {"value": "yes", "label": "Yes — reopen it"},
                            ],
                        }
                    ],
                }
            ],
        }
    )
    shot(
        chrome,
        render.render(follow, respondent="Alex", prior=prior),
        "follow-up.png",
        "1440,980",
        theme="light",
    )
    print("done")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
