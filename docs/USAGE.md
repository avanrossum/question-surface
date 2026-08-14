# Usage

Every command, where files land, and how an agent drives the tool.

---

## Commands

```bash
qsurface list                        # questionnaires and response counts
qsurface new <id> --title "..."      # scaffold a questionnaire
qsurface validate <id>               # check a spec without serving it
qsurface serve <id>                  # serve, block until submitted
qsurface show <id>                   # summarize the latest response
qsurface show <id> --path-only       # just the latest JSON path
qsurface show <id> --open            # open the markdown render for reading
qsurface render <id> -o out.html     # standalone preview, no server
qsurface archive <id>                # retire a questionnaire, keep its responses
qsurface config [key] [value]        # per-user settings
qsurface doctor                      # check the install
qsurface --version
```

Interview commands are in [INTERVIEWS.md](INTERVIEWS.md).

### serve

Binds `127.0.0.1`, opens a browser, and exits once the form is submitted, printing the paths it wrote.

| Flag | Effect |
|---|---|
| `--timeout MINUTES` | Give up waiting. Default 120; `0` waits forever. |
| `--port N` | Preferred port, default 8777. |
| `--no-open` | Do not open a browser. |
| `--stay-open` | Keep serving after a submit, for several respondents. |
| `--responses DIR` | Override where responses are written. |

If the preferred port is busy it takes a free one and says so, so two agents can ask you things at the same time.

On timeout it writes no response and exits non-zero. The draft is saved, so re-serving resumes where the respondent stopped. A partial record that reads like a decision is worse than no record, so nothing is written until submit.

---

## The question gate

**Five or more questions go to the surface. Four or fewer can be asked in chat.** Also use it below that count when the answers would benefit from exposition, real answer choices, or open-ended interaction — two genuinely hard forks belong on a surface, four easy questions do not.

The count is per-user:

```bash
qsurface config gate 3     # then re-run ./install.sh to refresh the pointer line
qsurface config            # show current settings
```

A skill is static text an agent reads rather than a program that can look a setting up, which is why the installer writes the number into your global `CLAUDE.md`. Without that line an agent assumes the default.

`timeout_minutes` is the other setting, controlling how long `serve` and `interview ask` wait.

The gate is a floor on batching, not a licence to manufacture questions. Five questions that should have been one routine call the agent was competent to make is worse than asking nothing.

---

## Where files land

Questionnaires and responses live in the project you are working in:

```
<your project>/
└── .question-surface/
    ├── questionnaires/<id>.json
    ├── responses/<id>/
    │   ├── <timestamp>.json    # the machine record
    │   ├── <timestamp>.md      # the human record
    │   └── draft.json          # in progress, deleted on submit, not tracked
    └── interviews/             # running session state, not tracked
```

A decision belongs in the repository it is about, where it can be reviewed alongside the change it gates and found by whoever clones the project later. Responses are meant to be committed; the tool never touches your git index.

The project root is the nearest enclosing repository, so it does not matter which subdirectory you run from. `QSURFACE_PROJECT` overrides it.

Questionnaire ids resolve against the project first, then the questionnaires bundled with the tool — which is how `example` stays readable from anywhere without being copied into projects.

---

## How an agent drives it

```
has questions → writes a spec → validates it → serves it → hands you a URL
             → keeps working on whatever the answers do not block
             → you submit → the server exits → it reads the answers → proceeds
```

The agent should run `serve` as a background command so the session stays responsive, tell you the URL plainly, and say which parts of the work are waiting on you.

Reading the answers back:

```bash
qsurface show <id>              # summary and paths
qsurface show <id> --path-only  # feed the JSON path to something else
```

`flagged_unknown` in a response is a work item rather than a non-answer. Those questions need research; the agent should do it or track it rather than asking again.

---

## Uninstalling

```bash
./install.sh --uninstall
```

Removes the PATH symlink, the skill symlink, and the block it added to your global `CLAUDE.md`. Your config and any responses in your projects are left alone.
