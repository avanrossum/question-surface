# Question Surface

A local web form for collecting answers to a large set of questions in one pass.

Serialized question-and-answer in chat is the wrong shape for architecture work. A fork with eight dependent questions becomes eight round trips, each one carrying less context than the last, and the answers end up scattered across a transcript that nobody re-reads. The Question Surface collects the whole set at once, in a form built for the questions being asked, and writes the answers to disk where an agent reads them directly.

Nothing in it is domain-specific. It is a spec format, a renderer, and a loopback server.

---

## Governance

**Five or more questions go through this surface. Four or fewer can be asked in chat.** This is a gate, not a suggestion — see the `question-surface` skill in `.claude/skills/` and the Question Surface section of `CLAUDE.md`.

---

## Usage

```bash
./qsurface.py list                        # questionnaires + response counts
./qsurface.py new my-topic --title "..."  # scaffold a new questionnaire
./qsurface.py validate my-topic           # check a spec without serving it
./qsurface.py serve my-topic              # open the form, block until submitted
./qsurface.py show my-topic               # summarize the latest response
./qsurface.py render my-topic -o out.html # standalone preview, no server
```

`serve` binds to `127.0.0.1`, opens a browser, and exits once the form is submitted, printing the paths it wrote. Add `--stay-open` to keep serving for multiple respondents, `--no-open` to suppress the browser, `--port` to move off 8777.

**Answers are never lost.** Every keystroke persists to `localStorage`, and a debounced save writes `responses/<id>/draft.json` server-side. Closing the tab, restarting the server, or a browser crash all resume where they left off. The draft is deleted on submit.

---

## Where things live

```
question-surface/
├── qsurface.py            # CLI
├── qsurface/              # spec validation, rendering, storage, server
├── assets/                # app.css + app.js, inlined into the rendered page
├── questionnaires/<id>.json   # authored question sets — tracked
├── responses/<id>/
│   ├── <timestamp>.json   # the machine record — this is what the agent reads
│   ├── <timestamp>.md     # human/git-diffable render of the same answers
│   └── draft.json         # in-progress, deleted on submit
└── tests/
```

Responses are tracked in git. They are decisions, and a decision that only exists in a chat transcript is a decision nobody can find later.

---

## Authoring a questionnaire

`questionnaires/example.json` is the reference spec and exercises every feature. Start from it or from `./qsurface.py new <id>`.

```json
{
  "id": "my-topic",
  "title": "My topic — object model decisions",
  "intro": "What this questionnaire decides and what it unblocks.",
  "context_docs": ["docs/DISCOVERY.md"],
  "sections": [
    {
      "title": "Object model",
      "intro": "Optional section preamble.",
      "questions": [ ... ]
    }
  ]
}
```

### Question types

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
| `id` | — | required, unique, alphanumeric + `-`/`_` |
| `prompt` | — | required, the question itself |
| `why` | `""` | **fill this in.** What the answer unblocks. A decision-maker answers better knowing what hangs on it |
| `required` | `false` | blocks submit unless answered or flagged unknown |
| `recommend` | `null` | marks an option `recommended`; the response records whether it was followed |
| `allow_unknown` | `true` | renders "Don't know — flag for research" |
| `notes` | `true` | renders a free-text notes box |
| `show_if` | — | conditional display |
| `placeholder` | `""` | scalar inputs only |

`options` accepts either a bare string (value and label are the same) or `{value, label, detail}`. `detail` is where the tradeoff of picking that option goes.

### Conditionals

```json
"show_if": { "question": "core-model", "equals": "custom" }
```

One of `equals`, `not_equals`, `includes` (multi-select contains), `any_of` (list), or `answered` (bool). The referenced question **must appear earlier** in the document — validation rejects forward references, which is what keeps one evaluation pass correct.

Conditionals are evaluated identically in the browser and on the server. A question whose branch was never taken is recorded as `skipped`, not as unanswered, so completion counts mean what they say. A branch hanging off a hidden question is itself hidden, and a stale draft cannot smuggle an answer into one.

### Inline formatting

`prompt`, `why`, `intro`, and `detail` support `` `code` ``, `**bold**`, and `*italic*`. Everything is HTML-escaped first, so a questionnaire can never inject markup.

---

## Reading the answers

```bash
./qsurface.py show my-topic                # summary + paths
./qsurface.py show my-topic --path-only    # just the latest JSON path
```

The response document:

```json
{
  "questionnaire_id": "my-topic",
  "respondent": "Alex",
  "submitted_at": "2026-08-14T01:07:00Z",
  "counts": { "total": 24, "answered": 20, "unknown": 3, "unanswered": 1, "skipped": 2 },
  "flagged_unknown": ["migration-cadence"],
  "unanswered": ["freeze-mechanism"],
  "skipped": ["campaign-followup"],
  "answers": {
    "core-model": {
      "prompt": "Which object model?",
      "type": "single",
      "value": "custom",
      "labels": ["Clean custom objects"],
      "unknown": false,
      "notes": "packaging is the deciding factor",
      "recommended": "custom",
      "followed_recommendation": true
    }
  }
}
```

`flagged_unknown` is the important list — those are the questions that need research rather than a decision, and they are the work item the questionnaire generates.

---

## Design constraints

- **Standard library only.** No npm, no pip install, no build step. A tool that rots because its dependencies moved is not durable, and this one has to still run in a year.
- **Loopback only.** No auth, no sessions, no multi-tenancy. It must never be reachable off the machine.
- **The JSON is authoritative; the markdown is regenerable.**
- **Spec validation is strict and fails at load.** A duplicate id, a forward-referencing conditional, or a recommendation naming a non-existent option costs a round trip with a human, which is the exact cost this tool exists to remove.

---

## Tests

```bash
python3 -m unittest discover -s tests -t .
```

30 tests covering spec validation, response building, conditional visibility, persistence, and rendering.
