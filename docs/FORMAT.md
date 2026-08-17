# Questionnaire format

The complete reference. `questionnaires/example.json` ships with the tool, exercises every feature, and is the fastest way to see all of this at once:

```bash
docket render example -o /tmp/preview.html
```

---

## The document

```json
{
  "id": "session-storage",
  "title": "Session storage — architecture decisions",
  "intro": "What this questionnaire decides and what it unblocks.",
  "context_docs": ["docs/DISCOVERY.md", "ADR-014"],
  "spec_version": 1,
  "follows": "an-earlier-questionnaire-id",
  "sections": [
    {
      "title": "Storage model",
      "intro": "Optional section preamble.",
      "questions": []
    }
  ]
}
```

| Field | Required | Purpose |
|---|---|---|
| `id` | yes | Matches the filename. Names the response directory. |
| `title` | yes | Heading and browser title. |
| `sections` | yes | At least one, each with a `title` and a non-empty `questions` list. |
| `intro` | no | Shown under the title. State what is being decided and what is *not* being reopened. |
| `context_docs` | no | Listed in the sidebar so the respondent knows what this came out of. |
| `spec_version` | no | Defaults to `1`. A spec declaring a version newer than the installed tool is refused rather than half-read. |
| `follows` | no | An earlier questionnaire id. Renders a read-only panel of what that round settled. |

---

## Question types

| Type | Collects | Notes |
|---|---|---|
| `single` | one option value | radio group; needs ≥2 options |
| `multi` | list of option values | checkboxes |
| `rank` | ordered list of values | drag to reorder |
| `scale` | integer | `min`/`max` (≤10 steps), `min_label`/`max_label` |
| `text` | string | one line |
| `longtext` | string | textarea |
| `number` | number | |
| `date` | ISO date | |
| `info` | nothing | a context block, not a question |

### Fields on every question

| Field | Default | Purpose |
|---|---|---|
| `id` | — | required, unique, alphanumeric plus `-`/`_` |
| `prompt` | — | required, the question itself |
| `why` | `""` | **Fill this in.** What the answer unblocks, and what breaks if it goes the other way. A question without a `why` gets a worse answer. |
| `required` | `false` | Blocks submit unless answered or flagged unknown. |
| `recommend` | `null` | Marks an option `recommended`. The response records whether it was followed. |
| `allow_unknown` | `true` | Renders "Don't know — flag for research". |
| `notes` | `true` | Renders a free-text notes box. |
| `show_if` | — | Conditional display. |
| `placeholder` | `""` | Scalar inputs only. |

`options` accepts a bare string (value and label the same) or `{value, label, detail}`. **`detail` is where the cost of choosing that option goes.** An option list without consequences is a preference poll.

---

## Conditionals

```json
"show_if": { "question": "backing-store", "equals": "redis" }
```

Exactly one operator per condition:

| Operator | True when |
|---|---|
| `equals` | the answer equals this value |
| `not_equals` | the answer does not equal this value |
| `includes` | a multi-select answer contains this value |
| `any_of` | the answer is one of this list (or a multi-select intersects it) |
| `answered` | `true` — the question has an answer; `false` — it does not |

The referenced question **must appear earlier in the document**. Validation rejects forward references, which is what keeps a single evaluation pass correct.

**An unanswered question satisfies `not_equals` and `answered: false`.** A branch hanging off `not_equals` is therefore visible before its parent is answered — usually what you want for "show unless they pick X", and a trap if you meant "show once they have picked something other than X". Pair it with `answered` on the parent when the distinction matters.

Conditionals are evaluated identically in the browser and on the server. A question whose branch was never taken is recorded as `skipped`, not unanswered. A branch hanging off a hidden question is itself hidden, and a stale draft cannot smuggle an answer into one.

---

## Inline formatting

`prompt`, `why`, `intro`, and `detail` support `` `code` ``, `**bold**`, and `*italic*`. Everything is HTML-escaped before formatting is applied, so a questionnaire can never inject markup into the page.

---

## The response document

```json
{
  "questionnaire_id": "session-storage",
  "title": "Session storage — architecture decisions",
  "respondent": "Alex",
  "submitted_at": "2026-08-14T19:07:00Z",
  "counts": { "total": 4, "answered": 3, "unknown": 1, "unanswered": 0, "skipped": 1 },
  "flagged_unknown": ["confidence"],
  "unanswered": [],
  "skipped": ["eviction"],
  "answers": {
    "backing-store": {
      "prompt": "What backs the session store?",
      "type": "single",
      "value": "postgres",
      "labels": ["The existing Postgres"],
      "unknown": false,
      "notes": "one less service to run on-call for",
      "recommended": "redis",
      "followed_recommendation": false
    }
  }
}
```

- `counts.total` counts only questions the respondent could actually reach.
- `flagged_unknown` is the work item the questionnaire generated. Research those; do not re-ask them.
- `labels` resolves option values to their human labels so a reader does not need the spec.
- `reordered` appears on `rank` answers. `false` means the respondent accepted the order as presented rather than arranging it — a weaker signal, but an answer.
- A `skipped` entry carries no value, notes, labels, or recommendation verdict. It was never asked.

Read it with `docket show <id>`, or `docket show <id> --path-only` for just the JSON path.

---

## Authoring quality bar

- **Ask the real fork, not its symptom.** A question your existing conventions already answer is a wasted slot.
- **Put the cost in `detail`.** State what choosing each option commits you to.
- **Use `info` blocks to brief.** A prompt needing three sentences of setup wants an `info` block above it.
- **Use conditionals rather than "if applicable".**
- **Prefer `single`/`multi` over `longtext` where the option space is known.** A questionnaire of twelve textareas is a homework assignment.
- **One questionnaire, one decision area.** A 60-question omnibus gets abandoned halfway.
- **Say what is already decided** in the `intro`, so the respondent knows what is not being reopened.
