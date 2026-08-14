"""Tests for interview mode.

The session state machine is exercised directly rather than over HTTP, so these
run in milliseconds. The server wiring and the page are covered by the live
round-trip in the browser checks.

Run: python3 -m unittest discover -s tests -t .
"""

from __future__ import annotations

import json
import os
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from qsurface import interview, paths  # noqa: E402


class InterviewTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve()
        self.addCleanup(self.tmp.cleanup)
        patcher = mock.patch.dict(
            os.environ, {"QSURFACE_PROJECT": str(self.root)}, clear=False
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def record(self, **overrides) -> dict:
        base = interview.new_record("t", "Test interview", "systems design", 8999)
        base.update(overrides)
        return base


class TestSessionFiles(InterviewTestCase):
    def test_session_round_trips(self):
        record = self.record()
        interview.write_session(record)
        self.assertEqual(interview.read_session("t")["token"], record["token"])

    def test_missing_session_explains_itself(self):
        with self.assertRaisesRegex(FileNotFoundError, "interview open"):
            interview.read_session("nope")

    def test_records_carry_a_token_and_are_not_predictable(self):
        first = interview.new_record("a", "A", "", 1)["token"]
        second = interview.new_record("a", "A", "", 1)["token"]
        self.assertNotEqual(first, second)
        self.assertGreater(len(first), 20)

    def test_session_state_lives_in_the_project(self):
        self.assertEqual(interview.sessions_dir(), paths.state_dir() / "interviews")


class TestExchangeFlow(InterviewTestCase):
    def test_ask_returns_the_answer_that_arrives(self):
        session = interview.Session(self.record())

        def respond():
            # Wait for the question to be posted, then answer it.
            for _ in range(200):
                if session.pending:
                    session.answer(session.pending["seq"], "  because of X  ", False)
                    return
                time.sleep(0.005)

        threading.Thread(target=respond, daemon=True).start()
        answer = session.ask({"prompt": "Why?"}, timeout=5)

        self.assertIsNotNone(answer)
        self.assertEqual(answer["answer"], "because of X")
        self.assertEqual(answer["seq"], 1)
        self.assertFalse(answer["skipped"])

    def test_sequence_numbers_increment(self):
        session = interview.Session(self.record())
        session.pending = None
        for expected in (1, 2, 3):
            threading.Thread(
                target=lambda: self._answer_when_pending(session), daemon=True
            ).start()
            answer = session.ask({"prompt": f"Q{expected}"}, timeout=5)
            self.assertEqual(answer["seq"], expected)

    def _answer_when_pending(self, session):
        for _ in range(200):
            if session.pending:
                session.answer(session.pending["seq"], "ok", False)
                return
            time.sleep(0.005)

    def test_a_skip_is_recorded_as_an_exchange(self):
        session = interview.Session(self.record())
        threading.Thread(
            target=lambda: self._skip_when_pending(session), daemon=True
        ).start()
        answer = session.ask({"prompt": "Anything else?"}, timeout=5)
        self.assertTrue(answer["skipped"])
        self.assertEqual(len(session.record["exchanges"]), 1)

    def _skip_when_pending(self, session):
        for _ in range(200):
            if session.pending:
                session.answer(session.pending["seq"], "", True)
                return
            time.sleep(0.005)

    def test_an_answer_for_the_wrong_question_is_refused(self):
        # A page left open from an earlier question must not answer a later one.
        session = interview.Session(self.record())
        threading.Thread(target=lambda: session.ask({"prompt": "Q"}, 2), daemon=True).start()
        for _ in range(200):
            if session.pending:
                break
            time.sleep(0.005)
        self.assertFalse(session.answer(99, "stale", False))
        self.assertEqual(session.record["exchanges"], [])

    def test_ask_gives_up_and_stops_presenting_the_question(self):
        session = interview.Session(self.record())
        started = time.monotonic()
        answer = session.ask({"prompt": "Unanswered"}, timeout=0.3)
        self.assertIsNone(answer)
        self.assertLess(time.monotonic() - started, 5)
        # Leaving it pending would show the respondent a question no one is
        # waiting on any more.
        self.assertIsNone(session.pending)

    def test_ask_after_close_returns_nothing(self):
        session = interview.Session(self.record())
        session.close()
        self.assertIsNone(session.ask({"prompt": "Too late"}, timeout=1))


class TestPolling(InterviewTestCase):
    def test_poll_reports_done_once_closed(self):
        session = interview.Session(self.record())
        session.close("all set")
        result = session.wait_for_question(after=0)
        self.assertTrue(result["done"])
        self.assertEqual(result["summary"], "all set")

    def test_poll_sees_a_pending_question(self):
        session = interview.Session(self.record())
        threading.Thread(target=lambda: session.ask({"prompt": "Hi"}, 5), daemon=True).start()
        for _ in range(200):
            if session.pending:
                break
            time.sleep(0.005)
        self.assertEqual(session.wait_for_question(after=0)["question"]["prompt"], "Hi")

    def test_poll_does_not_re_serve_a_question_already_seen(self):
        session = interview.Session(self.record())
        threading.Thread(target=lambda: session.ask({"prompt": "Hi"}, 5), daemon=True).start()
        for _ in range(200):
            if session.pending:
                break
            time.sleep(0.005)
        with mock.patch.object(interview, "POLL_SECONDS", 0.2):
            result = session.wait_for_question(after=1)
        self.assertTrue(result.get("waiting"))


class TestTranscript(InterviewTestCase):
    def test_transcript_is_written_after_every_answer_not_only_at_close(self):
        session = interview.Session(self.record())
        threading.Thread(
            target=lambda: self._answer(session, "first answer"), daemon=True
        ).start()
        session.ask({"prompt": "One?"}, timeout=5)

        written = list((paths.responses_dir() / "t").glob("*.json"))
        self.assertEqual(len(written), 1, "an interrupted interview must leave a record")
        document = json.loads(written[0].read_text())
        self.assertEqual(document["kind"], "interview")
        self.assertEqual(document["exchanges"][0]["answer"], "first answer")
        self.assertEqual(document["ended_at"], "")

    def _answer(self, session, text):
        for _ in range(200):
            if session.pending:
                session.answer(session.pending["seq"], text, False)
                return
            time.sleep(0.005)

    def test_close_stamps_the_end_and_returns_the_paths(self):
        session = interview.Session(self.record())
        written = session.close()
        self.assertIn("json", written)
        document = json.loads(Path(written["json"]).read_text())
        self.assertTrue(document["ended_at"])

    def test_closing_twice_does_not_rewrite_the_end_time(self):
        session = interview.Session(self.record())
        first = session.close()
        ended = json.loads(Path(first["json"]).read_text())["ended_at"]
        session.close()
        self.assertEqual(
            json.loads(Path(first["json"]).read_text())["ended_at"], ended
        )

    def test_markdown_shows_questions_answers_and_skips(self):
        record = self.record()
        record["exchanges"] = [
            {"seq": 1, "prompt": "What broke?", "why": "symptom first",
             "answer": "sessions drop", "skipped": False},
            {"seq": 2, "prompt": "Anything else?", "answer": "", "skipped": True},
        ]
        markdown = interview.transcript_markdown(record)
        self.assertIn("1. What broke?", markdown)
        self.assertIn("sessions drop", markdown)
        self.assertIn("*symptom first*", markdown)
        self.assertIn("Skipped.", markdown)
        self.assertIn("1 of 2 questions answered", markdown)
        self.assertIn("systems design", markdown)


if __name__ == "__main__":
    unittest.main()
