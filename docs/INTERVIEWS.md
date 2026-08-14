# Interviews

One question at a time, with the agent deciding each one from the last answer.

A form is right when the agent already knows every question. An interview is for when it does not, and should not — drawing material out for something you are writing, working through an architecture problem, or thinking through anything where you are the source.

---

## Running one

```bash
qsurface interview open <id> --title "..." --domain "systems design"
qsurface interview ask <id> --prompt "..." --why "..."
qsurface interview ask <id> --prompt "..."      # written from the last answer
qsurface interview close <id> --summary "..."
qsurface interview list                          # what is open
```

`open` starts a detached server and returns immediately, so the agent keeps working. `ask` pushes one question, blocks until you answer, and prints the answer as JSON. `close` writes the final transcript and shuts the server down.

| `ask` flag | Effect |
|---|---|
| `--prompt` | The question. Required. |
| `--why` | What the agent is digging for, shown under the question. |
| `--placeholder` | Placeholder text in the answer box. |
| `--option` | A suggested answer, offered as a chip. Repeatable. |
| `--timeout MINUTES` | How long to wait. Defaults to the `timeout_minutes` setting. |
| `--text` | Print the answer text only, rather than JSON. |

A non-zero exit from `ask` means the timeout passed or the session was closed. That is "still waiting", not "declined" — the answer box keeps its draft either way.

---

## Conducting one well

This is what the skill instructs an agent to do, and it is the difference between an interview and a form asked slowly.

**Adopt a domain.** Conduct it as an expert interviewer in a specific field. If the domain is not stated, infer it from what is being produced: a post about an outage is a technical-writing interview, a session on a data model is a systems-design one. `--domain` states the stance and records it in the transcript.

- **Follow the thread that opened.** If an answer contains something more interesting than the next planned question, ask about that instead.
- **Ask for the concrete when handed the abstract.** "It was slow" earns "slow doing what, and who noticed?" Specifics are the whole reason to interview someone.
- **Ask about contradictions**, without being adversarial. Two answers that cannot both be true is the most valuable thing an interview surfaces.
- **One question at a time.** Three questions stacked into one prompt is a form with extra steps.
- **Say what you are digging for** in `--why`. It changes how much someone gives you.
- **Stop when you have what you need**, not when a count runs out.

---

## What the respondent sees

The page holds four states and shows exactly one.

**Asking** — the current question, its `why`, any suggested chips, a large answer box, Skip, and Send. `⌘`/`Ctrl`+`Enter` sends. Everything answered so far stays visible above as a running transcript, so the conversation has context rather than being one box in isolation.

**Waiting** — a caret working down a margin rule, lighting each line as it passes. What it says depends on why it is waiting: "Getting the first question ready" on load, "Waiting for the next question" after a reload, and "Reading your answer" once you have sent one. After 22 seconds the secondary line acknowledges a long wait.

**Done** — the wrap-up, with the agent's closing summary if it gave one.

**Lost contact** — shown after repeated failures to reach the server. An agent that dies must not leave someone watching an animation that will never end, so the page says so and confirms the answers already sent are saved.

### Dictation

Speaking an answer suits an interview better than typing one, so the page points at the dictation already built into the operating system: the microphone key or `Fn` twice on macOS, `Win`+`H` on Windows. It is dismissible and remembered.

Deliberately not the Web Speech API, which in Chrome sends audio to a recognition service — that would break the loopback-only constraint the tool is built on. Whisper would be a large dependency for a tool that has none.

---

## The transcript

Written after **every** answer, not only at close, so an interview interrupted halfway still leaves everything said so far. It lands beside questionnaire responses in `.question-surface/responses/<id>/`.

```json
{
  "interview_id": "readme-shape",
  "kind": "interview",
  "domain": "developer documentation and positioning",
  "respondent": "Alex",
  "started_at": "2026-08-14T20:54:02Z",
  "ended_at": "2026-08-14T21:20:11Z",
  "counts": { "asked": 7, "answered": 7, "skipped": 0 },
  "exchanges": [
    {
      "seq": 1,
      "prompt": "Picture one specific person landing on this repo…",
      "why": "Everything downstream depends on this.",
      "answer": "…",
      "asked_at": "2026-08-14T20:54:09Z",
      "answered_at": "2026-08-14T21:00:55Z",
      "skipped": false
    }
  ]
}
```

The questions are kept as well as the answers, because they were generated rather than authored — a transcript holding only the answers is unreadable.

`qsurface show <id>` summarizes it and marks a transcript that is still in progress.

---

## Housekeeping

Session state lives in `.question-surface/interviews/` and is not tracked. A server that loses its agent shuts down after four idle hours rather than holding a port forever, and `qsurface doctor` reports any session record left pointing at nothing.

Always `close`. Nothing is lost if you do not, but an unclosed session leaves a server running until it goes idle.
