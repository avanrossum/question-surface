"""Tests for the Question Surface spec, store and renderer.

Run: python3 -m unittest discover -s tests -t .
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from qsurface import render, spec as spec_mod, store  # noqa: E402


def minimal(**overrides) -> dict:
    base = {
        "id": "test-q",
        "title": "Test questionnaire",
        "sections": [
            {
                "title": "Section one",
                "questions": [
                    {
                        "id": "pick",
                        "type": "single",
                        "prompt": "Pick one",
                        "options": ["alpha", "beta"],
                    }
                ],
            }
        ],
    }
    base.update(overrides)
    return base


class TestSpecValidation(unittest.TestCase):
    def test_minimal_spec_validates_and_gets_defaults(self):
        result = spec_mod.validate(minimal())
        question = result["sections"][0]["questions"][0]
        self.assertTrue(question["allow_unknown"])
        self.assertTrue(question["notes"])
        self.assertFalse(question["required"])
        # String shorthand expands to full option objects.
        self.assertEqual(question["options"][0], {"value": "alpha", "label": "alpha", "detail": ""})

    def test_missing_top_level_field_rejected(self):
        for field in ("id", "title", "sections"):
            broken = minimal()
            del broken[field]
            with self.assertRaises(spec_mod.SpecError):
                spec_mod.validate(broken)

    def test_duplicate_question_id_rejected(self):
        broken = minimal()
        broken["sections"][0]["questions"].append(
            {"id": "pick", "type": "text", "prompt": "Again"}
        )
        with self.assertRaisesRegex(spec_mod.SpecError, "duplicate question id"):
            spec_mod.validate(broken)

    def test_unknown_type_rejected(self):
        broken = minimal()
        broken["sections"][0]["questions"][0]["type"] = "telepathy"
        with self.assertRaisesRegex(spec_mod.SpecError, "unknown type"):
            spec_mod.validate(broken)

    def test_choice_needs_two_options(self):
        broken = minimal()
        broken["sections"][0]["questions"][0]["options"] = ["only"]
        with self.assertRaisesRegex(spec_mod.SpecError, "at least 2 options"):
            spec_mod.validate(broken)

    def test_recommend_must_name_a_real_option(self):
        broken = minimal()
        broken["sections"][0]["questions"][0]["recommend"] = "gamma"
        with self.assertRaisesRegex(spec_mod.SpecError, "not one of its options"):
            spec_mod.validate(broken)

    def test_forward_referencing_condition_rejected(self):
        broken = minimal()
        broken["sections"][0]["questions"][0]["show_if"] = {
            "question": "later",
            "equals": "x",
        }
        with self.assertRaisesRegex(spec_mod.SpecError, "not an earlier question"):
            spec_mod.validate(broken)

    def test_backward_referencing_condition_accepted(self):
        ok = minimal()
        ok["sections"][0]["questions"].append(
            {
                "id": "followup",
                "type": "text",
                "prompt": "Why?",
                "show_if": {"question": "pick", "equals": "alpha"},
            }
        )
        spec_mod.validate(ok)

    def test_condition_needs_exactly_one_operator(self):
        broken = minimal()
        broken["sections"][0]["questions"].append(
            {
                "id": "followup",
                "type": "text",
                "prompt": "Why?",
                "show_if": {"question": "pick", "equals": "a", "includes": "b"},
            }
        )
        with self.assertRaisesRegex(spec_mod.SpecError, "exactly one of"):
            spec_mod.validate(broken)

    def test_scale_bounds_enforced(self):
        broken = minimal()
        broken["sections"][0]["questions"] = [
            {"id": "s", "type": "scale", "prompt": "Rate", "min": 5, "max": 5}
        ]
        with self.assertRaisesRegex(spec_mod.SpecError, "must exceed"):
            spec_mod.validate(broken)

    def test_info_block_needs_no_id_and_is_not_answerable(self):
        ok = minimal()
        ok["sections"][0]["questions"].insert(
            0, {"type": "info", "prompt": "Read this first."}
        )
        result = spec_mod.validate(ok)
        self.assertEqual(len(spec_mod.answerable_questions(result)), 1)


class TestResponseBuilding(unittest.TestCase):
    def setUp(self):
        self.spec = spec_mod.validate(
            minimal(
                sections=[
                    {
                        "title": "S",
                        "questions": [
                            {
                                "id": "pick",
                                "type": "single",
                                "prompt": "Pick one",
                                "options": [
                                    {"value": "alpha", "label": "Alpha"},
                                    {"value": "beta", "label": "Beta"},
                                ],
                                "recommend": "alpha",
                            },
                            {
                                "id": "many",
                                "type": "multi",
                                "prompt": "Pick several",
                                "options": [
                                    {"value": "x", "label": "Ex"},
                                    {"value": "y", "label": "Why"},
                                ],
                            },
                            {"id": "note", "type": "longtext", "prompt": "Explain"},
                        ],
                    }
                ]
            )
        )

    def test_counts_split_answered_unknown_and_blank(self):
        response = store.build_response(
            self.spec,
            {
                "pick": {"value": "alpha"},
                "many": {"unknown": True},
                # `note` omitted entirely
            },
        )
        self.assertEqual(response["counts"]["total"], 3)
        self.assertEqual(response["counts"]["answered"], 1)
        self.assertEqual(response["counts"]["unknown"], 1)
        self.assertEqual(response["counts"]["unanswered"], 1)
        self.assertEqual(response["flagged_unknown"], ["many"])
        self.assertEqual(response["unanswered"], ["note"])

    def test_choice_labels_resolved(self):
        response = store.build_response(
            self.spec, {"pick": {"value": "beta"}, "many": {"value": ["x", "y"]}}
        )
        self.assertEqual(response["answers"]["pick"]["labels"], ["Beta"])
        self.assertEqual(response["answers"]["many"]["labels"], ["Ex", "Why"])

    def test_recommendation_agreement_tracked(self):
        agreed = store.build_response(self.spec, {"pick": {"value": "alpha"}})
        self.assertTrue(agreed["answers"]["pick"]["followed_recommendation"])
        differed = store.build_response(self.spec, {"pick": {"value": "beta"}})
        self.assertFalse(differed["answers"]["pick"]["followed_recommendation"])

    def test_unrecognized_keys_are_dropped(self):
        response = store.build_response(
            self.spec, {"pick": {"value": "alpha"}, "ghost": {"value": "boo"}}
        )
        self.assertNotIn("ghost", response["answers"])

    def test_whitespace_only_answer_counts_as_blank(self):
        response = store.build_response(self.spec, {"note": {"value": "   "}})
        self.assertIn("note", response["unanswered"])
        self.assertIsNone(response["answers"]["note"]["value"])

    def test_notes_preserved_and_stripped(self):
        response = store.build_response(
            self.spec, {"pick": {"value": "alpha", "notes": "  because  "}}
        )
        self.assertEqual(response["answers"]["pick"]["notes"], "because")

    def test_respondent_falls_back_to_the_local_identity(self):
        # The form does not ask who is answering; a loopback tool already knows.
        response = store.build_response(self.spec, {"pick": {"value": "alpha"}})
        self.assertTrue(response["respondent"])

    def test_explicit_respondent_wins_over_detection(self):
        response = store.build_response(
            self.spec, {"__respondent__": "Someone Else", "pick": {"value": "alpha"}}
        )
        self.assertEqual(response["respondent"], "Someone Else")


class TestRankAnswers(unittest.TestCase):
    """An untouched rank list is an answer, not a blank."""

    def setUp(self):
        self.spec = spec_mod.validate(
            minimal(
                sections=[
                    {
                        "title": "S",
                        "questions": [
                            {
                                "id": "order",
                                "type": "rank",
                                "prompt": "Order these",
                                "options": [
                                    {"value": "a", "label": "Ay"},
                                    {"value": "b", "label": "Bee"},
                                ],
                            }
                        ],
                    }
                ]
            )
        )

    def test_accepted_order_records_reordered_false(self):
        response = store.build_response(
            self.spec, {"order": {"value": ["a", "b"], "reordered": False}}
        )
        answer = response["answers"]["order"]
        self.assertEqual(answer["value"], ["a", "b"])
        self.assertFalse(answer["reordered"])
        self.assertEqual(response["counts"]["answered"], 1)
        self.assertEqual(response["unanswered"], [])

    def test_dragged_order_records_reordered_true(self):
        response = store.build_response(
            self.spec, {"order": {"value": ["b", "a"], "reordered": True}}
        )
        self.assertTrue(response["answers"]["order"]["reordered"])
        self.assertEqual(response["answers"]["order"]["labels"], ["Bee", "Ay"])

    def test_missing_rank_is_still_blank(self):
        response = store.build_response(self.spec, {})
        self.assertEqual(response["unanswered"], ["order"])
        self.assertNotIn("reordered", response["answers"]["order"])

    def test_markdown_marks_an_accepted_order(self):
        accepted = store.to_markdown(
            self.spec,
            store.build_response(
                self.spec, {"order": {"value": ["a", "b"], "reordered": False}}
            ),
        )
        self.assertIn("accepted the presented order", accepted)
        dragged = store.to_markdown(
            self.spec,
            store.build_response(
                self.spec, {"order": {"value": ["b", "a"], "reordered": True}}
            ),
        )
        self.assertNotIn("accepted the presented order", dragged)


class TestConditionalVisibility(unittest.TestCase):
    """A question the respondent never saw is not an unanswered question."""

    def setUp(self):
        self.spec = spec_mod.validate(
            minimal(
                sections=[
                    {
                        "title": "S",
                        "questions": [
                            {
                                "id": "gate",
                                "type": "single",
                                "prompt": "Which path?",
                                "options": ["build", "defer"],
                            },
                            {
                                "id": "branch",
                                "type": "text",
                                "prompt": "Why defer?",
                                "show_if": {"question": "gate", "equals": "defer"},
                            },
                            {
                                "id": "nested",
                                "type": "text",
                                "prompt": "Until when?",
                                "show_if": {"question": "branch", "answered": True},
                            },
                        ],
                    }
                ]
            )
        )

    def test_untaken_branch_is_skipped_not_unanswered(self):
        response = store.build_response(self.spec, {"gate": {"value": "build"}})
        self.assertEqual(response["counts"]["total"], 1)
        self.assertEqual(response["counts"]["answered"], 1)
        self.assertEqual(response["counts"]["unanswered"], 0)
        self.assertEqual(sorted(response["skipped"]), ["branch", "nested"])
        self.assertTrue(response["answers"]["branch"]["skipped"])

    def test_taken_branch_counts_normally(self):
        response = store.build_response(
            self.spec, {"gate": {"value": "defer"}, "branch": {"value": "waiting on the spike"}}
        )
        self.assertEqual(response["counts"]["total"], 3)
        self.assertEqual(response["unanswered"], ["nested"])
        self.assertEqual(response["skipped"], [])

    def test_branch_off_a_hidden_question_stays_hidden(self):
        # `nested` depends on `branch`, which is itself hidden. Answering it
        # from a stale draft must not resurrect it.
        response = store.build_response(
            self.spec, {"gate": {"value": "build"}, "nested": {"value": "smuggled"}}
        )
        self.assertIn("nested", response["skipped"])
        self.assertIsNone(response["answers"]["nested"]["value"])

    def test_hidden_question_carries_no_residue(self):
        # A stale draft can hold a value, notes and an unknown flag for a
        # question the respondent cannot reach. None of it may survive into
        # the record as though the question had been asked.
        spec = spec_mod.validate(
            minimal(
                sections=[
                    {
                        "title": "S",
                        "questions": [
                            {
                                "id": "gate",
                                "type": "single",
                                "prompt": "Which path?",
                                "options": ["build", "defer"],
                            },
                            {
                                "id": "why",
                                "type": "single",
                                "prompt": "Why defer?",
                                "options": [
                                    {"value": "cost", "label": "Cost"},
                                    {"value": "risk", "label": "Risk"},
                                ],
                                "recommend": "cost",
                                "show_if": {"question": "gate", "equals": "defer"},
                            },
                        ],
                    }
                ]
            )
        )
        response = store.build_response(
            spec,
            {
                "gate": {"value": "build"},
                "why": {"value": "cost", "unknown": True, "notes": "stale"},
            },
        )
        hidden = response["answers"]["why"]
        self.assertTrue(hidden["skipped"])
        self.assertIsNone(hidden["value"])
        self.assertFalse(hidden["unknown"])
        self.assertNotIn("notes", hidden)
        self.assertNotIn("labels", hidden)
        self.assertNotIn("recommended", hidden)
        self.assertNotIn("followed_recommendation", hidden)

    def test_skipped_questions_omitted_from_markdown(self):
        response = store.build_response(self.spec, {"gate": {"value": "build"}})
        markdown = store.to_markdown(self.spec, response)
        self.assertNotIn("Why defer?", markdown)
        self.assertIn("Which path?", markdown)

    def test_condition_operators(self):
        self.assertTrue(store._condition_met({"equals": "a"}, "a"))
        self.assertFalse(store._condition_met({"equals": "a"}, "b"))
        self.assertTrue(store._condition_met({"not_equals": "a"}, "b"))
        self.assertTrue(store._condition_met({"includes": "x"}, ["x", "y"]))
        self.assertFalse(store._condition_met({"includes": "z"}, ["x", "y"]))
        self.assertTrue(store._condition_met({"any_of": ["a", "b"]}, "b"))
        self.assertTrue(store._condition_met({"any_of": ["a", "b"]}, ["b", "c"]))
        self.assertTrue(store._condition_met({"answered": True}, "something"))
        self.assertTrue(store._condition_met({"answered": False}, ""))


class TestPersistence(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.spec = spec_mod.validate(minimal())
        self.addCleanup(self.tmp.cleanup)

    def test_write_creates_json_and_markdown_and_clears_draft(self):
        store.save_draft(self.root, self.spec["id"], {"pick": {"value": "alpha"}})
        draft_path = store.response_dir(self.root, self.spec["id"]) / store.DRAFT_NAME
        self.assertTrue(draft_path.exists())

        response = store.build_response(self.spec, {"pick": {"value": "alpha"}})
        paths = store.write(
            self.root, self.spec, response, now=datetime(2026, 8, 13, 20, 5, 0, tzinfo=timezone.utc)
        )

        self.assertTrue(paths["json"].exists())
        self.assertTrue(paths["markdown"].exists())
        self.assertFalse(draft_path.exists())
        self.assertEqual(paths["json"].name, "2026-08-13T20-05-00Z.json")

        written = json.loads(paths["json"].read_text())
        self.assertEqual(written["answers"]["pick"]["value"], "alpha")

    def test_draft_round_trips(self):
        store.save_draft(self.root, "test-q", {"pick": {"value": "beta"}})
        self.assertEqual(
            store.load_draft(self.root, "test-q"), {"pick": {"value": "beta"}}
        )

    def test_corrupt_draft_returns_empty_rather_than_raising(self):
        directory = store.response_dir(self.root, "test-q")
        directory.mkdir(parents=True)
        (directory / store.DRAFT_NAME).write_text("{not json")
        self.assertEqual(store.load_draft(self.root, "test-q"), {})

    def test_markdown_flags_unknowns(self):
        response = store.build_response(self.spec, {"pick": {"unknown": True}})
        markdown = store.to_markdown(self.spec, response)
        self.assertIn("Needs research", markdown)
        self.assertIn("Don't know — needs research", markdown)


class TestRendering(unittest.TestCase):
    def test_renders_every_question_type(self):
        spec = spec_mod.validate(
            minimal(
                sections=[
                    {
                        "title": "All types",
                        "questions": [
                            {"type": "info", "prompt": "Context block"},
                            {
                                "id": "a",
                                "type": "single",
                                "prompt": "Single",
                                "options": ["x", "y"],
                            },
                            {
                                "id": "b",
                                "type": "multi",
                                "prompt": "Multi",
                                "options": ["x", "y"],
                            },
                            {
                                "id": "c",
                                "type": "rank",
                                "prompt": "Rank",
                                "options": ["x", "y"],
                            },
                            {"id": "d", "type": "scale", "prompt": "Scale"},
                            {"id": "e", "type": "text", "prompt": "Text"},
                            {"id": "f", "type": "longtext", "prompt": "Longtext"},
                            {"id": "g", "type": "number", "prompt": "Number"},
                            {"id": "h", "type": "date", "prompt": "Date"},
                        ],
                    }
                ]
            )
        )
        html = render.render(spec)
        for qid in "abcdefgh":
            self.assertIn(f'data-qid="{qid}"', html)
        self.assertIn("info-block", html)
        self.assertIn('type="date"', html)
        self.assertIn("rank-list", html)

    def test_spec_text_is_escaped(self):
        spec = spec_mod.validate(
            minimal(
                sections=[
                    {
                        "title": "S",
                        "questions": [
                            {
                                "id": "x",
                                "type": "text",
                                "prompt": "<script>alert(1)</script>",
                            }
                        ],
                    }
                ]
            )
        )
        html = render.render(spec)
        self.assertNotIn("<script>alert(1)</script>", html)
        self.assertIn("&lt;script&gt;", html)

    def test_inline_formatting_subset_applied(self):
        self.assertEqual(render.fmt("use `session_store`"), "use <code>session_store</code>")
        self.assertEqual(render.fmt("**bold**"), "<strong>bold</strong>")
        self.assertEqual(render.fmt("*em*"), "<em>em</em>")

    def test_close_on_submit_offered_when_served(self):
        spec = spec_mod.validate(minimal())
        served = render.render(spec)
        self.assertIn('id="closeOnSubmit"', served)
        self.assertIn("Close this tab when I submit", served)

    def test_close_on_submit_absent_from_a_standalone_preview(self):
        # A standalone render has no server to submit to, so the control would
        # promise something it cannot do.
        spec = spec_mod.validate(minimal())
        self.assertNotIn('id="closeOnSubmit"', render.render(spec, standalone=True))

    def test_conditions_reach_the_client_bootstrap(self):
        spec = spec_mod.validate(
            minimal(
                sections=[
                    {
                        "title": "S",
                        "questions": [
                            {
                                "id": "pick",
                                "type": "single",
                                "prompt": "Pick",
                                "options": ["a", "b"],
                            },
                            {
                                "id": "why",
                                "type": "text",
                                "prompt": "Why?",
                                "show_if": {"question": "pick", "equals": "a"},
                            },
                        ],
                    }
                ]
            )
        )
        html = render.render(spec)
        self.assertIn('"why"', html)
        self.assertIn("data-show-if", html)


if __name__ == "__main__":
    unittest.main()
