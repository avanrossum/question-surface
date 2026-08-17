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
import traceback
import unittest
from pathlib import Path
from unittest import mock

import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from qsurface import interview, paths, spec as spec_mod, store  # noqa: E402


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

    def respondent(self, fn) -> threading.Thread:
        """Run the answering side in a thread, surfacing anything it raises.

        A helper thread that dies quietly shows up in the main thread as a
        timeout with no cause, which is how a missing import once looked like
        a deadlock.
        """
        errors: list[str] = []

        def wrapped():
            try:
                fn()
            except BaseException:                     # noqa: BLE001
                errors.append(traceback.format_exc())

        thread = threading.Thread(target=wrapped, daemon=True)
        thread.start()
        self.addCleanup(
            lambda: self.assertFalse(errors, "respondent thread raised:\n" + "".join(errors))
        )
        return thread

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


class TestSelections(InterviewTestCase):
    """A chip is a selection, recorded apart from whatever was typed."""

    def _reply(self, session, text, picks, skipped=False):
        for _ in range(200):
            if session.pending:
                session.answer(session.pending["seq"], text, skipped, picks)
                return
            time.sleep(0.005)

    def test_selection_and_prose_are_both_recorded(self):
        session = interview.Session(self.record())
        threading.Thread(
            target=lambda: self._reply(session, "and here is why", ["Option A"]),
            daemon=True,
        ).start()
        answer = session.ask({"prompt": "Which?", "options": ["Option A", "B"]}, 5)
        self.assertEqual(answer["selected"], ["Option A"])
        self.assertEqual(answer["answer"], "and here is why")

    def test_a_selection_alone_is_an_answer(self):
        session = interview.Session(self.record())
        threading.Thread(
            target=lambda: self._reply(session, "", ["Option A"]), daemon=True
        ).start()
        answer = session.ask({"prompt": "Which?", "options": ["Option A", "B"]}, 5)
        self.assertEqual(answer["selected"], ["Option A"])
        self.assertFalse(answer["skipped"])

    def test_several_selections_are_kept_in_order(self):
        session = interview.Session(self.record())
        threading.Thread(
            target=lambda: self._reply(session, "", ["B", "A"]), daemon=True
        ).start()
        answer = session.ask({"prompt": "Which?", "options": ["A", "B"]}, 5)
        self.assertEqual(answer["selected"], ["B", "A"])

    def test_a_skip_carries_no_selection(self):
        session = interview.Session(self.record())
        threading.Thread(
            target=lambda: self._reply(session, "", [], True), daemon=True
        ).start()
        answer = session.ask({"prompt": "Which?", "options": ["A", "B"]}, 5)
        self.assertTrue(answer["skipped"])
        self.assertEqual(answer["selected"], [])

    def test_markdown_shows_the_selection_above_the_prose(self):
        record = self.record()
        record["exchanges"] = [
            {"seq": 1, "prompt": "Which?", "selected": ["Option A"],
             "answer": "because of X", "skipped": False}
        ]
        markdown = interview.transcript_markdown(record)
        self.assertIn("**Option A**", markdown)
        self.assertIn("because of X", markdown)
        self.assertLess(
            markdown.index("**Option A**"), markdown.index("because of X")
        )


class TestQuestionContext(InterviewTestCase):
    def test_context_is_rendered_once_when_the_question_is_posted(self):
        session = interview.Session(self.record())
        threading.Thread(
            target=lambda: self._answer_when_pending(session), daemon=True
        ).start()
        session.ask(
            {"prompt": "Which?", "context": "Some **reasoning**.\n\n- a bullet"},
            timeout=5,
        )
        # The rendered form travels to the browser; the source is what is kept.
        exchange = session.record["exchanges"][0]
        self.assertNotIn("context_html", exchange)
        self.assertIn("**reasoning**", exchange["context"])

    def _answer_when_pending(self, session):
        for _ in range(200):
            if session.pending:
                self.assertIn("<strong>reasoning</strong>", session.pending["context_html"])
                self.assertIn("<li>", session.pending["context_html"])
                session.answer(session.pending["seq"], "ok", False, [])
                return
            time.sleep(0.005)


