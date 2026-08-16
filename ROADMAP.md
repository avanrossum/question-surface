# Roadmap

Things deliberately not in the current release, with the reason. Decisions here came from the `ship-design` questionnaire and the `readme-shape` interview, both tracked under `.question-surface/responses/`, unless noted.

## Shipped since this file was written

**Interview mode** (v1.3.0). One question at a time, each written after reading the last answer, conducted as an expert interviewer in a stated or inferred domain. It brought the persistent-server model with it, as predicted: `interview open` leaves a detached server, `ask` blocks for one answer, `close` finalises. The transcript is written after every answer, so an interrupted interview still leaves a record.

**The interview → questionnaire handoff** (v1.4.0). `qsurface interview distill` scaffolds a questionnaire from a finished transcript, each exchange carried across as a marked draft, with `follows` pointing back at the interview. Raised in the `readme-shape` interview: *"the raw question surface is also important for clarifying — ESPECIALLY AFTER AN INTERVIEW."*

Still open from those designs:

- **Richer question types mid-interview.** Today an interview question is free text plus optional suggested chips. A scale or a ranking mid-conversation would sometimes be the right instrument.
- **Resuming a closed interview.** A follow-up session that carries the previous transcript, the way `follows` works for questionnaires.
- **Dictation on questionnaire `longtext` fields.** The nudge exists in interview mode; the same hint would help on long-form form fields.

## Sharpening distill

The first live run showed the command's unit is wrong. It emits one draft question per exchange, but an exchange is not a decision — an answer holds zero, one, or several. In a real retro of four exchanges, two produced empty drafts (pure history, and "nothing that stands out"), one held a decision already made, and one contained three separate forks compressed into a single slot.

What holds up is the material handling: the `info` blocks carrying each exchange, and the `follows` wiring that puts the conversation above the questions. What does not is the 1:1 draft.

Likely shape: the agent reads the transcript anyway, so let it pass the decisions it found — `--decision "..."`, repeatable, or a small JSON file — and have `distill` do what it is good at, which is preserving the material and wiring the spec. The current behaviour stays as the default for when the agent wants a starting point rather than a blank page.

## From the build retro

Both of these came out of the `build-retro` interview, and both came out of the *waiting* between questions rather than from being asked what to build.

### Team retros

A lead sends the same two or three opening questions to each member of a team, each interview forks from there on its own thread, and the answers are synthesized at the end.

This is the first thing that does not fit the current model. Everything today assumes one session, one respondent, one transcript — one detached server per interview, keyed by a session file in the project. Several people answering in parallel needs a different shape for identity, for storage, and for who is allowed to see whose answers. Worth designing properly rather than growing into.

### Voice mode

Conducting an interview spoken rather than typed: text-to-speech for the question, and a local alternative to Whisper for the answer.

Notable as the only thing so far that could justify revisiting the standard-library-only rule. The current dictation nudge points at the operating system's own dictation precisely because it needs no dependency, and that is a workaround rather than the feature. A genuinely spoken interview needs real components, and the constraint should be broken deliberately and visibly if it is broken at all — probably as an optional extra rather than in the core.

## Considered and deferred

### MCP server

Expose the tool over MCP so clients that cannot shell out can call it as a typed tool. Deferred: the CLI already reaches every runtime that can run a command, which is most of them, and a second interface is a second thing to version. Revisit once the CLI has been in real use and it is clear which clients are actually shut out.

### A JavaScript test runner

The client-side checks currently drive headless Chrome from `scripts/check_browser.py`, chosen over Jest to avoid npm and a build step. The known weakness is coverage discipline: it is easy to forget to add a check, and there is no coverage report to notice. If that proves insufficient in practice, add Jest as a deliberate exception for the browser suite only — the no-dependency constraint applies to the shipped tool, not necessarily to its development harness.

### A plugin manifest for Claude Code

`install.sh` covers Claude Code and every other runtime today. A plugin would lower install friction for Claude Code users specifically, at the cost of a second install path to keep working. Worth doing if other people start installing this.

## Open questions

### The name says little to someone who has not used it

Raised when the name was confirmed: "unless you know what it is, you don't really know what it is by the name alone." The name was kept because it is accurate and the alternatives traded description for evocation. If the README's opening line is doing the work the name cannot, that is an acceptable split — but worth revisiting if the tool is ever pitched somewhere the README is not.

## Not planned

- **Streaming the agent's reasoning into the page.** Settled in the `build-retro` interview and no longer an open question. Nothing streams today because `ask` blocks until the whole question is composed, which was an accident of implementation — but the correct one. Watching a question form makes a respondent start composing against a version of it that has not finished being asked. Worse, the silence is doing work of its own: a moment to reconsider what was just said, notice what was left out, and decide where to take it next. A "thinking out loud" feed would remove that, and it is not a cost the design tolerates — it is something the design provides.
- **An interface of its own.** No Electron, no SPA, no desktop app. Launching a browser at a local page is the whole design and it works.
- **Anything reachable off the machine.** Loopback only, no auth, no session model, no multi-tenancy. There must never be a reason to expose it.
- **Runtime dependencies.** Standard library only. The tool has to still run in a year without anyone maintaining a lockfile.
