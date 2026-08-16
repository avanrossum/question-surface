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
| `--option` | A selectable answer, offered as a chip. Repeatable. Recorded separately from the typed answer, so a selection survives the sentence being edited. |
| `--context` | Reasoning behind the question, shown in a collapsed block. Paragraphs, `-` bullets, pipe tables, and inline formatting. |
| `--context-file` | Read the context from a file, for anything long. |
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

## Handing off to a form, in the same tab

When an interview ends with things that have become precise enough to decide, the form for them opens where the interview already is. Nobody goes hunting for a second URL, and nobody gets a questionnaire they did not agree to.

```bash
qsurface interview hold <id>                                  # questions over, hold the page
# ...distill, author the follow-up, validate it...
qsurface interview offer <id> --questionnaire <qid> \
    --message "Three things worth pinning down."              # blocks for the outcome
```

`hold` switches the page to "That's the last question — hold on a moment" while the agent reads the conversation back. Without it the page still says "reading your answer", which stops being true once there are no more questions.

`offer` presents the questionnaire by name and count with two buttons. Taking it loads the form into the same tab; declining shows the usual close-this-tab message. Either way `offer` blocks until the respondent decides, then prints the outcome:

| Outcome | Meaning |
|---|---|
| `taken` | The form was answered. Prints the counts and both response paths. |
| `declined` | No follow-up. The transcript stands. |
| exit 1 | Nobody answered the offer before the timeout. |

The transcript records what happened in a `followup` block — offered, taken, and where the answers went — so the interview and the response beside it are not two unrelated files.

If there is nothing worth asking, skip both and `close` as usual.

## Turning an interview into a questionnaire

```bash
qsurface interview distill <interview-id> [--out <id>] [--only 2,4,5] [--force]
```

An interview ends with material that has become precise enough to decide. `distill` writes a questionnaire scaffold from the transcript rather than making the agent retype it:

- Each selected exchange becomes an `info` block holding what was asked and what was said, followed by a draft question marked `TODO`.
- The spec declares `follows: <interview-id>`, so serving it renders the interview above the questions.
- `--only` selects exchange numbers; the default is every answered one.

**Every question it writes is a draft.** The tool cannot tell which parts of a conversation became decisions, so it carries all of them across and marks them rather than guessing. The agent rewrites what is a real fork, deletes what is settled, and adds the options and their costs before serving it.

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
      "selected": ["Reliability"],
      "context": "…as passed to --context, unrendered",
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
