"""Tests for `docket interview distill`.

Driven through the CLI rather than by importing it: `bin/docket` runs the same code the console script does; it shares its
name with the `docket` package, so the package wins any plain import, and
running the command is the truer test anyway.

The fixture is shaped from a real transcript — `build-retro`, tracked in this
repo — rather than invented, so the assertions describe what the tool actually
produces from a conversation.

Run: python3 -m unittest discover -s tests -t .
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from docket import spec as spec_mod  # noqa: E402

TRANSCRIPT = {
    "interview_id": "retro",
    "title": "Building it in a day — retro",
    "kind": "interview",
    "domain": "engineering retrospective",
    "respondent": "Alex",
    "started_at": "2026-08-16T04:46:56Z",
    "ended_at": "2026-08-16T05:08:00Z",
    "counts": {"asked": 4, "answered": 3, "skipped": 1},
    "exchanges": [
        {
            "seq": 1,
            "prompt": "What did you expect to have at the end?",
            "why": "A retro that starts with 'how did it go' gets a summary.",
            "answer": "One small thing, reusable across multiple spaces.",
            "selected": [],
            "skipped": False,
        },
        {
            "seq": 2,
            "prompt": "Is the value in not watching it form, or getting it whole?",
            "why": "It is currently an accident rather than a decision.",
            "answer": "The silence is doing work too.",
            "selected": ["Both, and they can't be separated"],
            "skipped": False,
        },
        {
            "seq": 3,
            "prompt": "Where did I waste your time?",
            "answer": "",
            "selected": [],
            "skipped": True,
        },
        {
            "seq": 4,
            "prompt": "Anything else?",
            "answer": "Two features fell out of the waiting.",
            "selected": [],
            "skipped": False,
        },
    ],
}


class DistillTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.project = Path(self.tmp.name).resolve()
        self.addCleanup(self.tmp.cleanup)
        directory = self.project / ".docket" / "responses" / "retro"
        directory.mkdir(parents=True)
        (directory / "2026-08-16T04-46-56Z.json").write_text(
            json.dumps(TRANSCRIPT), encoding="utf-8"
        )

    def distill(self, *args) -> subprocess.CompletedProcess:
        env = dict(os.environ, DOCKET_PROJECT=str(self.project))
        return subprocess.run(
            [sys.executable, str(ROOT / "bin" / "docket"), "interview", "distill", *args],
            capture_output=True,
            text=True,
            env=env,
            timeout=60,
        )

    def spec_at(self, questionnaire_id: str) -> dict:
        path = (
            self.project
            / ".docket"
            / "questionnaires"
            / f"{questionnaire_id}.json"
        )
        self.assertTrue(path.exists(), f"expected {path}")
        return json.loads(path.read_text(encoding="utf-8"))


class TestDistilledSpec(DistillTestCase):
    def test_it_writes_a_spec_that_validates(self):
        result = self.distill("retro")
        self.assertEqual(result.returncode, 0, result.stderr)
        # A scaffold that cannot be served is not a scaffold.
        spec_mod.validate(self.spec_at("retro-decisions"))

    def test_it_follows_the_interview_it_came_from(self):
        self.distill("retro")
        self.assertEqual(self.spec_at("retro-decisions")["follows"], "retro")

    def test_each_answered_exchange_becomes_context_plus_a_draft(self):
        self.distill("retro")
        questions = self.spec_at("retro-decisions")["sections"][0]["questions"]
        info = [q for q in questions if q["type"] == "info"]
        drafts = [q for q in questions if q["type"] != "info"]
        self.assertEqual(len(info), 3)      # the skipped one is left out
        self.assertEqual(len(drafts), 3)
        self.assertEqual(
            [q["id"] for q in drafts], ["decision-1", "decision-2", "decision-4"]
        )

    def test_the_material_travels_with_it(self):
        self.distill("retro")
        blob = json.dumps(self.spec_at("retro-decisions"))
        self.assertIn("One small thing, reusable across multiple spaces.", blob)
        self.assertIn("Both, and they can't be separated", blob)

    def test_every_question_is_marked_as_a_draft(self):
        # The tool cannot know which exchanges became decisions, and a question
        # that does not say so would be mistaken for one it wrote on purpose.
        self.distill("retro")
        drafts = [
            q
            for q in self.spec_at("retro-decisions")["sections"][0]["questions"]
            if q["type"] != "info"
        ]
        for question in drafts:
            self.assertIn("TODO", question["prompt"])
            self.assertIn("TODO", question["why"])

    def test_skipped_exchanges_are_left_out(self):
        self.distill("retro")
        self.assertNotIn(
            "Where did I waste your time?",
            json.dumps(self.spec_at("retro-decisions")),
        )

    def test_only_selects_exchanges(self):
        self.distill("retro", "--only", "2,4")
        drafts = [
            q
            for q in self.spec_at("retro-decisions")["sections"][0]["questions"]
            if q["type"] != "info"
        ]
        self.assertEqual([q["id"] for q in drafts], ["decision-2", "decision-4"])

    def test_selecting_only_a_skipped_exchange_fails_loudly(self):
        result = self.distill("retro", "--only", "3")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("nothing to distill", result.stderr)

    def test_out_names_the_questionnaire(self):
        self.distill("retro", "--out", "next-steps")
        self.assertEqual(self.spec_at("next-steps")["id"], "next-steps")


class TestDistillRefusals(DistillTestCase):
    def test_it_will_not_overwrite_without_force(self):
        self.assertEqual(self.distill("retro").returncode, 0)
        second = self.distill("retro")
        self.assertNotEqual(second.returncode, 0)
        self.assertIn("already exists", second.stderr)

    def test_force_overwrites(self):
        self.distill("retro")
        self.assertEqual(self.distill("retro", "--force").returncode, 0)

    def test_missing_interview_is_refused(self):
        result = self.distill("never-happened")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("no transcript", result.stderr)

    def test_out_must_be_an_id_not_a_path(self):
        # Joining an absolute path discards the base directory, so an unchecked
        # --out writes the spec anywhere on disk.
        for bad in ("/tmp/escaped", "../escaped", "with/slash"):
            result = self.distill("retro", "--out", bad)
            self.assertNotEqual(result.returncode, 0, bad)
            self.assertIn("not a questionnaire id", result.stderr)
        self.assertFalse(Path("/tmp/escaped.json").exists())

    def test_a_questionnaire_response_is_not_an_interview(self):
        directory = self.project / ".docket" / "responses" / "a-form"
        directory.mkdir(parents=True)
        (directory / "2026-08-16T00-00-00Z.json").write_text(
            json.dumps({"questionnaire_id": "a-form", "counts": {}, "answers": {}})
        )
        result = self.distill("a-form")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("not an interview transcript", result.stderr)


if __name__ == "__main__":
    unittest.main()
