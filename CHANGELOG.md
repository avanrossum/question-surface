# Changelog — Docket

Semver. Newest first. The tool carries its own version because questionnaires authored against one spec format have to keep working against later ones.

---

## 2.0.0 — 2026-08-17

**Question Surface is now Docket.** A docket is a list of matters awaiting decision and the record of how each was disposed of, which is what the tool hands you. The old name described the input widget at the moment agent harnesses began absorbing input widgets as built-ins; the committed decision record is the part worth naming. Reasoning in `~/Developer/The_CEO/consultations/question-surface/`.

Done before the first external install, which is the only ordering in which a rename is free rather than a migration.

### Breaking

- **The project state directory is `.docket/`**, not `.question-surface/`. Any project already holding one should `git mv` it; the tool reads only the new name.
- **The command is `docket`.** `qsurface` is gone rather than aliased. `./install.sh` removes a pre-2.0 `qsurface` symlink and skill rather than leaving them orphaned on PATH.
- **The Python package is `docket/`** and the entry point is `docket.py`. As before, the script and the package share a name and the package wins any plain import, which is why the `distill` tests drive the CLI as a subprocess.
- **The skill is `docket`**, and config lives in `$XDG_CONFIG_HOME/docket/`.
- The repository is `github.com/avanrossum/docket`. GitHub redirects the old URL permanently, so existing remotes keep working.

### Changed

- **The tagline is locked to the name** and appears identically in the repo description, the skill description, the README's opening line, and the install banner: *Docket collects your coding agent's open questions into one page you clear in a sitting, and keeps the answers as a record you can commit next to the code they decided.*
- The README's naming section says what a docket is instead of joking that the name explains nothing, which was the problem being fixed.
- `ROADMAP.md` closes the naming question it opened on 2026-08-14.

### Not changed

- **The tracked decision records keep the words they were written with.** The transcripts under `.docket/` still discuss a tool called Question Surface, because that is what it was called when they were recorded. A record edited to match the present is not a record. The same applies to the changelog entries below this one.
- Every v1 tag stays where it is.

## 1.5.0 — 2026-08-16

### Added

- **The interview hands off to a form in the same tab.** `qsurface interview hold` tells the page the questions are over while the agent reads the conversation back, and `qsurface interview offer --questionnaire <id>` presents a follow-up by name and count with two buttons. Taking it loads the form into the tab the interview is already in; declining shows the usual close-this-tab message. `offer` blocks until the respondent decides and prints the outcome with the response paths.
- **The transcript records the handoff** in a `followup` block — offered, taken, and where the answers went — so an interview and the response beside it are not two unrelated files.
- **A wrap-up waiting state**: "That's the last question — hold on a moment." The page previously still said it was reading an answer once there were no more questions to ask.

### Fixed

- **`write_transcript` dropped fields it was not told about.** It builds its document from a fixed key list, so `followup` was set on the record and silently never written. Caught by checking the artifact rather than the return value.

### Notes

- The offer is an offer. A questionnaire nobody agreed to is the manufactured-questions failure the gate exists to prevent, so the skill says to hand off only when the interview produced forks rather than observations.
- Test helper threads now surface what they raise. A missing import in a respondent thread killed it silently and presented in the main thread as an unexplained timeout, which is a slow way to find a typo. 117 Python tests, 49 client-side checks.

## 1.4.2 — 2026-08-16

### Fixed

- **`distill --out` accepted a path and escaped the questionnaires directory.** Joining an absolute path discards the base, so `--out /tmp/x` wrote the spec to `/tmp/x.json` with an `id` that would never have validated. It is an id now, checked like every other id. Found by running the command with a scratch path during the first live distill.

### Notes

- The first live distill also showed where the command is weak, recorded in the roadmap: it emits one draft per exchange, but an answer contains zero, one, or several decidable things. Two of four drafts from a real retro were empty and one held three separate forks.

## 1.4.1 — 2026-08-16

### Added

- **Tests for `interview distill`**, which shipped in 1.4.0 verified only by hand. Thirteen of them, driven through the CLI and shaped from a real transcript: the spec validates, follows its interview, carries the material across, marks every question as a draft, honours `--only`, and refuses to overwrite, to distill a missing interview, or to distill a questionnaire response. 107 Python tests.
- **A design principle, written down** — a turn arrives whole, and the agent's reasoning never streams into the page. Recorded in `docs/DESIGN.md` and as a non-goal in the roadmap.
- **Two roadmap entries from the `build-retro` interview**: team retros (several respondents answering the same opening questions, forking individually, synthesized at the end) and voice mode (the only candidate so far for deliberately breaking the standard-library-only rule).

