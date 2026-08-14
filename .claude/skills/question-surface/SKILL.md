---
name: question-surface
description: Collect answers from the user through a local web surface instead of asking serially in chat. Two modes. Batch form — whenever a task needs decisions, requirements, or clarifications: architecture forks, scoping, discovery, requirements gathering, keep-vs-drop inventories, or any point where you are about to write a numbered list of questions into a chat message; also for fewer questions when the answers would benefit from real exposition, detailed answer choices, or open-ended interaction; mandatory at the configured gate, default five. Interview mode — whenever the user asks to be interviewed, or when each answer should determine the next question: drawing out material for writing, working through an architecture or systems-design problem, or thinking through a complex problem out loud. Covers authoring, serving, conducting, and consuming the answers.
---

# Question Surface — batch question collection

**Two triggers, either one is sufficient:**

1. **Count.** The gate is five or more questions by default. It is a per-user setting — if the user's global `CLAUDE.md` states a different number, that number wins. `qsurface config gate` reports the current value.
2. **Shape.** Any number of questions whose answers would benefit from exposition, detailed answer choices, or open-ended interaction. Two genuinely hard forks with real tradeoffs belong here even though two is below the gate. A form where each option carries its consequence gets a better answer than the same question flattened into a chat paragraph.

Four easy questions stay in chat. Two hard ones do not.

## Why this exists

A long or dense question set asked serially in chat degrades in a specific, repeatable way. Each answer arrives without the others in view, so the user cannot see the tradeoffs between them. Later questions get shorter answers than early ones. The answers end up scattered across a transcript nobody re-reads, and the next session re-derives half of them. Conditional questions are the worst case — asking "and if you picked the custom model, then…" three messages later has lost the context that made the question meaningful.

Collecting them at once fixes all of that, and produces a durable artifact in the bargain.

## When not to use it

A single blocking question. A quick yes/no. Anything where you should make the routine call yourself and say so. The gate is a floor on batching, not a licence to manufacture questions — five questions that should have been one decision you were competent to make is worse than asking nothing.

## Workflow

1. **Draft the spec.** `qsurface new <id> --title "..."` writes to `.question-surface/questionnaires/` in the current project. Group questions into sections by decision area. Order matters: a `show_if` may only reference an earlier question.

2. **Fill in `why` on every question.** This is the part that makes the difference. State what the answer unblocks and what breaks if it goes the other way. A question without a `why` gets a worse answer.

3. **Recommend where you have a view.** Set `recommend` to the option you would pick, and put the tradeoff in each option's `detail`. The user is a decision-maker, not a requirements oracle — a recommendation to react to is faster than a blank fork, and the response records whether it was followed. Do not recommend when you genuinely have no basis; a fake recommendation is worse than none.

4. **Validate.** `qsurface validate <id>` — catches duplicate ids, forward-referencing conditionals, and recommendations naming options that don't exist.

5. **Serve it in the background and say so plainly.** `qsurface serve <id>` blocks until submission, so run it as a background command and tell the user the URL. Then **keep working on whatever is not blocked by the answers** — that is the point of not blocking the session. Say which parts you are proceeding with and which are waiting.

6. **Read the answers back.** `qsurface show <id>` for the summary and paths; read the JSON for the detail. The response document records, per question, the value, whether it was flagged unknown, free-text notes, and whether your recommendation was followed.

7. **Act on `flagged_unknown` separately.** Those are not decisions the user declined to make — they are research items the questionnaire generated. Do the research, or turn them into tracked work; do not simply re-ask them. If a flagged item needs a decision after you have researched it, that is a follow-up questionnaire, not a chat message.

## Authoring quality bar

- **Ask the real fork, not its symptom.** A question the project's existing governance already answers is a wasted slot.
- **Put the cost in `detail`.** Each option states what choosing it commits us to. An option list without consequences is a preference poll.
- **Use `info` blocks to brief, not longer prompts.** A prompt that needs three sentences of setup wants an `info` block above it.
- **Use conditionals rather than "if applicable".** A question that only matters down one branch should not be visible down the other.
- **Prefer `single`/`multi` over `longtext` where the option space is known.** Free text is for things you genuinely cannot enumerate. A questionnaire of twelve textareas is a homework assignment.
- **Keep one questionnaire to one decision area.** Two unrelated areas are two questionnaires; a 60-question omnibus gets abandoned halfway.
- **Say what is already decided.** Put it in the `intro` so the user knows what is not being reopened.

