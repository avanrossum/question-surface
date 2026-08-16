#!/usr/bin/env python3
"""Question Surface — collect answers to a large question set in one pass.

    qsurface serve example           # open the form, wait for submit
    qsurface validate example        # check a spec without serving
    qsurface render example -o /tmp/preview.html
    qsurface list                    # questionnaires + response counts
    qsurface show example            # summarize the latest response
    qsurface new my-questionnaire    # scaffold a new questionnaire
    qsurface doctor                  # check the install is wired up

A questionnaire is referenced by its id or by an explicit path to a JSON file.
Ids resolve against the current project's `.question-surface/questionnaires/`
first, then the questionnaires bundled with the tool. Responses are always
written into the project. See `qsurface/paths.py`.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from qsurface import __version__  # noqa: E402
from qsurface import browser  # noqa: E402
from qsurface import config as config_mod  # noqa: E402
from qsurface import interview  # noqa: E402
from qsurface import paths  # noqa: E402
from qsurface import render as render_mod  # noqa: E402
from qsurface import server as server_mod  # noqa: E402
from qsurface import spec as spec_mod  # noqa: E402
from qsurface import store  # noqa: E402


def find_spec(reference: str) -> Path | None:
    """Locate a questionnaire spec, or None. Interviews have no spec file."""
    candidate = Path(reference)
    if candidate.suffix == ".json" and candidate.exists():
        return candidate
    for directory in paths.search_path():
        for option in (directory / f"{reference}.json", directory / reference):
            if option.exists():
                return option
    if candidate.with_suffix(".json").exists():
        return candidate.with_suffix(".json")
    return None


def resolve(reference: str) -> Path:
    """Resolve a questionnaire id or path to a spec file."""
    found = find_spec(reference)
    if found:
        return found
    searched = paths.search_path()
    looked = "\n".join(f"         {d}/" for d in searched)
    raise SystemExit(
        f"error: no questionnaire {reference!r}\n"
        f"       looked in:\n{looked}\n"
        f"       run `qsurface list` to see what exists"
    )


def latest_response(questionnaire_id: str) -> Path | None:
    """The most recent submitted response, ignoring any in-progress draft."""
    directory = store.response_dir(paths.responses_dir(), questionnaire_id)
    if not directory.exists():
        return None
    files = [f for f in sorted(directory.glob("*.json")) if f.name != store.DRAFT_NAME]
    return files[-1] if files else None


def prior_answers(spec: dict) -> dict:
    """Answers from the questionnaire this one follows, if there are any.

    A follow-up round that cannot show what was already decided makes the
    respondent re-derive it from memory, which is the failure this tool exists
    to remove.
    """
    if not spec.get("follows"):
        return {}
    path = latest_response(spec["follows"])
    if not path:
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def cmd_validate(args) -> int:
    path = resolve(args.questionnaire)
    spec = spec_mod.load(path)
    questions = spec_mod.answerable_questions(spec)
    required = sum(1 for q in questions if q.get("required"))
    conditional = sum(1 for q in questions if q.get("show_if"))
    print(f"ok  {path.name}")
    print(f"    {spec['title']}")
    print(
        f"    {len(spec['sections'])} sections · {len(questions)} questions "
        f"({required} required, {conditional} conditional)"
    )
    return 0


def cmd_serve(args) -> int:
    path = resolve(args.questionnaire)
    spec = spec_mod.load(path)
    responses_root = Path(args.responses) if args.responses else paths.responses_dir()
    responses_root.mkdir(parents=True, exist_ok=True)

    minutes = (
        args.timeout
        if args.timeout is not None
        else config_mod.get("timeout_minutes")
    )
    outcome = server_mod.serve(
        spec,
        responses_root,
        port=args.port,
        open_browser=not args.no_open,
        stay_open=args.stay_open,
        timeout=(minutes * 60) if minutes else None,
        prior=prior_answers(spec),
    )
    if not outcome:
        return 1

    counts = outcome["response"]["counts"]
    print("  Submitted.")
    print(f"    answered  {counts['answered']}/{counts['total']}")
    print(f"    unknown   {counts['unknown']}")
    print(f"    blank     {counts['unanswered']}")
    print(f"    json      {outcome['json']}")
    print(f"    markdown  {outcome['markdown']}")
    return 0


def cmd_render(args) -> int:
    path = resolve(args.questionnaire)
    spec = spec_mod.load(path)
    html = render_mod.render(
        spec,
        standalone=True,
        respondent=store.detect_respondent(),
        prior=prior_answers(spec),
    )
    if args.out:
        out = Path(args.out)
        out.write_text(html, encoding="utf-8")
        print(f"wrote {out}")
    else:
        sys.stdout.write(html)
    return 0


def cmd_list(args) -> int:
    responses_root = paths.responses_dir()
    seen: set[str] = set()
    found = False

    for directory in paths.search_path():
        files = sorted(directory.glob("*.json")) if directory.exists() else []
        if not files:
            continue
        label = (
            "project" if directory == paths.questionnaires_dir() else "bundled"
        )
        print(f"{label}  {directory}")
        found = True
        for path in files:
            try:
                spec = spec_mod.load(path)
            except spec_mod.SpecError as exc:
                print(f"  {path.stem:<30} INVALID — {exc}")
                continue
            if spec["id"] in seen:
                # A project questionnaire shadows a bundled one of the same id.
                print(f"  {spec['id']:<30}      (shadowed by the project copy)")
                continue
            seen.add(spec["id"])
            count = len(spec_mod.answerable_questions(spec))
            answers = store.response_dir(responses_root, spec["id"])
            responses = sorted(answers.glob("*.json")) if answers.exists() else []
            responses = [r for r in responses if r.name != store.DRAFT_NAME]
            state = f"{len(responses)} response(s)" if responses else "no responses"
            if (answers / store.DRAFT_NAME).exists():
                state += " · draft in progress"
            print(f"  {spec['id']:<30} {count:>3}q  {state}")
            print(f"  {'':<30}      {spec['title']}")
        print()

    if not found:
        print("no questionnaires yet — scaffold one with `qsurface new <id>`")
        print(f"they will be written to {paths.questionnaires_dir()}")
    return 0


def cmd_show(args) -> int:
    # An interview transcript has no questionnaire behind it, so fall back to
    # the reference as a bare id rather than insisting on a spec file.
    spec_path = find_spec(args.questionnaire)
    identifier = args.questionnaire
    if spec_path:
        identifier = spec_mod.load(spec_path)["id"]

    directory = store.response_dir(paths.responses_dir(), identifier)
    files = sorted(directory.glob("*.json")) if directory.exists() else []
    files = [f for f in files if f.name != store.DRAFT_NAME]
    if not files:
        if not spec_path:
            raise SystemExit(
                f"error: no questionnaire or interview {args.questionnaire!r}"
            )
        print(f"no responses yet for {identifier}")
        return 1

    latest = files[-1]
    if args.path_only:
        print(latest)
        return 0

    if args.open:
        markdown = latest.with_suffix(".md")
        target = markdown if markdown.exists() else latest
        webbrowser.open(target.as_uri())
        print(f"opened {target}")
        return 0

    data = json.loads(latest.read_text(encoding="utf-8"))
    counts = data["counts"]

    if data.get("kind") == "interview":
        print(f"{data['title']}  ({latest.name})")
        print(f"  respondent {data['respondent'] or '(unstated)'}")
        if data.get("domain"):
            print(f"  conducted as {data['domain']}")
        print(
            f"  {counts['answered']} answered · {counts['skipped']} skipped "
            f"of {counts['asked']} asked"
        )
        if not data.get("ended_at"):
            print("  still in progress — this transcript is not final")
        print(f"  json     {latest}")
        print(f"  markdown {latest.with_suffix('.md')}")
        return 0

    print(f"{data['title']}  ({latest.name})")
    print(f"  respondent {data['respondent'] or '(unstated)'}")
    print(
        f"  answered {counts['answered']}/{counts['total']} · "
        f"unknown {counts['unknown']} · blank {counts['unanswered']}"
    )
    if data["flagged_unknown"]:
        print(f"  needs research: {', '.join(data['flagged_unknown'])}")
    if data["unanswered"]:
        print(f"  left blank:     {', '.join(data['unanswered'])}")
    print(f"  json     {latest}")
    print(f"  markdown {latest.with_suffix('.md')}")
    return 0


SCAFFOLD = {
    "id": "",
    "title": "",
    "intro": "One paragraph on what this questionnaire decides and what happens next.",
    "context_docs": [],
    "sections": [
        {
            "title": "First section",
            "intro": "",
            "questions": [
                {
                    "id": "example-question",
                    "type": "single",
                    "prompt": "What should we do?",
                    "why": "State why the answer matters and what it unblocks.",
                    "required": True,
                    "recommend": "option-a",
                    "options": [
                        {
                            "value": "option-a",
                            "label": "Option A",
                            "detail": "What choosing this commits us to.",
                        },
                        {
                            "value": "option-b",
                            "label": "Option B",
                            "detail": "What choosing this commits us to.",
                        },
                    ],
                }
            ],
        }
    ],
}


def cmd_new(args) -> int:
    directory = paths.questionnaires_dir()
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{args.questionnaire}.json"
    if path.exists():
        raise SystemExit(f"error: {path} already exists")
    spec = dict(SCAFFOLD)
    spec["id"] = args.questionnaire
    spec["title"] = args.title or args.questionnaire
    path.write_text(json.dumps(spec, indent=2) + "\n", encoding="utf-8")
    print(f"scaffolded {path}")
    return 0


def cmd_config(args) -> int:
    settings = config_mod.load()
    if not args.key:
        print(f"config  {config_mod.config_path()}")
        for key, value in settings.items():
            marker = "" if key in _stored_keys() else "  (default)"
            print(f"  {key:<16} {value}{marker}")
        print()
        print(config_mod.gate_sentence())
        return 0

    if args.value is None:
        print(settings.get(args.key, ""))
        return 0

    try:
        value = int(args.value)
    except ValueError:
        raise SystemExit(f"error: {args.key} must be a whole number")
    if value < 0:
        raise SystemExit(f"error: {args.key} cannot be negative")

    try:
        path = config_mod.set_value(args.key, value)
    except KeyError as exc:
        raise SystemExit(f"error: {exc}")
    print(f"{args.key} = {value}   ({path})")
    if args.key == "gate":
        print()
        print("Update the pointer line in your global CLAUDE.md so agents see it:")
        print(f"  {config_mod.gate_sentence(value)}")
    return 0


def _stored_keys() -> set[str]:
    path = config_mod.config_path()
    if not path.exists():
        return set()
    try:
        return set(json.loads(path.read_text(encoding="utf-8")))
    except (json.JSONDecodeError, OSError):
        return set()


def cmd_doctor(args) -> int:
    """Report whether an install is actually wired up, and what is missing."""
    problems = 0

    def check(ok: bool, label: str, detail: str = "") -> None:
        nonlocal problems
        if not ok:
            problems += 1
        print(f"  {'ok  ' if ok else 'FAIL'}  {label}")
        if detail:
            print(f"          {detail}")

    print(f"question-surface {__version__}")
    print(f"  installed at {ROOT}")
    print()

    major, minor = sys.version_info[:2]
    check(
        (major, minor) >= (3, 9),
        f"python {major}.{minor}",
        "" if (major, minor) >= (3, 9) else "needs 3.9 or newer",
    )

    on_path = shutil.which("qsurface")
    check(
        bool(on_path),
        "qsurface on PATH",
        on_path or "run ./install.sh, or add this directory to PATH",
    )

    skill = Path.home() / ".claude" / "skills" / "question-surface"
    linked = skill.exists()
    target = ""
    if skill.is_symlink():
        target = f"-> {os.readlink(skill)}"
    check(linked, "skill installed for Claude Code", target or (
        "" if linked else f"expected {skill} — run ./install.sh"
    ))

    settings = config_mod.load()
    check(True, f"gate = {settings['gate']}", str(config_mod.config_path()))
    check(
        True,
        f"serve timeout = {settings['timeout_minutes'] or 'none'} min",
    )

    claude_md = Path.home() / ".claude" / "CLAUDE.md"
    pointer = False
    if claude_md.exists():
        try:
            pointer = "Question Surface:" in claude_md.read_text(encoding="utf-8")
        except OSError:
            pointer = False
    check(
        pointer,
        "gate pointer in global CLAUDE.md",
        "" if pointer else "agents will assume the default — run ./install.sh to add it",
    )

    chrome = browser.find_chrome()
    check(
        bool(chrome),
        "headless browser for JS checks",
        chrome or "optional — only needed to run scripts/check_browser.py",
    )

    # A dead agent can leave a session file behind pointing at nothing.
    sessions = interview.list_sessions()
    stale = [s for s in sessions if not interview.health(s)]
    if sessions:
        check(
            not stale,
            f"{len(sessions)} interview(s) open, {len(stale)} stale",
            ""
            if not stale
            else "clear with: "
            + ", ".join(f"qsurface interview close {s['id']}" for s in stale),
        )

    print()
    print("all good" if not problems else f"{problems} thing(s) need attention")
    return 0 if not problems else 1


def cmd_interview_open(args) -> int:
    existing = interview.session_file(args.interview)
    if existing.exists():
        session = json.loads(existing.read_text(encoding="utf-8"))
        if interview.health(session):
            print(f"  already open → http://127.0.0.1:{session['port']}/")
            return 0
        existing.unlink(missing_ok=True)  # stale record from a dead server

    # Pick a free port here so the parent knows the URL without waiting on the
    # child to report one back.
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]

    record = interview.new_record(
        args.interview, args.title or args.interview, args.domain or "", port
    )
    interview.write_session(record)

    log_path = interview.sessions_dir() / f"{args.interview}.log"
    with open(log_path, "ab") as log:
        child = subprocess.Popen(
            [sys.executable, str(ROOT / "qsurface.py"), "interview", "_serve",
             args.interview],
            stdout=log,
            stderr=log,
            start_new_session=True,
        )
    record["pid"] = child.pid
    interview.write_session(record)

    url = f"http://127.0.0.1:{port}/"
    deadline = time.time() + 10
    while time.time() < deadline:
        if interview.health(record):
            break
        if child.poll() is not None:
            print(f"error: the interview server exited immediately — see {log_path}",
                  file=sys.stderr)
            return 1
        time.sleep(0.15)
    else:
        print(f"error: the interview server did not come up — see {log_path}",
              file=sys.stderr)
        return 1

    if not args.no_open:
        webbrowser.open(url)
    print(f"  Interview open → {url}")
    print(f"  {record['title']}")
    print("  Ask the first question with:")
    print(f"    qsurface interview ask {args.interview} --prompt \"...\"")
    return 0


def cmd_interview_serve(args) -> int:
    """Internal: the detached server process."""
    interview.serve(interview.read_session(args.interview))
    return 0


def cmd_interview_ask(args) -> int:
    session = interview.read_session(args.interview)
    if not interview.health(session):
        print("error: that interview is not running — reopen it", file=sys.stderr)
        return 1

    context = args.context or ""
    if args.context_file:
        context = Path(args.context_file).read_text(encoding="utf-8")

    question = {
        "prompt": args.prompt,
        "why": args.why or "",
        "context": context,
        "placeholder": args.placeholder or "",
        "options": args.option or [],
    }
    minutes = args.timeout if args.timeout is not None else config_mod.get(
        "timeout_minutes"
    )
    seconds = (minutes * 60) if minutes else None

    try:
        result = interview.control(
            session,
            "/control/ask",
            {"question": question, "timeout": seconds},
            # Outlast the server's own wait so the server decides the timeout.
            timeout=(seconds + 30) if seconds else None,
        )
    except (urllib.error.URLError, OSError) as exc:
        print(f"error: lost contact with the interview server — {exc}", file=sys.stderr)
        return 1

    if not result.get("ok"):
        print("no answer — the interview timed out or was closed", file=sys.stderr)
        return 1

    answer = result["answer"]
    if args.text:
        picked = answer.get("selected") or []
        if picked and not answer.get("skipped"):
            print("[" + ", ".join(picked) + "]")
        print("" if answer.get("skipped") else answer.get("answer", ""))
    else:
        print(json.dumps(answer, indent=2, ensure_ascii=False))
    return 0


def cmd_interview_close(args) -> int:
    session = interview.read_session(args.interview)
    if not interview.health(session):
        interview.session_file(args.interview).unlink(missing_ok=True)
        print("that interview was not running; cleared its session file")
        return 0
    result = interview.control(
        session, "/control/close", {"summary": args.summary or ""}, timeout=20
    )
    written = result.get("transcript") or {}
    print("  Interview closed.")
    if written:
        print(f"    json      {written.get('json', '')}")
        print(f"    markdown  {written.get('markdown', '')}")
    return 0


def cmd_interview_list(args) -> int:
    sessions = interview.list_sessions()
    if not sessions:
        print("no interviews open")
        return 0
    for session in sessions:
        alive = interview.health(session)
        state = (
            f"running · {alive['answered']} answered" if alive else "NOT RUNNING (stale)"
        )
        print(f"  {session['id']:<24} :{session['port']}  {state}")
        print(f"  {'':<24} {session['title']}")
    return 0


def cmd_interview_distill(args) -> int:
    """Scaffold a questionnaire from a finished interview.

    An interview reliably ends with material that has become precise enough to
    decide rather than discuss. Turning that into a questionnaire by hand means
    re-reading the transcript and retyping it, which is where things get lost.

    The tool cannot know which exchanges became decisions, so it does not
    pretend to: every question it writes is a marked draft for the agent to
    rewrite or delete, and the material behind each one travels with it.
    """
    latest = latest_response(args.interview)
    if not latest:
        raise SystemExit(f"error: no transcript for interview {args.interview!r}")

    transcript = json.loads(latest.read_text(encoding="utf-8"))
    if transcript.get("kind") != "interview":
        raise SystemExit(f"error: {latest} is not an interview transcript")

    exchanges = [e for e in transcript.get("exchanges", []) if not e.get("skipped")]
    if args.only:
        wanted = {int(n) for n in args.only.replace(" ", "").split(",") if n}
        exchanges = [e for e in exchanges if e.get("seq") in wanted]
        missing = wanted - {e.get("seq") for e in exchanges}
        if missing:
            print(
                f"note: no answered exchange for {sorted(missing)}", file=sys.stderr
            )
    if not exchanges:
        raise SystemExit("error: nothing to distill — no answered exchanges selected")

    questions: list[dict] = []
    for exchange in exchanges:
        picked = exchange.get("selected") or []
        said = " · ".join(picked)
        if exchange.get("answer"):
            said = f"{said}\n\n{exchange['answer']}" if said else exchange["answer"]
        questions.append(
            {
                "type": "info",
                "prompt": f"**Asked:** {exchange['prompt']}\n\n**You said:** {said}",
            }
        )
        questions.append(
            {
                "id": f"decision-{exchange['seq']}",
                "type": "longtext",
                "prompt": f"TODO — the decision this implies. Drafted from: "
                f"{_shorten(exchange['prompt'])}",
                "why": "TODO — say what this answer unblocks and what breaks if "
                "it goes the other way.",
                "required": False,
            }
        )

    questionnaire_id = args.out or f"{args.interview}-decisions"
    # An id, not a path. Without this a value like `/tmp/x` or `../x` walks out
    # of the questionnaires directory, because joining an absolute path
    # discards the base — and writes a spec whose id would never validate.
    if not questionnaire_id.replace("-", "").replace("_", "").isalnum():
        raise SystemExit(
            f"error: {questionnaire_id!r} is not a questionnaire id — "
            "letters, digits, - and _ only"
        )
    spec = {
        "id": questionnaire_id,
        "title": f"{transcript.get('title', args.interview)} — decisions",
        "intro": (
            f"Distilled from the *{transcript.get('title', args.interview)}* "
            f"interview of {transcript.get('started_at', '')[:10]}.\n\n"
            "**Every question below is a draft.** The tool cannot tell which "
            "parts of a conversation became decisions, so it carried all of "
            "them across and marked them. Rewrite what is a real fork, delete "
            "what is already settled, and put the options and their costs in "
            "before serving this."
        ),
        "follows": args.interview,
        "sections": [
            {
                "title": "Decisions to confirm",
                "intro": f"Drafted from {len(exchanges)} exchange(s).",
                "questions": questions,
            }
        ],
    }

    spec_mod.validate(json.loads(json.dumps(spec)))  # fail here, not on serve

    directory = paths.questionnaires_dir()
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{questionnaire_id}.json"
    if path.exists() and not args.force:
        raise SystemExit(f"error: {path} already exists — pass --force to replace")
    path.write_text(json.dumps(spec, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print(f"distilled {len(exchanges)} exchange(s) -> {path}")
    print(f"  every question is a TODO draft; edit them before serving")
    print(f"  serving it shows the interview above the questions (follows: {args.interview})")
    print(f"  next: qsurface validate {questionnaire_id}")
    return 0


def _shorten(text: str, limit: int = 70) -> str:
    text = " ".join(str(text).split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def cmd_archive(args) -> int:
    path = resolve(args.questionnaire)
    if path.parent.resolve() == paths.BUNDLED_QUESTIONNAIRES.resolve():
        raise SystemExit(
            f"error: {path.stem} is bundled with the tool, not this project — "
            "nothing to archive"
        )
    archive = paths.questionnaires_dir() / "archive"
    archive.mkdir(parents=True, exist_ok=True)
    destination = archive / path.name
    if destination.exists():
        raise SystemExit(f"error: {destination} already exists")
    path.rename(destination)
    print(f"archived {path.name} -> {destination}")
    print("  responses are untouched; `show` still reads them")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="qsurface", description="Batch question collection."
    )
    parser.add_argument(
        "--version", action="version", version=f"question-surface {__version__}"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("serve", help="serve a questionnaire and wait for submission")
    p.add_argument("questionnaire")
    p.add_argument("--port", type=int, default=8777)
    p.add_argument("--no-open", action="store_true", help="do not open a browser")
    p.add_argument(
        "--stay-open",
        action="store_true",
        help="keep serving after submit (multiple respondents)",
    )
    p.add_argument(
        "--timeout",
        type=int,
        default=None,
        metavar="MINUTES",
        help="give up waiting after this long; 0 waits forever "
        "(default: the `timeout_minutes` setting)",
    )
    p.add_argument("--responses", help="override the responses directory")
    p.set_defaults(func=cmd_serve)

    p = sub.add_parser("validate", help="validate a spec without serving it")
    p.add_argument("questionnaire")
    p.set_defaults(func=cmd_validate)

    p = sub.add_parser("render", help="render a standalone preview HTML file")
    p.add_argument("questionnaire")
    p.add_argument("-o", "--out")
    p.set_defaults(func=cmd_render)

    p = sub.add_parser("list", help="list questionnaires and response counts")
    p.set_defaults(func=cmd_list)

    p = sub.add_parser("show", help="summarize the latest response")
    p.add_argument("questionnaire")
    p.add_argument("--path-only", action="store_true")
    p.add_argument(
        "--open", action="store_true", help="open the markdown render for reading"
    )
    p.set_defaults(func=cmd_show)

    p = sub.add_parser("new", help="scaffold a new questionnaire")
    p.add_argument("questionnaire")
    p.add_argument("--title")
    p.set_defaults(func=cmd_new)

    p = sub.add_parser("config", help="show or change a per-user setting")
    p.add_argument("key", nargs="?", help=f"one of: {', '.join(config_mod.VALID_KEYS)}")
    p.add_argument("value", nargs="?", help="omit to read the current value")
    p.set_defaults(func=cmd_config)

    p = sub.add_parser("doctor", help="check that this install is wired up")
    p.set_defaults(func=cmd_doctor)

    p = sub.add_parser("archive", help="retire a questionnaire, keeping its responses")
    p.add_argument("questionnaire")
    p.set_defaults(func=cmd_archive)

    p = sub.add_parser(
        "interview",
        help="ask one question at a time, deciding each from the last answer",
    )
    iv = p.add_subparsers(dest="interview_command", required=True)

    s = iv.add_parser("open", help="start an interview and open the browser")
    s.add_argument("interview")
    s.add_argument("--title")
    s.add_argument(
        "--domain",
        help="the expertise the interview is conducted with, shown to the respondent",
    )
    s.add_argument("--no-open", action="store_true")
    s.set_defaults(func=cmd_interview_open)

    s = iv.add_parser("ask", help="ask one question and wait for the answer")
    s.add_argument("interview")
    s.add_argument("--prompt", required=True)
    s.add_argument("--why", help="why you are asking, shown under the question")
    s.add_argument("--placeholder")
    s.add_argument(
        "--option",
        action="append",
        help="a selectable answer, offered as a chip and recorded separately "
        "from the typed answer; repeatable",
    )
    s.add_argument(
        "--context",
        help="reasoning behind the question, shown in a collapsed block. "
        "Supports paragraphs, bullets, pipe tables and inline formatting",
    )
    s.add_argument(
        "--context-file",
        help="read the context from a file instead, for anything long",
    )
    s.add_argument("--timeout", type=int, default=None, metavar="MINUTES")
    s.add_argument("--text", action="store_true", help="print the answer text only")
    s.set_defaults(func=cmd_interview_ask)

    s = iv.add_parser("close", help="finish the interview and write the transcript")
    s.add_argument("interview")
    s.add_argument("--summary", help="a closing note shown to the respondent")
    s.set_defaults(func=cmd_interview_close)

    s = iv.add_parser("list", help="show open interviews")
    s.set_defaults(func=cmd_interview_list)

    s = iv.add_parser(
        "distill", help="scaffold a questionnaire from a finished interview"
    )
    s.add_argument("interview")
    s.add_argument("--out", help="questionnaire id, default <interview>-decisions")
    s.add_argument(
        "--only", help="comma-separated exchange numbers, default every answered one"
    )
    s.add_argument("--force", action="store_true", help="overwrite an existing spec")
    s.set_defaults(func=cmd_interview_distill)

    s = iv.add_parser("_serve", help=argparse.SUPPRESS)
    s.add_argument("interview")
    s.set_defaults(func=cmd_interview_serve)

    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except spec_mod.SpecError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
