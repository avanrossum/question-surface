# Question Surface

A local web form for collecting answers to a large set of questions in one pass.

Serialized question-and-answer in chat is the wrong shape for architecture work. A fork with eight dependent questions becomes eight round trips, each one carrying less context than the last, and the answers end up scattered across a transcript that nobody re-reads. The Question Surface collects the whole set at once, in a form built for the questions being asked, and writes the answers to disk where an agent reads them directly.

Nothing in it is domain-specific. It is a spec format, a renderer, and a loopback server.

---

## Install

```bash
git clone https://github.com/avanrossum/question-surface.git
cd question-surface
./install.sh
```

That does three things, each of which it will tell you about and none of which it does silently:

1. Symlinks `qsurface` into `~/.local/bin`.
2. Symlinks the `question-surface` skill into `~/.claude/skills/`, so every Claude Code session in every project can see it.
3. Offers to add one line to your global `~/.claude/CLAUDE.md` carrying the current gate. It asks first, and `./install.sh --uninstall` removes everything it added.

Symlinks rather than copies, so `git pull` updates the tool and the skill together. Requires Python 3.9+ and nothing else. Run `qsurface doctor` any time to see what is and isn't wired up.

---

## The gate

**Five or more questions go through the surface; four or fewer can be asked in chat.** Also use it below that count when the answers would benefit from exposition, detailed answer choices, or open-ended interaction — two genuinely hard forks belong here, four easy ones don't.

The count is per-user:

```bash
qsurface config gate 3     # then re-run ./install.sh to refresh the pointer line
qsurface config            # show current settings
```

A skill is static text an agent reads rather than a program that can look a setting up, which is why the installer writes the number into your global `CLAUDE.md` — without that line an agent assumes the default.

---

## Usage

```bash
qsurface list                        # questionnaires + response counts
qsurface new my-topic --title "..."  # scaffold a new questionnaire
qsurface validate my-topic           # check a spec without serving it
qsurface serve my-topic              # open the form, block until submitted
qsurface show my-topic               # summarize the latest response
qsurface show my-topic --open        # open the markdown render for reading
qsurface archive my-topic            # retire it, keeping its responses
qsurface render my-topic -o out.html # standalone preview, no server
qsurface doctor                      # check the install
```

`serve` binds to `127.0.0.1`, opens a browser, and exits once the form is submitted, printing the paths it wrote. If the preferred port is busy it takes a free one and says so, so two agents can ask questions at the same time. `--stay-open` keeps serving for multiple respondents, `--no-open` suppresses the browser, `--port` moves off 8777.

**It stops waiting eventually.** `--timeout MINUTES` (default 120, `0` waits forever) ends the wait if nobody submits. On timeout it writes no response and exits non-zero — the draft is saved, so re-serving resumes where the respondent stopped. A partial record that reads like a decision is worse than no record.

**Answers are never lost.** Every keystroke persists to `localStorage`, and a debounced save writes a server-side draft. Closing the tab, restarting the server, or a browser crash all resume where they left off. The draft is deleted on submit.

---

## Where things live

Questionnaires and responses live in **the project you are working in**, not next to the tool:

```
<your project>/
└── .question-surface/
    ├── questionnaires/<id>.json   # authored question sets — tracked
    └── responses/<id>/
        ├── <timestamp>.json       # the machine record — this is what the agent reads
        ├── <timestamp>.md         # human/git-diffable render of the same answers
        └── draft.json             # in-progress, deleted on submit, not tracked
```

A decision belongs in the repository it is about, where it can be reviewed alongside the change it gates. Responses are meant to be committed; the tool never stages them itself. The project root is the nearest enclosing repository, so it does not matter which subdirectory you run from. `QSURFACE_PROJECT` overrides it.

The tool's own directory holds the CLI, the package, the assets, and the bundled `example` questionnaire, which is readable from any project.

---

## Authoring a questionnaire

`questionnaires/example.json` is the reference spec and exercises every feature. Start from it or from `./qsurface.py new <id>`.

```json
{
  "id": "my-topic",
  "title": "My topic — object model decisions",
  "intro": "What this questionnaire decides and what it unblocks.",
  "context_docs": ["docs/DISCOVERY.md"],
  "spec_version": 1,
  "follows": "an-earlier-questionnaire-id",
  "sections": [
    {
      "title": "Object model",
      "intro": "Optional section preamble.",
      "questions": [ ... ]
    }
  ]
}
```

`spec_version` is optional and defaults to `1`; a questionnaire declaring a version newer than the installed tool understands is refused rather than half-read. `follows` is optional — naming an earlier questionnaire renders a read-only panel of what that round settled, so a second pass does not make the respondent reconstruct it from memory.

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
python3 -m unittest discover -s tests -t .   # 60 tests, under a second
python3 scripts/check_browser.py             # client-side checks in a real browser
```

The Python suite covers spec validation, response building, conditional visibility, persistence, rendering, path resolution, config, and follow-up panels.

The browser checks cover `assets/app.js`, which the Python suite cannot reach — conditional show/hide and the residue it must clear, rank seeding, progress counting, and required-field blocking. They drive headless Chrome (or Chromium, or Edge) if one is installed and skip cleanly if not, rather than pulling in a JavaScript toolchain and breaking the no-build-step constraint. `--require` turns a missing browser into a failure, which is what CI uses.