## Interview mode

**When the user asks to be interviewed, or when each answer should determine the next question, use interview mode instead of a form.** One question at a time, you read each answer before writing the next. Typical asks: "interview me for a post about X", working through an architecture problem out loud, or thinking through anything where the user is the source and you are drawing it out.

The batch form is for when you already know every question. An interview is for when you don't, and shouldn't.

### Conduct it as an expert interviewer

**Adopt the mindset of an expert interviewer in a specific domain.** If the user names the domain, use it. If they don't, infer it from what they are trying to produce — a post about an outage is a technical-writing interview; a session on a data model is a systems-design interview. Pass it with `--domain`, both to state your stance and to record it in the transcript.

What separates an interview from a form asked slowly:

- **Follow the thread that opened.** If an answer contains something more interesting than your next planned question, ask about that instead.
- **Ask for the concrete when you are given the abstract.** "It was slow" earns "slow doing what, and who noticed?" Specifics are the entire reason to interview someone.
- **Notice contradictions and ask about them**, without being adversarial. Two answers that cannot both be true is the most valuable thing an interview surfaces.
- **One question at a time.** Do not stack three questions into one prompt; that is a form with extra steps.
- **Use `--why` to say what you are digging for.** It changes how much the person gives you.
- **Stop when you have what you need**, not when a count runs out. Two more questions that produce material already covered is worse than stopping.

### Workflow

```bash
qsurface interview open <id> --title "..." --domain "systems design"
qsurface interview ask <id> --prompt "..." --why "..."     # blocks, prints the answer as JSON
qsurface interview ask <id> --prompt "..."                 # ...informed by the last answer
qsurface interview close <id> --summary "..."              # writes the transcript
```

`open` returns immediately, leaving a detached server. Each `ask` blocks until the answer comes back and prints it as JSON — `--text` prints just the answer text. `--option` adds suggested answers as chips the respondent can click to build on; repeat it for several.

**Always `close`.** The transcript is written after every answer, so nothing is lost if you don't, but an unclosed session leaves a server running until it goes idle. `qsurface interview list` shows what is open.

If `ask` exits non-zero, the user hasn't answered within the timeout or the session was closed. That means "still waiting", not "declined" — the answer box keeps their draft.

Read the finished transcript with `qsurface show <id>`, or read the JSON directly for the exchange list.

## Follow-up rounds

Set `"follows": "<earlier-questionnaire-id>"` in the spec and the form renders a read-only panel of what that round settled, so the user is not reconstructing it from memory. Use this for a second pass after research, rather than repeating questions with more context pasted into the prompts.

## Commands

```bash
qsurface list                      # questionnaires and response counts
qsurface new <id> --title "..."    # scaffold
qsurface validate <id>             # check a spec without serving it
qsurface serve <id>                # serve, block until submitted
qsurface serve <id> --timeout 30   # give up after 30 minutes; 0 waits forever
qsurface show <id>                 # summary and paths
qsurface show <id> --path-only     # just the latest JSON path
qsurface archive <id>              # retire a questionnaire, keep its responses
qsurface config gate 3             # change the gate for this user
qsurface doctor                    # check the install
```

`serve` exits non-zero if it times out with no submission. The draft is saved either way, so re-serving resumes where the user stopped — treat a timeout as "still waiting", not as "declined to answer".

## Where things land

Questionnaires and responses live in the project being worked on, under `.question-surface/`. Responses are records of decisions and are meant to be committed with the work they gate — the tool never stages them itself, so commit them as part of the task. The `example` questionnaire ships with the tool and is available from any project as the format reference.

## Enforcement

Model-enforced. No hook can detect the failure mode, because the failure mode is writing questions into a chat message rather than calling a tool. The backstop is noticing the shape of what you are about to write: **a numbered list of questions in a chat message is the violation.** If you catch yourself composing one, stop and author a questionnaire instead.
