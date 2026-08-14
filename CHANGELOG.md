# Changelog — Question Surface

Semver. Newest first. The tool carries its own version because questionnaires authored against one spec format have to keep working against later ones.

---

## 1.0.0 — 2026-08-14

Initial release as a standalone repository. The engine is unchanged from the version that was in use inside a governance repo; the questionnaires, responses, and governance wiring that were specific to that project are not carried over.

### Added

- **CLI** (`qsurface.py`) — `serve`, `validate`, `render`, `list`, `show`, `new`.
- **Question types** — `single`, `multi`, `rank` (drag to order), `scale`, `text`, `longtext`, `number`, `date`, plus non-collecting `info` blocks.
- **Per-question affordances** — a `why` line stating what the answer unblocks, a `recommend` value that marks an option and records whether it was followed, a "Don't know — flag for research" toggle, and a notes box. All on by default except `recommend`.
- **Conditionals** (`show_if`) with `equals` / `not_equals` / `includes` / `any_of` / `answered`, evaluated identically in the browser and on the server.
- **Draft persistence** — `localStorage` on every keystroke plus a debounced server-side `draft.json`. Survives tab close, browser crash, and server restart; deleted on submit.
- **Dual output** — an authoritative JSON record and a regenerable markdown render, both written to `responses/<id>/`.
- **Strict spec validation** — duplicate ids, forward-referencing conditionals, recommendations naming non-existent options, and out-of-range scales all fail at load rather than in front of the respondent.
- **Governance** — the `question-surface` skill and a section in `CLAUDE.md`: five or more questions go through this surface.
- 37 tests.

### Changed from the internal version

- **An untouched rank list is an answer, not a blank.** A rank question renders a complete ordering the moment it appears, so requiring a drag before it counted made a respondent who agreed with the presented order prove it. The presented order is now recorded, with `reordered: false` distinguishing acceptance from an arranged ranking, and the markdown notes it.
- **Hiding a branch clears its controls, not just its stored value.** A radio left visibly checked on a re-shown branch reported as blank on submit. The server-side twin is fixed too: a skipped question no longer carries notes, resolved labels, or a verdict on a recommendation it was never shown.
- **The form no longer asks who is answering.** A loopback single-user tool already knows; the respondent is taken from the git identity, falling back to the OS user, and shown read-only.
- `serve()` releases its socket on exit rather than holding the port for the life of the process.

### Notes

- Standard library only, by design. No npm, no pip, no build step — a tool that rots because its dependencies moved is not durable.
- Binds to `127.0.0.1` only. There is no auth and no session model, and there must never be a reason to expose it.