### Notes

- The no-streaming behaviour was an accident of `ask` blocking until a question is composed. It is now a decision: watching a question form makes a respondent answer a version of it that has not finished being asked, and the silence between turns is where they reconsider what they just said. The waiting state is not dead time being decorated.

## 1.4.0 — 2026-08-14

### Added

- **`qsurface interview distill`** — scaffolds a questionnaire from a finished interview transcript. Each answered exchange becomes an `info` block holding what was asked and what was said, followed by a draft question marked `TODO`, and the spec declares `follows: <interview-id>` so serving it renders the interview above the questions. `--only` selects exchanges. The tool cannot tell which parts of a conversation became decisions, so it carries all of them across and marks them rather than guessing.
- **Interview options are a selection, not text.** `--option` chips now toggle and are recorded in `selected` alongside the typed answer, rather than pasting their label into the answer box where the choice is lost the moment the sentence around it is edited. A selection alone counts as an answer.
- **`--context` and `--context-file` on `interview ask`** — reasoning behind a question, shown in a block clamped to about four lines with a "Read more" toggle. Renders a small markdown subset: paragraphs, bullets, pipe tables, and inline formatting, all escaped before any markup is applied.
- **`follows` understands an interview transcript**, so a distilled questionnaire shows the conversation it came from.

### Fixed

- **A closing summary could appear once per answer.** `send()` started a second poll loop while the first was still running, so every answer forked another, and each fork called `finish()` when the interview closed. One loop is now enforced, `finish()` is idempotent, and a check asserts the summary appears exactly once.
- **The "Read more" toggle never appeared.** Whether the context overflows was measured while the card was still `display:none`, where both heights read zero and the content always looks like it fits.
- **The context clamp did nothing.** It used `-webkit-line-clamp`, which only counts inline text and is inert once the block holds a table or a list — which is most of the time, since that is what the block is for. Clamped by height instead, with a fade.
- **`render.rich` could hang on a pipe row with no divider under it**, which matched no block rule and left the cursor unmoved. Found by the test written for it.

### Notes

- Two of the new checks replaced ones that were passing without proving anything: the context clamp was asserted by class name rather than by measuring, and the summary count included a static paragraph. 94 Python tests, 41 client-side checks.

## 1.3.2 — 2026-08-14

### Fixed

- **The waiting state no longer claims to be reading an answer that does not exist.** The interview page enters that state on load, before anything has been said. It now says what is actually true, with three variants chosen by why it was entered: getting the first question ready, waiting for the next one after a reload, or reading the answer just sent. Three checks assert the copy matches the reason.

### Changed

- **The README was rewritten from an interview conducted with the tool** (`.question-surface/responses/readme-shape/`). It opens with the request that started the project, leads with what both modes have in common rather than billing one above the other, and stops at 91 lines. The reference material it used to carry moved into `docs/USAGE.md`, `docs/INTERVIEWS.md`, and `docs/DESIGN.md`, which are linked prominently rather than buried.

### Added

- Roadmap entry for an interview → questionnaire handoff, which came out of that interview: an interview reliably ends with things that have become precise enough to decide, and turning those into a questionnaire is manual today.

## 1.3.1 — 2026-08-14

### Changed

- **The interview processing state is now a designed treatment.** A caret works down a margin rule, lighting each line as it passes — the shape of someone reading a page they intend to respond to, rather than a spinner. After 22 seconds the secondary line changes to acknowledge a long wait, so a slow turn still shows movement. Built in Claude Design against this project's own tokens and imported wholesale; no libraries, no build step, and `prefers-reduced-motion` parks the mark with a slow breath instead.

### Added

- Four client-side checks covering the animation, and both interview screenshots are now produced by `scripts/make_screenshots.py` rather than by hand, so they cannot drift. 28 client-side checks.

### Notes

- CSS animations do not advance under Chrome's `--virtual-time-budget`, so the motion checks seek the animation directly through `getAnimations()` rather than sampling over time. Sampling appears to work and silently proves nothing.

## 1.3.0 — 2026-08-14

### Added

