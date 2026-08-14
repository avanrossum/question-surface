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
                # Deliberately never answered by the harness.
                {
                    "id": "must-answer",
                    "type": "text",
                    "prompt": "Required, and left blank on purpose",
                    "required": True,
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

    // A blank required question blocks submission and is pointed at.
    pick("gate", "build");
    document.getElementById("submitBtn").click();
    var panel = document.getElementById("result");
    log("blank_required_blocks", !panel.hidden &&
      /required/i.test(panel.textContent) && /blank/i.test(panel.textContent));
    log("blank_required_marked", q("must-answer").classList.contains("missing"));
    log("blank_required_not_submitted",
      document.getElementById("submitBtn").textContent === "Submit answers");

    // Close-on-submit ships off, and remembers the choice when it can.
    var toggle = document.getElementById("closeOnSubmit");
    log("close_toggle_present", !!toggle);
    log("close_toggle_default_off", toggle && toggle.checked === false);
    var storage = true;
    try { localStorage.setItem("qsurface:probe", "1"); localStorage.removeItem("qsurface:probe"); }
    catch (e) { storage = false; }
    log("storage_available", storage);
    if (toggle && storage) {
      toggle.checked = true;
      toggle.dispatchEvent(new Event("change", { bubbles: true }));
      log("close_toggle_persists", localStorage.getItem("qsurface:close-on-submit") === "1");
    }
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
    "blank_required_blocks": ("true", "a blank required question blocks submit"),
    "blank_required_marked": ("true", "the blocking question is marked on the page"),
    "blank_required_not_submitted": ("true", "the submit button stays ready to retry"),
    "close_toggle_present": ("true", "close-on-submit is offered on a served form"),
    "close_toggle_default_off": ("true", "close-on-submit ships off"),
}

# Only meaningful where the browser allows storage for the page's origin.
CONDITIONAL = {
    "close_toggle_persists": (
        "storage_available",
        "true",
        "close-on-submit remembers the choice",
    ),
}


# The interview page talks to a server for everything, so the checks stub
# fetch before the page's own script runs and drive it through each state.
STUB_TEMPLATE = """
<script>
window.__STUB__ = %s;
window.fetch = function (url, opts) {
  var route = String(url);
  var plan = window.__STUB__;
  if (plan.failEverything) return Promise.reject(new Error("offline"));
  var body;
  if (route.indexOf("/answer") !== -1) {
    body = { ok: true };
  } else {
    var seen = plan.pollCount = (plan.pollCount || 0) + 1;
    body = plan.polls[Math.min(seen - 1, plan.polls.length - 1)];
  }
  return Promise.resolve({ json: function () { return Promise.resolve(body); } });
};
</script>
"""

REPORTER = """
setTimeout(function () {
  var out = [];
  function log(k, v) { out.push(k + "=" + v); }
  function active(id) {
    var el = document.getElementById(id);
    return el && el.classList.contains("is-active");
  }
  log("state_asking", active("stateAsking"));
  log("state_processing", active("stateProcessing"));
  log("state_done", active("stateDone"));
  log("state_lost", active("stateLost"));
  log("history_count", document.querySelectorAll(".iv-exchange").length);
  log("prompt_text", (document.getElementById("ivPrompt").textContent || "").slice(0, 24));
  var pre = document.createElement("pre");
  pre.textContent = "\\n@@" + out.join("\\n@@") + "\\n";
  document.body.appendChild(pre);
}, %d);
"""


def interview_page_html() -> str:
    from qsurface import interview  # noqa: PLC0415

    record = interview.new_record("check", "Interview check", "systems design", 0)
    return render.interview_page(record)


