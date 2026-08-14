# Question Surface

A local web form for collecting answers to a large set of questions in one pass. Standard-library Python, no dependencies, no build step. `README.md` is the format reference.

## Asking more than four questions — the Question Surface (governed)

**Five or more questions go through the Question Surface. Four or fewer may be asked in chat.** The workflow, the authoring quality bar, and the spec format are in the **`question-surface` skill** (`.claude/skills/question-surface/`); the README is the format reference.

A long question set asked serially in chat degrades predictably: each answer arrives without the others in view, so the tradeoffs between them are invisible; later questions get shorter answers than early ones; conditional follow-ups arrive after the context that made them meaningful is gone; and the answers scatter across a transcript nobody re-reads, so the next session re-derives half of them. Collecting the set at once removes all of that and leaves a durable artifact — a tracked questionnaire and a tracked response — instead of a transcript.

- **The tool is stdlib-Python and dependency-free**, serves on loopback only, and blocks until submitted. `./qsurface.py serve <id>`.
- **Questionnaires and responses are both tracked in git.** A response is a record of decisions; a decision that exists only in a chat transcript is a decision nobody can find later.
- **`flagged_unknown` in a response is a work item, not a non-answer.** Those questions need research; turn them into tracked items rather than re-asking them.
- **Enforcement is model-enforced.** No hook can catch it, because the failure mode is writing questions into a chat message rather than calling a tool. **A numbered list of questions in a chat message is the violation.**
- The gate is a floor on batching, not a licence to manufacture questions. Routine judgement calls are still made, not asked.

## Working on the tool itself

- **Standard library only.** No npm, no pip install, no build step. This constraint is the reason the tool still runs unattended a year later; do not relax it.
- **Loopback only.** `127.0.0.1`, no auth, no session model, no multi-tenant path. There must never be a reason to expose it.
- **`spec.py` is the single authority on what a valid spec looks like.** The renderer and the store both assume they are handed an already-validated spec. New spec features get their validation there first.
- **Conditionals are evaluated twice — in `assets/app.js` and in `qsurface/store.py`.** The two implementations must agree. Changing one without the other produces a form that shows a question the server records as `skipped`, or the reverse. There are tests for this; keep them passing.
- **The JSON response is authoritative; the markdown is a regenerable render of it.**
- Run the tests before committing: `python3 -m unittest discover -s tests -t .`

## Layout

```
qsurface.py              # CLI
qsurface/                # spec validation, rendering, storage, server
assets/                  # app.css + app.js, inlined into the rendered page
questionnaires/<id>.json # authored question sets — tracked
responses/<id>/          # <timestamp>.json + .md — tracked; draft.json — not
tests/
```
