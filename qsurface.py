#!/usr/bin/env python3
"""Question Surface — collect answers to a large question set in one pass.

    ./qsurface.py serve example           # open the form, wait for submit
    ./qsurface.py validate example        # check a spec without serving
    ./qsurface.py render example -o /tmp/preview.html
    ./qsurface.py list                    # questionnaires + response counts
    ./qsurface.py show example            # summarize the latest response
    ./qsurface.py new my-questionnaire    # scaffold a new questionnaire

A questionnaire is referenced by its id (resolved under `questionnaires/`) or by
an explicit path to a JSON file.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from qsurface import render as render_mod  # noqa: E402
from qsurface import server as server_mod  # noqa: E402
from qsurface import spec as spec_mod  # noqa: E402
from qsurface import store  # noqa: E402

QUESTIONNAIRES = ROOT / "questionnaires"
RESPONSES = ROOT / "responses"


def resolve(reference: str) -> Path:
    """Resolve a questionnaire id or path to a spec file."""
    candidate = Path(reference)
    if candidate.suffix == ".json" and candidate.exists():
        return candidate
    for option in (
        QUESTIONNAIRES / f"{reference}.json",
        QUESTIONNAIRES / reference,
        candidate.with_suffix(".json"),
    ):
        if option.exists():
            return option
    raise SystemExit(
        f"error: no questionnaire {reference!r}\n"
        f"       looked in {QUESTIONNAIRES}/ — run `list` to see what exists"
    )


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
    responses_root = Path(args.responses) if args.responses else RESPONSES
    responses_root.mkdir(parents=True, exist_ok=True)

    outcome = server_mod.serve(
        spec,
        responses_root,
        port=args.port,
        open_browser=not args.no_open,
        stay_open=args.stay_open,
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
        spec, standalone=True, respondent=store.detect_respondent()
    )
    if args.out:
        out = Path(args.out)
        out.write_text(html, encoding="utf-8")
        print(f"wrote {out}")
    else:
        sys.stdout.write(html)
    return 0


def cmd_list(args) -> int:
    if not QUESTIONNAIRES.exists():
        print("no questionnaires directory yet")
        return 0
    files = sorted(QUESTIONNAIRES.glob("*.json"))
    if not files:
        print("no questionnaires yet — scaffold one with `new <id>`")
        return 0

    for path in files:
        try:
            spec = spec_mod.load(path)
        except spec_mod.SpecError as exc:
            print(f"  {path.stem:<32} INVALID — {exc}")
            continue
        count = len(spec_mod.answerable_questions(spec))
        directory = store.response_dir(RESPONSES, spec["id"])
        responses = sorted(directory.glob("*.json")) if directory.exists() else []
        responses = [r for r in responses if r.name != store.DRAFT_NAME]
        has_draft = (directory / store.DRAFT_NAME).exists()
        state = f"{len(responses)} response(s)" if responses else "no responses"
        if has_draft:
            state += " · draft in progress"
        print(f"  {spec['id']:<32} {count:>3}q  {state}")
        print(f"  {'':<32}      {spec['title']}")
    return 0


def cmd_show(args) -> int:
    path = resolve(args.questionnaire)
    spec = spec_mod.load(path)
    directory = store.response_dir(RESPONSES, spec["id"])
    files = sorted(directory.glob("*.json")) if directory.exists() else []
    files = [f for f in files if f.name != store.DRAFT_NAME]
    if not files:
        print(f"no responses yet for {spec['id']}")
        return 1

    latest = files[-1]
    if args.path_only:
        print(latest)
        return 0

    data = json.loads(latest.read_text(encoding="utf-8"))
    counts = data["counts"]
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
    QUESTIONNAIRES.mkdir(parents=True, exist_ok=True)
    path = QUESTIONNAIRES / f"{args.questionnaire}.json"
    if path.exists():
        raise SystemExit(f"error: {path} already exists")
    spec = dict(SCAFFOLD)
    spec["id"] = args.questionnaire
    spec["title"] = args.title or args.questionnaire
    path.write_text(json.dumps(spec, indent=2) + "\n", encoding="utf-8")
    print(f"scaffolded {path}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="qsurface", description="Batch question collection."
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
    p.set_defaults(func=cmd_show)

    p = sub.add_parser("new", help="scaffold a new questionnaire")
    p.add_argument("questionnaire")
    p.add_argument("--title")
    p.set_defaults(func=cmd_new)

    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except spec_mod.SpecError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