# Answers the first question that appears, the way a respondent would.
AUTO_ANSWER = """
<script>
(function () {
  var tries = 0;
  var timer = setInterval(function () {
    var asking = document.getElementById("stateAsking");
    if (asking && asking.classList.contains("is-active")) {
      document.getElementById("ivAnswer").value = "the deploy drops them";
      document.getElementById("ivSend").click();
      clearInterval(timer);
    }
    if (++tries > 200) clearInterval(timer);
  }, 40);
})();
</script>
"""


def run_interview_case(
    chrome: str, plan: dict, settle_ms: int, tmp: Path, auto_answer: bool = False
) -> dict:
    html = interview_page_html()
    html = html.replace("</head>", (STUB_TEMPLATE % json.dumps(plan)) + "</head>")
    tail = (AUTO_ANSWER if auto_answer else "") + "<script>" + (REPORTER % settle_ms) + "</script>"
    html = html.replace("</body>", tail + "</body>")
    page = tmp / "interview.html"
    page.write_text(html, encoding="utf-8")
    dom = browser.dump_dom(page, chrome=chrome, budget_ms=settle_ms + 8000)

    results: dict[str, str] = {}
    for line in dom.splitlines():
        idx = line.find("@@")
        while idx != -1:
            rest = line[idx + 2 :]
            end = rest.find("<")
            field = rest if end == -1 else rest[:end]
            if "=" in field:
                key, _, value = field.partition("=")
                results[key.strip()] = value.strip()
            idx = line.find("@@", idx + 2)
    return results


# The processing animation cannot be sampled by waiting: CSS animations do not
# advance under --virtual-time-budget. Seeking the animation directly tests the
# keyframes themselves, which is the thing that would break in an edit anyway.
MOTION_HARNESS = """
(function () {
  var out = [];
  function log(k, v) { out.push(k + "=" + v); }
  try {
    document.getElementById("stateProcessing").classList.add("is-active");
    var caret = document.querySelector(".iv-mark-caret");
    var anims = caret.getAnimations();
    log("caret_animation", anims.map(function (a) { return a.animationName; }).join("|"));
    var ys = [];
    [0, 1900, 3900, 5900, 7900].forEach(function (ms) {
      anims[0].currentTime = ms;
      var m = getComputedStyle(caret).transform;
      ys.push(m === "none" ? 0 : Math.round(parseFloat(m.split(",")[5]) || 0));
    });
    log("caret_stops", ys.filter(function (v, i, a) { return a.indexOf(v) === i; }).length);
    log("caret_travel", Math.max.apply(null, ys) - Math.min.apply(null, ys));

    var line = document.querySelectorAll(".iv-mark-lines span")[0];
    var lineAnim = line.getAnimations()[0];
    var colors = [];
    [0, 1000, 5000].forEach(function (ms) {
      lineAnim.currentTime = ms;
      var c = getComputedStyle(line).backgroundColor;
      if (colors.indexOf(c) === -1) colors.push(c);
    });
    log("line_highlights", colors.length);
    log("reduced_motion_respected",
      typeof window.matchMedia("(prefers-reduced-motion: reduce)").matches === "boolean");
  } catch (err) {
    log("motion_error", String(err && err.message || err));
  }
  var pre = document.createElement("pre");
  pre.textContent = "\\n@@" + out.join("\\n@@") + "\\n";
  document.body.appendChild(pre);
})();
"""


def check_processing_motion(chrome: str, tmp: Path) -> list:
    from qsurface import interview  # noqa: PLC0415

    record = interview.new_record("motion", "Motion check", "", 0)
    html = render.interview_page(record)
    html = html.replace("</body>", "<script>" + MOTION_HARNESS + "</script></body>")
    page = tmp / "motion.html"
    page.write_text(html, encoding="utf-8")
    dom = browser.dump_dom(page, chrome=chrome, budget_ms=3000)

    results: dict[str, str] = {}
    for line in dom.splitlines():
        idx = line.find("@@")
        while idx != -1:
            rest = line[idx + 2 :]
            end = rest.find("<")
            field = rest if end == -1 else rest[:end]
            if "=" in field:
                key, _, value = field.partition("=")
                results[key.strip()] = value.strip()
            idx = line.find("@@", idx + 2)

    return [
        (results.get("caret_animation"), "ivCaret", "the reading mark is animated"),
        (results.get("caret_stops"), "5", "the mark stops at each of the five lines"),
        (results.get("caret_travel"), "96", "the mark travels the full column"),
        (results.get("line_highlights"), "2", "a line lights as the mark reaches it"),
    ]


