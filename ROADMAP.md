# Roadmap

Things deliberately not in the current release, with the reason. Decisions here came from the `ship-design` questionnaire (`.question-surface/responses/ship-design/`) unless noted.

## Shipped since this file was written

**Interview mode** (v1.3.0). One question at a time, each written after reading the last answer, conducted as an expert interviewer in a stated or inferred domain. It brought the persistent-server model with it, as predicted: `interview open` leaves a detached server, `ask` blocks for one answer, `close` finalises. The transcript is written after every answer, so an interrupted interview still leaves a record.

Still open from that design:

- **Richer question types mid-interview.** Today an interview question is free text plus optional suggested chips. A scale or a ranking mid-conversation would sometimes be the right instrument.
- **Resuming a closed interview.** A follow-up session that carries the previous transcript, the way `follows` works for questionnaires.
- **The waiting state.** The current processing animation is a plain three-dot pulse. It is the screen the respondent sees in every gap, and it deserves a designed treatment.
- **Dictation on questionnaire `longtext` fields.** The nudge exists in interview mode; the same hint would help on long-form form fields.

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

- **An interface of its own.** No Electron, no SPA, no desktop app. Launching a browser at a local page is the whole design and it works.
- **Anything reachable off the machine.** Loopback only, no auth, no session model, no multi-tenancy. There must never be a reason to expose it.
- **Runtime dependencies.** Standard library only. The tool has to still run in a year without anyone maintaining a lockfile.