class TestFollowUpHandoff(InterviewTestCase):
    """An interview that ends with real forks offers the form in the same tab."""

    SURVEY = {
        "id": "followup",
        "title": "Pinning it down",
        "sections": [
            {
                "title": "Decisions",
                "questions": [
                    {"id": "shape", "type": "text", "prompt": "Which shape?"}
                ],
            }
        ],
    }

    def spec(self) -> dict:
        return spec_mod.validate(json.loads(json.dumps(self.SURVEY)))

    def wait_for(self, predicate, tries=200):
        for _ in range(tries):
            if predicate():
                return True
            time.sleep(0.005)
        return False

    def test_holding_is_announced_once_then_the_poll_blocks(self):
        session = interview.Session(self.record())
        session.hold()
        self.assertTrue(session.wait_for_question(0, "")["holding"])
        # Announcing it on every poll would make the long-poll a busy loop.
        with mock.patch.object(interview, "POLL_SECONDS", 0.2):
            self.assertTrue(session.wait_for_question(0, "holding").get("waiting"))

    def test_hold_writes_the_transcript(self):
        session = interview.Session(self.record())
        session.hold()
        self.assertTrue(list((paths.responses_dir() / "t").glob("*.json")))

    def test_an_accepted_offer_returns_where_the_answers_went(self):
        session = interview.Session(self.record())
        result = {}

        def respondent():
            self.assertTrue(self.wait_for(lambda: session.phase == "offering"))
            self.assertTrue(session.respond_to_offer(True))
            response = store.build_response(self.spec(), {"shape": {"value": "a"}})
            written = store.write(paths.responses_dir(), self.spec(), response)
            session.record_survey(written, response)

        self.respondent(respondent)
        result = session.make_offer(self.spec(), "two things", timeout=5)

        self.assertEqual(result["outcome"], "taken")
        self.assertIn("followup", result["json"])
        self.assertEqual(result["counts"]["answered"], 1)

    def test_a_declined_offer_says_so_and_asks_nothing_further(self):
        session = interview.Session(self.record())

        def respondent():
            self.assertTrue(self.wait_for(lambda: session.phase == "offering"))
            session.respond_to_offer(False)

        self.respondent(respondent)
        result = session.make_offer(self.spec(), "", timeout=5)
        self.assertEqual(result["outcome"], "declined")

    def test_the_transcript_records_the_handoff_either_way(self):
        taken = interview.Session(self.record())

        def accept():
            self.assertTrue(self.wait_for(lambda: taken.phase == "offering"))
            taken.respond_to_offer(True)
            response = store.build_response(self.spec(), {"shape": {"value": "a"}})
            taken.record_survey(
                store.write(paths.responses_dir(), self.spec(), response), response
            )

        self.respondent(accept)
        taken.make_offer(self.spec(), "", timeout=5)
        document = json.loads(
            sorted((paths.responses_dir() / "t").glob("*.json"))[-1].read_text()
        )
        self.assertTrue(document["followup"]["taken"])
        self.assertEqual(document["followup"]["questionnaire_id"], "followup")
        self.assertIn("Followed by", interview.transcript_markdown(taken.record))

    def test_a_declined_handoff_is_recorded_as_offered(self):
        session = interview.Session(self.record())
        self.respondent(
            lambda: (
                self.wait_for(lambda: session.phase == "offering"),
                session.respond_to_offer(False),
            )
        )
        session.make_offer(self.spec(), "", timeout=5)
        self.assertEqual(session.record["followup"], {"offered": True, "taken": False})
        self.assertIn("offered and declined", interview.transcript_markdown(session.record))

    def test_the_offer_can_only_be_answered_once(self):
        session = interview.Session(self.record())
        self.respondent(lambda: session.make_offer(self.spec(), "", 5))
        self.assertTrue(self.wait_for(lambda: session.phase == "offering"))
        self.assertTrue(session.respond_to_offer(False))
        # A second tab, or a double click, must not reopen a settled offer.
        self.assertFalse(session.respond_to_offer(True))

    def test_an_offer_that_is_never_answered_gives_up(self):
        session = interview.Session(self.record())
        result = session.make_offer(self.spec(), "", timeout=0.3)
        self.assertEqual(result["outcome"], "no answer")

    def test_the_survey_phase_is_announced_to_a_reloaded_page(self):
        # Accepting, then reloading, must land back on the form rather than on
        # an offer that has already been taken.
        session = interview.Session(self.record())
        self.respondent(lambda: session.make_offer(self.spec(), "", 5))
        self.assertTrue(self.wait_for(lambda: session.phase == "offering"))
        session.respond_to_offer(True)
        self.assertTrue(session.wait_for_question(0, "")["survey"])
