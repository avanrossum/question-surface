"""Questionnaire spec loading and validation.

A questionnaire is a JSON document describing sections of questions. This module
is the single authority on what a valid spec looks like; the renderer and the
store both assume they are handed an already-validated spec.

Validation is strict and fails loudly. A questionnaire that reaches a human with
a broken conditional or a duplicate question id costs a round trip with that
human, which is exactly the cost this tool exists to avoid.
"""

from __future__ import annotations

import json
from pathlib import Path

# Question types that collect an answer. `info` is deliberately excluded — it is
# a content block, not a question, and never appears in the response document.
CHOICE_TYPES = {"single", "multi", "rank"}
SCALAR_TYPES = {"text", "longtext", "number", "date", "scale"}
ANSWER_TYPES = CHOICE_TYPES | SCALAR_TYPES
ALL_TYPES = ANSWER_TYPES | {"info"}

# Conditional operators supported by `show_if`.
CONDITION_OPS = {"equals", "not_equals", "includes", "answered", "any_of"}


class SpecError(ValueError):
    """Raised when a questionnaire spec is malformed."""


def load(path: str | Path) -> dict:
    """Load and validate a questionnaire spec from a JSON file."""
    path = Path(path)
    if not path.exists():
        raise SpecError(f"questionnaire not found: {path}")
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SpecError(f"{path}: invalid JSON — {exc}") from exc
    return validate(raw, source=str(path))


def validate(spec: dict, source: str = "<spec>") -> dict:
    """Validate a spec dict, returning it normalized with defaults applied."""
    if not isinstance(spec, dict):
        raise SpecError(f"{source}: spec must be a JSON object")

    for field in ("id", "title", "sections"):
        if not spec.get(field):
            raise SpecError(f"{source}: missing required field '{field}'")

    if not isinstance(spec["sections"], list) or not spec["sections"]:
        raise SpecError(f"{source}: 'sections' must be a non-empty list")

    spec.setdefault("intro", "")
    spec.setdefault("context_docs", [])
    spec.setdefault("respondent", "")

    seen_ids: set[str] = set()
    # Ordered list of answerable ids as they appear, so a `show_if` can only
    # reference a question the respondent has already been shown.
    order: list[str] = []

    for s_idx, section in enumerate(spec["sections"]):
        _validate_section(section, s_idx, source, seen_ids, order)

    return spec


def _validate_section(
    section: dict, s_idx: int, source: str, seen_ids: set[str], order: list[str]
) -> None:
    where = f"{source}: section[{s_idx}]"
    if not isinstance(section, dict):
        raise SpecError(f"{where}: must be an object")
    if not section.get("title"):
        raise SpecError(f"{where}: missing 'title'")
    section.setdefault("id", f"section-{s_idx + 1}")
    section.setdefault("intro", "")

    questions = section.get("questions")
    if not isinstance(questions, list) or not questions:
        raise SpecError(f"{where}: 'questions' must be a non-empty list")

    for q_idx, question in enumerate(questions):
        _validate_question(question, f"{where}.questions[{q_idx}]", seen_ids, order)


def _validate_question(
    question: dict, where: str, seen_ids: set[str], order: list[str]
) -> None:
    if not isinstance(question, dict):
        raise SpecError(f"{where}: must be an object")

    qtype = question.get("type")
    if qtype not in ALL_TYPES:
        raise SpecError(
            f"{where}: unknown type {qtype!r} — expected one of {sorted(ALL_TYPES)}"
        )

    if not question.get("prompt"):
        raise SpecError(f"{where}: missing 'prompt'")

    if qtype == "info":
        # An info block needs no id, but tolerate one for anchoring.
        question.setdefault("id", "")
        return

    qid = question.get("id")
    if not qid:
        raise SpecError(f"{where}: missing 'id'")
    if not isinstance(qid, str) or not qid.replace("-", "").replace("_", "").isalnum():
        raise SpecError(f"{where}: id {qid!r} must be alphanumeric with - or _")
    if qid in seen_ids:
        raise SpecError(f"{where}: duplicate question id {qid!r}")
    seen_ids.add(qid)

    # Defaults. `allow_unknown` and `notes` default on: this tool is used to ask
    # a decision-maker things they may not know yet, and "I don't know" is a
    # first-class answer that must be distinguishable from "skipped".
    question.setdefault("why", "")
    question.setdefault("recommend", None)
    question.setdefault("required", False)
    question.setdefault("allow_unknown", True)
    question.setdefault("notes", True)
    question.setdefault("placeholder", "")

    if qtype in CHOICE_TYPES:
        _validate_options(question, where)
    if qtype == "scale":
        question.setdefault("min", 1)
        question.setdefault("max", 5)
        question.setdefault("min_label", "")
        question.setdefault("max_label", "")
        if not isinstance(question["min"], int) or not isinstance(question["max"], int):
            raise SpecError(f"{where}: scale 'min'/'max' must be integers")
        if question["max"] - question["min"] < 1:
            raise SpecError(f"{where}: scale 'max' must exceed 'min'")
        if question["max"] - question["min"] > 10:
            raise SpecError(f"{where}: scale range must be 10 or fewer steps")

    if "show_if" in question and question["show_if"] is not None:
        _validate_condition(question["show_if"], where, order)

    order.append(qid)


def _validate_options(question: dict, where: str) -> None:
    options = question.get("options")
    if not isinstance(options, list) or len(options) < 2:
        raise SpecError(f"{where}: '{question['type']}' needs at least 2 options")

    seen_values: set[str] = set()
    for o_idx, option in enumerate(options):
        if isinstance(option, str):
            # Shorthand: a bare string is both value and label.
            options[o_idx] = option = {"value": option, "label": option}
        if not isinstance(option, dict):
            raise SpecError(f"{where}.options[{o_idx}]: must be an object or string")
        value = option.get("value")
        if not value:
            raise SpecError(f"{where}.options[{o_idx}]: missing 'value'")
        if value in seen_values:
            raise SpecError(f"{where}.options[{o_idx}]: duplicate value {value!r}")
        seen_values.add(value)
        option.setdefault("label", value)
        option.setdefault("detail", "")

    if question.get("recommend") is not None:
        recommended = question["recommend"]
        wanted = recommended if isinstance(recommended, list) else [recommended]
        for value in wanted:
            if value not in seen_values:
                raise SpecError(
                    f"{where}: recommend {value!r} is not one of its options"
                )


def _validate_condition(condition: dict, where: str, order: list[str]) -> None:
    if not isinstance(condition, dict):
        raise SpecError(f"{where}.show_if: must be an object")
    target = condition.get("question")
    if not target:
        raise SpecError(f"{where}.show_if: missing 'question'")
    if target not in order:
        raise SpecError(
            f"{where}.show_if: references {target!r}, which is not an earlier question"
        )
    ops = [key for key in condition if key in CONDITION_OPS]
    if len(ops) != 1:
        raise SpecError(
            f"{where}.show_if: needs exactly one of {sorted(CONDITION_OPS)}, got {ops}"
        )


def answerable_questions(spec: dict) -> list[dict]:
    """Every question in the spec that collects an answer, in document order."""
    return [
        question
        for section in spec["sections"]
        for question in section["questions"]
        if question["type"] in ANSWER_TYPES
    ]
