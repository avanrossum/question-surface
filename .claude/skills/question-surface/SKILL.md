---
name: question-surface
description: Collect answers to five or more questions at once using the local Question Surface web form instead of asking them serially in chat. Use whenever a task needs a batch of decisions, requirements, or clarifications from the user — architecture forks, scoping, discovery, requirements gathering, keep-vs-drop inventories, or any point where you are about to write a numbered list of questions into a chat message. Covers authoring the questionnaire spec, serving it, and consuming the answers. Mandatory at five questions or more.
---

# Question Surface — batch question collection

**Five or more questions go through the Question Surface. Four or fewer may be asked in chat.**

The tool lives at the root of this repo. Its README is the format reference; this skill is the workflow and the judgement about when and how to use it.

## Why the gate exists

A long question set asked serially in chat degrades in a specific, repeatable way. Each answer arrives without the others in view, so the respondent cannot see the tradeoffs between them. Later questions get shorter answers than early ones. The answers end up scattered across a transcript nobody re-reads, and the next session re-derives half of them. Conditional questions are the worst case — asking "and if you picked the custom model, then…" three messages later has lost the context that made the question meaningful.

Collecting them at once fixes all of that, and produces a durable artifact in the bargain.

## When it applies

**Use it for:** architecture forks with dependent sub-questions · scoping and requirements gathering · discovery on a legacy surface · keep-vs-drop inventories · anything where you were about to write a numbered list of questions into chat.

**Don't use it for:** a single blocking question · a quick yes/no · anything where you should just make the routine call yourself and say so. The gate is a floor on batching, not a licence to manufacture questions. Five questions that should have been one decision you were competent to make is worse than asking nothing.

## Workflow

1. **Draft the spec.** `./qsurface.py new <id> --title "..."`, then author it. Group questions into sections by decision area. Order matters: a `show_if` may only reference an earlier question.

2. **Fill in `why` on every question.** This is the part that makes the difference. State what the answer unblocks and what breaks if it goes the other way. A question without a `why` gets a worse answer.

3. **Recommend where you have a view.** Set `recommend` to the option you would pick, and put the tradeoff in each option's `detail`. The respondent is a decision-maker, not a requirements oracle — a recommendation to react to is faster than a blank fork, and the response records whether the recommendation was followed. Do not recommend when you genuinely have no basis; a fake recommendation is worse than none.

4. **Validate.** `./qsurface.py validate <id>` — catches duplicate ids, forward-referencing conditionals, and recommendations naming options that don't exist.

5. **Serve it, and tell the user the URL.** `./qsurface.py serve <id>` blocks until submission. Run it in the background so the session stays responsive, and say plainly that you are waiting on it.

6. **Read the answers back.** `./qsurface.py show <id>` for the summary and paths; read the JSON for the detail.

7. **Act on `flagged_unknown` separately.** Those are not decisions the respondent declined to make — they are research items the questionnaire generated. Turn them into tracked work items rather than re-asking them.

## Authoring quality bar

- **Ask the real fork, not its symptom.** A question the project's existing governance already answers is a wasted slot. Ask what is genuinely open.
- **Put the cost in `detail`.** Each option states what choosing it commits us to. An option list without consequences is a preference poll.
- **Use `info` blocks to brief, not longer prompts.** A prompt that needs three sentences of setup wants an `info` block above it.
- **Use conditionals rather than "if applicable".** A question that only matters down one branch should not be visible down the other.
- **Prefer `single`/`multi` over `longtext` where the option space is known.** Free text is for things you genuinely cannot enumerate. A questionnaire of twelve textareas is a homework assignment.
- **Keep one questionnaire to one decision area.** Two unrelated areas are two questionnaires; a 60-question omnibus gets abandoned halfway.

## Enforcement

Model-enforced. No hook can detect the failure mode, because the failure mode is writing questions into a chat message rather than calling a tool. The backstop is noticing the shape of what you are about to write: **a numbered list of questions in a chat message is the violation.** If you catch yourself composing one, stop and author a questionnaire instead.

Responses are committed to git as part of the task that generated them.
