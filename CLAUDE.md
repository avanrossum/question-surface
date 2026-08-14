# Question Surface

A local web form for collecting answers to a batch of questions in one pass. Standard-library Python, no dependencies, no build step. `README.md` is the format reference; `ROADMAP.md` records what was deliberately left out and why.

## Asking the user questions (governed)

**Five or more questions go through the Question Surface, and so does any smaller number whose answers would benefit from exposition, detailed answer choices, or open-ended interaction.** The workflow, the authoring quality bar, and the spec format are in the **`question-surface` skill** (`.claude/skills/question-surface/`).

A long or dense question set asked serially in chat degrades predictably: each answer arrives without the others in view, so the tradeoffs between them are invisible; later questions get shorter answers than early ones; conditional follow-ups arrive after the context that made them meaningful is gone; and the answers scatter across a transcript nobody re-reads, so the next session re-derives half of them. Collecting the set at once removes all of that and leaves a durable artifact — a tracked questionnaire and a tracked response — instead of a transcript.

- **Serve in the background, then keep working.** `qsurface serve <id>` blocks until submission. Run it as a background command, tell the user the URL, and proceed with everything the answers do not block. Say which parts are waiting.
- **Questionnaires and responses are tracked in git.** A response is a record of decisions; a decision that exists only in a chat transcript is a decision nobody can find later. Commit them with the work they gate — the tool does not stage them itself.
- **`flagged_unknown` is a work item, not a non-answer.** Those questions need research. Do it, or track it; do not re-ask them.
- **Enforcement is model-enforced.** No hook can catch it, because the failure mode is writing questions into a chat message rather than calling a tool. **A numbered list of questions in a chat message is the violation.**
- The gate is a floor on batching, not a licence to manufacture questions. Routine judgement calls are still made, not asked.

This repo uses its own tool: the decisions behind the current design are in `.question-surface/responses/`.

## Working on the tool itself

- **Standard library only.** No npm, no pip install, no build step. This constraint is the reason the tool still runs unattended a year later; do not relax it. The development harness may use what is already on the machine (a browser), but the shipped tool may not require anything.
- **Loopback only.** `127.0.0.1`, no auth, no session model, no multi-tenant path. There must never be a reason to expose it.
- **`spec.py` is the single authority on what a valid spec looks like.** The renderer and the store both assume they are handed an already-validated spec. New spec features get their validation there first, and a format change means bumping `SPEC_VERSION`.
- **Conditionals are evaluated twice — in `assets/app.js` and in `qsurface/store.py`.** The two implementations must agree. Changing one without the other produces a form that shows a question the server records as `skipped`, or the reverse. There are tests on both sides; keep them passing.
- **Hidden means empty, on both sides.** When a branch hides, the client clears the control as well as the stored value, and the server drops notes, labels and recommendation verdicts for anything not visible. Half-clearing produces a form that looks answered and submits blank.
- **`paths.py` owns where things live.** `STATE_DIR_NAME` is the single point of change if the project directory is ever renamed.
- **The JSON response is authoritative; the markdown is a regenerable render of it.**

Before committing:

```bash
python3 -m unittest discover -s tests -t .   # 60 tests
python3 scripts/check_browser.py             # 12 client-side checks, needs a browser
```

The browser checks are not optional when `assets/app.js` changed — that file is where both of the bugs found in the first review lived, and the Python suite cannot see any of it.

## Releases

Semver, annotated tags, and a changelog entry per release.

1. Update `CHANGELOG.md` with what changed and why.
2. Bump `__version__` in `qsurface/__init__.py`.
3. Run both suites.
4. Commit, then `git tag -a vX.Y.Z -m "..."`.

A response format change that adds a field is a minor bump; anything that makes an existing questionnaire stop loading is a major, and needs `SPEC_VERSION` handling rather than a break.

## Layout

```
qsurface.py              # CLI
qsurface/                # spec, store, render, server, paths, config, browser
assets/                  # app.css + app.js, inlined into the rendered page
questionnaires/          # bundled reference questionnaire, ships with the tool
scripts/check_browser.py # client-side checks
install.sh               # user install / uninstall
tests/
.question-surface/       # this project's own questionnaires and responses
```
