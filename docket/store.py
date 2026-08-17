"""Response persistence.

Every submission writes two files side by side:

- `<stamp>.json` — the machine record, which is what Claude reads back.
- `<stamp>.md` — a human/git-diffable render of the same answers.

Both land in the response directory for that questionnaire. The JSON is
authoritative; the markdown is regenerable from it. Drafts go to a single
`draft.json` overwritten in place and deleted on submit, so a half-finished
questionnaire survives a browser crash without leaving debris behind.
"""

from __future__ import annotations

import getpass
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from . import spec as spec_mod

DRAFT_NAME = "draft.json"


def detect_respondent() -> str:
    """Who is answering.

    This is a local, single-user tool served on loopback — the machine already
    knows who is at the keyboard, so the form does not spend a field asking.
    Prefer the git identity for a human-readable name, fall back to the OS user.
    """
    try:
        result = subprocess.run(
            ["git", "config", "user.name"],
            capture_output=True,
            text=True,
            timeout=2,
        )
        name = result.stdout.strip()
        if name:
            return name
    except (OSError, subprocess.SubprocessError):
        pass
    try:
        return os.environ.get("USER") or os.environ.get("USERNAME") or getpass.getuser()
    except Exception:  # getpass raises on an unnamed uid
        return ""


def response_dir(root: Path, questionnaire_id: str) -> Path:
    return Path(root) / questionnaire_id


def _stamp(now: datetime | None = None) -> str:
    return (now or datetime.now(timezone.utc)).strftime("%Y-%m-%dT%H-%M-%SZ")


def _raw_value(submitted: dict, qid: str):
    entry = submitted.get(qid) or {}
    value = entry.get("value")
    return value.strip() if isinstance(value, str) else value


def _condition_met(condition: dict, value) -> bool:
    empty = value in (None, "", [])
    if "answered" in condition:
        return (not empty) if condition["answered"] else empty
    if "equals" in condition:
        return str(value) == str(condition["equals"])
    if "not_equals" in condition:
        return str(value) != str(condition["not_equals"])
    if "includes" in condition:
        return isinstance(value, list) and condition["includes"] in value
    if "any_of" in condition:
        wanted = condition.get("any_of") or []
        if isinstance(value, list):
            return any(v in wanted for v in value)
        return value in wanted
    return True


def visibility(spec: dict, submitted: dict) -> dict[str, bool]:
    """Which questions the respondent could actually reach, given their answers.

    Mirrors the client-side conditional logic. Without this the server counts a
    question the respondent was never shown as "left blank", which makes a
    completed questionnaire look unfinished. Spec validation guarantees a
    `show_if` only references an earlier question, so one forward pass is enough.
    """
    shown: dict[str, bool] = {}
    for question in spec_mod.answerable_questions(spec):
        condition = question.get("show_if")
        if not condition:
            shown[question["id"]] = True
            continue
        target = condition["question"]
        # A branch hanging off a hidden question is itself unreachable.
        reachable = shown.get(target, False)
        shown[question["id"]] = reachable and _condition_met(
            condition, _raw_value(submitted, target)
        )
    return shown


def build_response(spec: dict, submitted: dict, now: datetime | None = None) -> dict:
    """Merge the raw browser payload with the spec into the canonical document.

    `submitted` is what the browser posts: `{qid: {value, unknown, notes}}`.
    Anything the spec does not declare is dropped, so a stale draft against an
    edited questionnaire cannot smuggle in orphaned answers.
    """
    now = now or datetime.now(timezone.utc)
    answers: dict[str, dict] = {}
    unanswered: list[str] = []
    unknown: list[str] = []
    skipped: list[str] = []
    shown = visibility(spec, submitted)

    for question in spec_mod.answerable_questions(spec):
        qid = question["id"]
        raw = submitted.get(qid) or {}
        is_unknown = bool(raw.get("unknown"))
        value = raw.get("value")
        notes = (raw.get("notes") or "").strip()

        if isinstance(value, str):
            value = value.strip()
        empty = value in (None, "", [])

        visible = shown.get(qid, True)
        entry: dict = {
            "prompt": question["prompt"],
            "type": question["type"],
            "value": None if empty else value,
            "unknown": is_unknown,
        }
        if not visible:
            # A question the respondent never saw carries no answer, no notes,
            # and no verdict on a recommendation it was never shown. Clearing
            # only `value` leaves resolved labels and a recommendation verdict
            # attached to a question that was never asked.
            entry["skipped"] = True
            entry["value"] = None
            entry["unknown"] = False
        else:
            if notes:
                entry["notes"] = notes
            if question["type"] in spec_mod.CHOICE_TYPES and not empty:
                entry["labels"] = _labels_for(question, value)
            if question["type"] == "rank" and not empty:
                # False means the respondent accepted the order as presented
                # rather than arranging it — a weaker signal, but an answer.
                entry["reordered"] = bool(raw.get("reordered"))
            if question.get("recommend") is not None:
                entry["recommended"] = question["recommend"]
                entry["followed_recommendation"] = _follows(
                    question["recommend"], value
                )

        answers[qid] = entry

        if not visible:
            skipped.append(qid)
        elif is_unknown:
            unknown.append(qid)
        elif empty:
            unanswered.append(qid)

    reachable = len(answers) - len(skipped)
    return {
        "questionnaire_id": spec["id"],
        "title": spec["title"],
        "respondent": (
            submitted.get("__respondent__")
            or spec.get("respondent")
            or detect_respondent()
        ),
        "submitted_at": now.isoformat(timespec="seconds").replace("+00:00", "Z"),
        "counts": {
            "total": reachable,
            "answered": reachable - len(unanswered) - len(unknown),
            "unknown": len(unknown),
            "unanswered": len(unanswered),
            "skipped": len(skipped),
        },
        "flagged_unknown": unknown,
        "unanswered": unanswered,
        "skipped": skipped,
        "answers": answers,
    }


