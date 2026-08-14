# Roadmap

Things deliberately not in the current release, with the reason. Decisions here came from the `ship-design` questionnaire (`.question-surface/responses/ship-design/`) unless noted.

## Next: interview mode

A second presentation for a different shape of conversation. The batch form is right when the agent already knows every question. It is wrong when each answer should determine the next one.

> "I'd like to write a post about X. Please interview me for this, so I capture real scenarios and communicate the point properly."

Also used for architecture and systems design, and for thinking through a complex problem out loud.

### The interaction

One question on screen at a time. The respondent answers, the page shows a processing state while the agent reads that answer and decides what to ask next, then the next question arrives. Repeat until the agent is satisfied it has what it needs, not until a fixed list is exhausted.

```
user asks for an interview
  → agent opens the surface and asks its first question
  → user answers
  → page shows a processing state
  → agent reads the answer, writes the next question
  → repeat until the agent has enough
  → transcript written as a response document
```

### Governance

The agent conducts the interview **as an expert interviewer in a specific domain**, and where the domain is not stated, infers it from context. This is the part that separates a useful interview from a form asked slowly. An expert interviewer follows the interesting thread, asks for the concrete example when given an abstraction, and notices when an answer contradicts an earlier one. A generic agent asks the next question on its list.

The skill should also say when to stop: when further questions would produce material the user has already covered, not when a counter runs out.

### What it needs that does not exist yet

This is the reason it is a roadmap item rather than a patch. The batch flow works because `serve` blocks once and exits on submit. An interview needs the server alive across many turns, with the agent in the loop between each one — which is the persistent-server model deliberately deferred in `ship-design`, and it comes back here on its own merits.

Sketch:

```bash
qsurface interview open <id>            # starts the server, returns immediately
qsurface interview ask <id> -q q.json   # pushes one question, blocks for the answer, prints it
qsurface interview close <id>           # wrap-up screen, writes the transcript, shuts down
```

The page holds a long-poll or SSE connection so a pushed question appears without a reload, and shows the processing state whenever no question is pending. That state is a real design surface — it is where the respondent spends every gap in the conversation, and a dead-looking page reads as a hang. It also needs an honest failure mode: if the agent dies mid-interview, the page must say so rather than animating forever.

The transcript is the response document, in interview order, with the questions that were actually asked. Because those questions were generated rather than authored, the record has to keep them — a transcript that only stores the answers is unreadable.

### Voice

Wanted as a value-add, not a requirement. Speaking an answer suits an interview far better than typing one.

Not the Web Speech API: in Chrome it ships audio to Google's servers for recognition, which breaks the loopback-only constraint the whole tool is built on. Not Whisper either — that is a dependency, and a large one.

The workable version is a nudge to the dictation already built into the operating system, which runs locally and costs nothing: detect the platform from the user agent and show the shortcut on a focused text field (macOS presses the microphone key or Fn twice; Windows is Win+H). Most people have it and do not know it is there. This could land on `longtext` fields before interview mode exists.

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
