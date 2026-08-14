# Design and testing

The constraints this tool is built under, why they hold, and how it is checked.

---

## Constraints

**Standard library only.** No npm, no pip install, no build step, no lockfile. A tool that stops working because a dependency moved is not durable, and this one has to still run in a year without anyone maintaining it. The development harness may use what is already on the machine — a browser, for instance — but the shipped tool may not require anything.

**Loopback only.** `127.0.0.1`, no auth, no session model, no multi-tenant path. There must never be a reason to expose it. This is why the voice answer is the operating system's own dictation rather than a cloud recognition service.

**No interface of its own.** No Electron, no single-page app, no desktop shell. Launching a browser at a local page is the whole design.

**The JSON is authoritative.** The markdown beside it is a regenerable render, kept because a decision record that cannot be read in a diff is one nobody reviews.

**Validation fails at load.** A duplicate id, a forward-referencing conditional, or a recommendation naming an option that does not exist costs a round trip with a human — which is the exact cost the tool exists to remove.

---

## How it is put together

```
qsurface.py              CLI
qsurface/spec.py         the single authority on what a valid questionnaire is
qsurface/store.py        response building, visibility, persistence
qsurface/render.py       spec and interview record → HTML
qsurface/server.py       the loopback server for a questionnaire
qsurface/interview.py    session state machine and detached server
qsurface/paths.py        where questionnaires and responses live
qsurface/config.py       per-user settings
qsurface/browser.py      locating and driving a headless browser
assets/                  app.css, app.js, interview.css, interview.js — inlined at render
```

Two things are worth knowing before changing anything.

**Conditionals are evaluated twice**, in `assets/app.js` and in `qsurface/store.py`, and the two must agree. Changing one without the other produces a form that shows a question the server records as skipped, or the reverse. There are tests on both sides.

**Hidden means empty, on both sides.** When a branch hides, the client clears the control as well as the stored value, and the server drops notes, resolved labels, and recommendation verdicts for anything not visible. Half-clearing produces a form that looks answered and submits blank — which is exactly the bug that shipped once already.

---

## Testing

```bash
python3 -m unittest discover -s tests -t .   # 94 tests
python3 scripts/check_browser.py             # 41 client-side checks
```

The Python suite covers spec validation, response building, conditional visibility, persistence, rendering, path resolution, config, follow-up panels, and the interview state machine.

The client-side checks cover `assets/app.js` and `assets/interview.js`, which the Python suite cannot reach. They drive a real Chromium-family browser if one is installed and skip cleanly if not, rather than pulling in a JavaScript toolchain and breaking the no-build-step constraint. `--require` turns a missing browser into a failure, which is what CI uses.

CI runs the Python suite on 3.9 through 3.13 and the browser checks with `--require`.

### What the browser checks have caught

Six real defects so far, which is the argument for keeping them:

- **A rank question counted as blank until dragged.** A ranked list renders a complete ordering the moment it appears, so a respondent who agreed with the presented order had to disturb it to prove agreement. It now records the presented order with `reordered: false`, keeping acceptance distinguishable from an arranged ranking.
- **A hidden branch kept its controls filled in.** Re-showing the branch displayed a checked radio that submit reported as blank.
- **The interview client could busy-loop.** Its long poll re-issued the instant it returned, paced only by the server holding the connection open. Anything answering immediately would have spun it as fast as the event loop allowed. It hung a headless Chrome outright, which is how it was found.
- **A closing summary printed once per answer.** `send()` forked a second poll loop on every answer, and each fork called `finish()` at the end.
- **The context "Read more" toggle never appeared.** Overflow was measured while the card was still `display:none`, where both heights read zero.
- **The context clamp did nothing at all.** `-webkit-line-clamp` only counts inline text, and the block almost always holds a table or a list.

And two checks that were passing while testing nothing. One named `submitted_with_blanks` claimed to prove a blank required question blocks submission, but the harness had answered every required question by that point, so what it observed was the standalone preview panel appearing. Another asserted the context was clamped by looking for the class name rather than measuring whether anything was actually clipped — which is how the broken clamp above survived its own check.

### A note on timing

CSS animations do not advance under Chrome's `--virtual-time-budget`. Any check that samples an animation over time will observe a frozen clock, report success against a stationary element, and prove nothing. The motion checks seek animations directly through `getAnimations()` for that reason.

---

## Releases

Semver, annotated tags, and a changelog entry per release.

1. Update `CHANGELOG.md` with what changed and why.
2. Bump `__version__` in `qsurface/__init__.py`.
3. Run both suites.
4. Commit, then `git tag -a vX.Y.Z -m "..."`.

Adding a field to the response document is a minor bump. Anything that stops an existing questionnaire loading is a major, and needs `SPEC_VERSION` handling rather than a break.

Screenshots in the README are generated by `scripts/make_screenshots.py` from the real renderer, so they cannot drift. Re-run it after changing any CSS or markup.