def _labels_for(question: dict, value) -> list[str]:
    by_value = {o["value"]: o["label"] for o in question.get("options", [])}
    values = value if isinstance(value, list) else [value]
    return [by_value.get(v, str(v)) for v in values]


def _follows(recommend, value) -> bool:
    wanted = recommend if isinstance(recommend, list) else [recommend]
    got = value if isinstance(value, list) else [value]
    return sorted(str(w) for w in wanted) == sorted(
        str(g) for g in got if g not in (None, "")
    )


def write(root: Path, spec: dict, response: dict, now: datetime | None = None) -> dict:
    """Write the JSON + markdown pair. Returns the paths written."""
    directory = response_dir(root, spec["id"])
    directory.mkdir(parents=True, exist_ok=True)
    stamp = _stamp(now)

    json_path = directory / f"{stamp}.json"
    json_path.write_text(
        json.dumps(response, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    md_path = directory / f"{stamp}.md"
    md_path.write_text(to_markdown(spec, response), encoding="utf-8")

    draft = directory / DRAFT_NAME
    if draft.exists():
        draft.unlink()

    return {"json": json_path, "markdown": md_path}


def save_draft(root: Path, questionnaire_id: str, payload: dict) -> Path:
    directory = response_dir(root, questionnaire_id)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / DRAFT_NAME
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def load_draft(root: Path, questionnaire_id: str) -> dict:
    path = response_dir(root, questionnaire_id) / DRAFT_NAME
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def to_markdown(spec: dict, response: dict) -> str:
    counts = response["counts"]
    lines = [
        f"# {response['title']} — responses",
        "",
        f"Questionnaire: `{response['questionnaire_id']}`  ",
        f"Submitted: {response['submitted_at']}  ",
        f"Respondent: {response['respondent'] or '(unstated)'}  ",
        f"Answered {counts['answered']} / {counts['total']}"
        f" · flagged unknown {counts['unknown']}"
        f" · left blank {counts['unanswered']}"
        + (
            f" · not shown {counts['skipped']}"
            if counts.get("skipped")
            else ""
        ),
        "",
    ]

    if response["flagged_unknown"]:
        lines += [
            "> **Needs research:** "
            + ", ".join(f"`{qid}`" for qid in response["flagged_unknown"]),
            "",
        ]

    for section in spec["sections"]:
        answerable = [
            q for q in section["questions"] if q["type"] in spec_mod.ANSWER_TYPES
        ]
        if not answerable:
            continue
        lines += [f"## {section['title']}", ""]
        for question in answerable:
            entry = response["answers"].get(question["id"], {})
            # A question whose branch was never taken is not a gap in the
            # answers; printing it as "(no answer)" reads as one.
            if entry.get("skipped"):
                continue
            lines += [f"### {question['prompt']}", "", f"*{format_value(entry)}*", ""]
            if entry.get("reordered") is False and not entry.get("unknown"):
                lines += ["<sub>accepted the presented order</sub>", ""]
            if entry.get("notes"):
                lines += [f"**Notes:** {entry['notes']}", ""]
            if entry.get("recommended") is not None and not entry.get("unknown"):
                verdict = (
                    "matches recommendation"
                    if entry.get("followed_recommendation")
                    else "**differs from recommendation**"
                )
                lines += [f"<sub>{verdict}</sub>", ""]

    return "\n".join(lines)


def format_value(entry: dict) -> str:
    """One-line human rendering of an answer. Shared with the follow-up panel."""
    if entry.get("unknown"):
        return "Don't know — needs research"
    if entry.get("labels"):
        return " · ".join(entry["labels"])
    value = entry.get("value")
    if value in (None, "", []):
        return "(no answer)"
    if isinstance(value, list):
        return " · ".join(str(v) for v in value)
    return str(value)