def check_interview(chrome: str) -> int:
    """Drive the interview page through asking, done, and lost."""
    failures = 0
    print("\ninterview mode")

    with tempfile.TemporaryDirectory() as tmp_name:
        tmp = Path(tmp_name)

        # A question arrives, is answered, and the interview ends.
        flow = run_interview_case(
            chrome,
            {
                "polls": [
                    {"question": {"seq": 1, "prompt": "What broke first?",
                                  "why": "symptom before solution", "options": []}},
                    {"done": True, "summary": "thanks"},
                ]
            },
            1500,
            tmp,
            auto_answer=True,
        )
        expectations = [
            (flow.get("state_asking"), "false", "the question is cleared once answered"),
            (flow.get("state_done"), "true", "a finished interview shows the wrap-up"),
            (flow.get("history_count"), "1", "the answered exchange joins the transcript"),
        ]

        # A question arrives and nothing else does — the page must wait, visibly.
        waiting = run_interview_case(
            chrome, {"polls": [{"question": {"seq": 1, "prompt": "Still thinking?"}},
                               {"waiting": True}]}, 600, tmp
        )
        expectations += [
            (waiting.get("state_asking"), "true", "an unanswered question stays on screen"),
            (waiting.get("prompt_text"), "Still thinking?", "the prompt is rendered"),
        ]

        # The agent dies. The page must say so rather than animate forever.
        lost = run_interview_case(chrome, {"failEverything": True}, 14000, tmp)
        expectations += [
            (lost.get("state_lost"), "true", "a dead agent surfaces as lost contact"),
            (lost.get("state_processing"), "false", "the processing state does not persist"),
        ]
        expectations += check_processing_motion(chrome, tmp)

    for actual, expected, description in expectations:
        if actual == expected:
            print(f"  ok    {description}")
        else:
            failures += 1
            print(f"  FAIL  {description}")
            print(f"        expected {expected!r}, got {actual!r}")
    return failures


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
    # Rendered as if served, so the close-on-submit control is present. The
    # page's fetches fail with no server behind them, which the app already
    # handles and none of these checks reach.
    html = render.render(validated)

    with tempfile.TemporaryDirectory() as tmp:
        results = browser.drive(html, HARNESS, Path(tmp), chrome=chrome)

    if "harness_error" in results:
        print(f"FAIL  harness raised: {results['harness_error']}")
        return 1
    if not results:
        print("FAIL  the page reported nothing — it likely failed to load")
        return 1

    failures = 0
    ran = 0
    for key, (expected, description) in EXPECTED.items():
        actual = results.get(key)
        ran += 1
        if actual == expected:
            print(f"  ok    {description}")
        else:
            failures += 1
            print(f"  FAIL  {description}")
            print(f"        {key}: expected {expected!r}, got {actual!r}")

    for key, (guard, expected, description) in CONDITIONAL.items():
        if results.get(guard) != "true":
            print(f"  skip  {description} ({guard} is false here)")
            continue
        ran += 1
        actual = results.get(key)
        if actual == expected:
            print(f"  ok    {description}")
        else:
            failures += 1
            print(f"  FAIL  {description}")
            print(f"        {key}: expected {expected!r}, got {actual!r}")

    interview_failures = check_interview(chrome)
    failures += interview_failures
    ran += 11

    print()
    if failures:
        print(f"{failures} of {ran} client-side checks failed")
        return 1
    print(f"{ran} client-side checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