- **Interview mode.** `qsurface interview open|ask|close|list` runs a conversation instead of a form: one question at a time, each written by the agent after reading the previous answer. `open` leaves a detached server and returns, `ask` pushes one question and blocks for its answer, `close` finalises the transcript. The skill governs the conduct — expert interviewer in a stated or inferred domain, following the thread, asking for the concrete, stopping when it has what it needs rather than at a count.
- **Crash-safe transcripts.** The transcript pair is rewritten after every answer, not only at close, so an interview interrupted halfway still leaves everything said so far. `qsurface show` reads an interview transcript as well as a questionnaire response.
- **A dictation nudge** on interview answers, pointing at the operating system's own dictation (microphone key on macOS, `Win+H` on Windows). Deliberately not the Web Speech API, which sends audio to a recognition service and would break the loopback-only constraint.
- **Stale-session reporting** in `qsurface doctor`, since a dead agent can leave a session record pointing at nothing.

### Fixed

- **The interview client could busy-loop.** Its long-poll re-issued immediately on return, which is paced only by the server holding the connection for ~20s. Anything answering a poll immediately — a proxy, a shorter server timeout — would have spun the loop as fast as the event loop allowed. There is now a floor between polls regardless of what the server does. Found by the browser checks, which hung a headless Chrome outright.

### Notes

- The interview page holds four states and shows exactly one: asking, processing, done, and lost contact. The last exists because an agent that dies must not leave the respondent watching an animation forever; the page says so after repeated poll failures.

## 1.2.0 — 2026-08-14

### Added

- **Close-on-submit.** A checkbox in the submit bar, off by default, that closes the tab once the answers are recorded. The choice is remembered across questionnaires since it is a preference about how someone works. Browsers only permit a page to close a tab a script opened, so when the browser refuses, the success panel says so instead of leaving the respondent waiting for a tab that will never disappear.
- **MIT licence.**

### Fixed

- **A client-side check was passing for the wrong reason.** `submitted_with_blanks` claimed to prove that a blank required question blocks submission, but the harness had answered every required question by that point, so what it actually observed was the standalone preview panel appearing. Replaced with three checks that leave a required question blank on purpose and assert the submission is blocked, the offending question is marked, and the button stays ready to retry. 17 client-side checks, up from 12.

### Changed

- README screenshots are rendered as served rather than standalone, so they show what a respondent actually sees.

## 1.1.0 — 2026-08-14

Makes the tool installable and global: any agent that can run a shell command can now ask a batch of questions from any project. Shape decided by the `ship-design` and `naming` questionnaires, whose responses are tracked under `.question-surface/responses/`.

### Added

- **`install.sh`** — puts `qsurface` on PATH, symlinks the skill into `~/.claude/skills/`, and offers to add a gate pointer line to the global `CLAUDE.md`. Symlinks rather than copies, so `git pull` updates tool and skill together. `--uninstall` removes everything it added; `--yes` runs unattended.
- **Project-local state.** Questionnaires and responses now live in `<project>/.question-surface/`, found from the nearest enclosing repository, so a decision lands in the repo it is about. The bundled `example` questionnaire stays readable from anywhere. `QSURFACE_PROJECT` overrides the project root.
- **`--timeout MINUTES`** on `serve` (default 120, `0` waits forever). On timeout it writes no response and exits non-zero, leaving the draft intact — a partial record that reads like a decision is worse than none.
- **Per-user config** — `qsurface config gate <n>` and `timeout_minutes`, stored under `$XDG_CONFIG_HOME/question-surface/`.
- **`spec_version`** on questionnaires, defaulting to 1. A spec declaring a newer version than the tool understands is refused rather than half-read.
- **`follows`** on questionnaires — names an earlier questionnaire and renders a read-only panel of what it settled, so a follow-up round does not make the respondent reconstruct it.
- **`qsurface doctor`**, **`qsurface archive`**, **`qsurface show --open`**, and **`--version`**.
- **Client-side checks** — `scripts/check_browser.py` drives headless Chrome over the parts of `app.js` the Python suite cannot reach, and skips cleanly when no browser is installed. 12 checks.
- **CI** — the suite across Python 3.9–3.13, plus the client-side checks.
- 60 Python tests, up from 37.

### Changed

- **Port collision no longer fails.** `serve` falls back to a free port and prints which one, so two agents can ask questions at once.
- **The gate has two triggers.** Five or more questions as before, *and* any number whose answers would benefit from exposition, detailed answer choices, or open-ended interaction. Two hard forks belong on the surface; four easy questions do not.

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
