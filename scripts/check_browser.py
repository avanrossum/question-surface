#!/usr/bin/env python3
"""Client-side checks, run in a real browser.

Covers the parts of `assets/app.js` the Python suite cannot see: conditional
show/hide and the residue it must clear, rank seeding, progress counting, and
draft restore. Every check here corresponds to a way the form has actually been
wrong, or could silently go wrong without anyone noticing until a respondent
sees it.

    python3 scripts/check_browser.py            # run them
    python3 scripts/check_browser.py --require   # fail instead of skip if no browser

Exits 0 when the checks pass or are skipped for want of a browser, 1 on failure.
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from qsurface import browser, render, spec as spec_mod  # noqa: E402

SPEC = {
    "id": "browser-check",
    "title": "Browser check",
    "sections": [
        {
            "title": "Checks",
            "questions": [
                {
                    "id": "gate",
                    "type": "single",
                    "prompt": "Which path?",
                    "required": True,
                    "options": ["build", "defer"],
                },
                {
                    "id": "branch-radio",
                    "type": "single",
                    "prompt": "Why defer?",
                    "options": ["cost", "risk"],
                    "show_if": {"question": "gate", "equals": "defer"},
                },
                {
                    "id": "branch-text",
                    "type": "longtext",
                    "prompt": "Until when?",
                    "show_if": {"question": "gate", "equals": "defer"},
                },
                {
                    "id": "nested",
                    "type": "text",
                    "prompt": "Nested under a hidden question",
                    "show_if": {"question": "branch-radio", "answered": True},
                },
                {
                    "id": "order",
                    "type": "rank",
                    "prompt": "Order these",
                    "options": ["a", "b", "c"],
                },
            ],
        }
    ],
}

HARNESS = """
(function () {
  var out = [];
  function log(k, v) { out.push(k + "=" + v); }
  function q(id) { return document.querySelector('.q[data-qid="' + id + '"]'); }
  function fire(el, t) { el.dispatchEvent(new Event(t, { bubbles: true })); }
  function pick(id, v) {
    var i = q(id).querySelector('input[value="' + v + '"]');
    i.checked = true; fire(i, "change");
  }
  try {
    // An untouched rank list is an answer, not a blank.
    log("rank_seeded", q("order").classList.contains("answered"));
    log("progress_initial", document.getElementById("progressCount").textContent);

    // A branch off a hidden question stays hidden.
    log("nested_hidden_initially", q("nested").hidden);

    pick("gate", "defer");
    log("branch_shown", !q("branch-radio").hidden);

    pick("branch-radio", "cost");
    log("nested_shown_once_parent_answered", !q("nested").hidden);
    var unk = q("branch-radio").querySelector(".qs-unknown");
    unk.checked = true; fire(unk, "change");
    var notes = q("branch-radio").querySelector(".qs-notes");
    notes.value = "note"; fire(notes, "input");
    var txt = q("branch-text").querySelector(".text-input");
    txt.value = "text"; fire(txt, "input");

    pick("gate", "build");
    log("branch_hidden", q("branch-radio").hidden);
    log("nested_hidden_again", q("nested").hidden);

    pick("gate", "defer");
    log("radio_residue", q("branch-radio").querySelector('input[value="cost"]').checked);
    log("unknown_residue", q("branch-radio").querySelector(".qs-unknown").checked);
    log("notes_residue", q("branch-radio").querySelector(".qs-notes").value === "");
    log("text_residue", q("branch-text").querySelector(".text-input").value === "");

    // Required-but-blank blocks submission.
    pick("gate", "build");
    document.getElementById("submitBtn").click();
    log("submitted_with_blanks", !document.getElementById("result").hidden);
  } catch (err) {
    log("harness_error", String(err && err.message || err));
  }
  var pre = document.createElement("pre");
  pre.textContent = "\\n@@" + out.join("\\n@@") + "\\n";
  document.body.appendChild(pre);
})();
"""

# key -> (expected, what it proves)
EXPECTED = {
    "rank_seeded": ("true", "an untouched rank list counts as answered"),
    "progress_initial": ("1", "only the rank question is answered on load"),
    "nested_hidden_initially": ("true", "a branch off a hidden question stays hidden"),
    "branch_shown": ("true", "a conditional appears when its condition is met"),
    "nested_shown_once_parent_answered": ("true", "a nested branch opens with its parent"),
    "branch_hidden": ("true", "a conditional hides when its condition stops holding"),
    "nested_hidden_again": ("true", "hiding a parent hides what hangs off it"),
    "radio_residue": ("false", "a re-shown branch has no stale checked radio"),
    "unknown_residue": ("false", "a re-shown branch has no stale unknown flag"),
    "notes_residue": ("true", "a re-shown branch has no stale notes"),
    "text_residue": ("true", "a re-shown branch has no stale text"),
    "submitted_with_blanks": ("true", "a blank required question blocks submit"),
}


def main() -> int:
    require = "--require" in sys.argv
    chrome = browser.find_chrome()
    if not chrome:
        message = "no Chromium-family browser found"
        if require:
            print(f"FAIL  {message} (--require)")
            return 1
        print(f"skip  {message} — client-side checks not run")
        print("      install Chrome or Chromium to run them")
        return 0

    print(f"browser  {chrome}")
    validated = spec_mod.validate(json.loads(json.dumps(SPEC)))
    html = render.render(validated, standalone=True)

    with tempfile.TemporaryDirectory() as tmp:
        results = browser.drive(html, HARNESS, Path(tmp), chrome=chrome)

    if "harness_error" in results:
        print(f"FAIL  harness raised: {results['harness_error']}")
        return 1
    if not results:
        print("FAIL  the page reported nothing — it likely failed to load")
        return 1

    failures = 0
    for key, (expected, description) in EXPECTED.items():
        actual = results.get(key)
        if actual == expected:
            print(f"  ok    {description}")
        else:
            failures += 1
            print(f"  FAIL  {description}")
            print(f"        {key}: expected {expected!r}, got {actual!r}")

    print()
    if failures:
        print(f"{failures} of {len(EXPECTED)} client-side checks failed")
        return 1
    print(f"{len(EXPECTED)} client-side checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
