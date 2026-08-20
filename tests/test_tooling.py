"""Tests for path resolution, per-user config, spec versioning and follow-ups.

Run: python3 -m unittest discover -s tests -t .
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from docket import config, paths, render, spec as spec_mod, store  # noqa: E402

from test_docket import minimal  # noqa: E402


class TestProjectPaths(unittest.TestCase):
    """State follows the project being worked on, not the installed tool."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve()
        self.addCleanup(self.tmp.cleanup)
        # DOCKET_PROJECT would short-circuit the discovery being tested.
        patcher = mock.patch.dict(os.environ, {}, clear=False)
        patcher.start()
        os.environ.pop("DOCKET_PROJECT", None)
        self.addCleanup(patcher.stop)

    def test_repository_root_is_found_from_a_subdirectory(self):
        (self.root / ".git").mkdir()
        nested = self.root / "src" / "deep"
        nested.mkdir(parents=True)
        self.assertEqual(paths.project_root(nested), self.root)

    def test_falls_back_to_the_working_directory_outside_a_repository(self):
        loose = self.root / "scratch"
        loose.mkdir()
        self.assertEqual(paths.project_root(loose), loose)

    def test_state_lives_under_the_project_root(self):
        (self.root / ".git").mkdir()
        nested = self.root / "a" / "b"
        nested.mkdir(parents=True)
        # Running from a subdirectory must not create a second state directory.
        self.assertEqual(
            paths.responses_dir(nested), self.root / ".docket" / "responses"
        )
        self.assertEqual(
            paths.questionnaires_dir(nested),
            self.root / ".docket" / "questionnaires",
        )

    def test_environment_override_wins(self):
        with mock.patch.dict(os.environ, {"DOCKET_PROJECT": str(self.root)}):
            self.assertEqual(paths.project_root(Path("/")), self.root)

    def test_search_path_puts_the_project_before_the_bundle(self):
        (self.root / ".git").mkdir()
        search = paths.search_path(self.root)
        self.assertEqual(search[0], paths.questionnaires_dir(self.root))
        self.assertIn(paths.BUNDLED_QUESTIONNAIRES, search)

    def test_search_path_does_not_repeat_the_bundle(self):
        # Running the tool inside its own clone must not list the same
        # directory twice, which would report every questionnaire as shadowed.
        search = paths.search_path(paths.TOOL_ROOT)
        self.assertEqual(len(search), len(set(search)))


class TestConfig(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        patcher = mock.patch.dict(
            os.environ, {"XDG_CONFIG_HOME": self.tmp.name}, clear=False
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_defaults_apply_with_no_file(self):
        self.assertEqual(config.load()["gate"], 5)
        self.assertEqual(config.get("timeout_minutes"), 120)

    def test_set_persists_and_reloads(self):
        path = config.set_value("gate", 3)
        self.assertTrue(path.exists())
        self.assertEqual(config.get("gate"), 3)
        # Untouched settings keep their defaults rather than disappearing.
        self.assertEqual(config.get("timeout_minutes"), 120)

    def test_unknown_setting_rejected(self):
        with self.assertRaises(KeyError):
            config.set_value("colour", 1)

    def test_corrupt_config_falls_back_to_defaults(self):
        path = config.config_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{not json")
        self.assertEqual(config.load()["gate"], 5)

    def test_unknown_keys_in_the_file_are_ignored(self):
        path = config.config_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"gate": 2, "nonsense": True}))
        settings = config.load()
        self.assertEqual(settings["gate"], 2)
        self.assertNotIn("nonsense", settings)

    def test_gate_sentence_reflects_the_setting(self):
        config.set_value("gate", 7)
        self.assertIn("7 or more", config.gate_sentence())

    def test_zero_gate_reads_as_no_floor(self):
        self.assertIn("no fixed question count", config.gate_sentence(0))


class TestSpecVersion(unittest.TestCase):
    def test_absent_version_defaults_to_one(self):
        # Every questionnaire authored before the field existed keeps loading.
        result = spec_mod.validate(minimal())
        self.assertEqual(result["spec_version"], 1)

    def test_current_version_accepted(self):
        spec_mod.validate(minimal(spec_version=spec_mod.SPEC_VERSION))

    def test_future_version_refused_rather_than_guessed_at(self):
        with self.assertRaisesRegex(spec_mod.SpecError, "newer than this tool"):
            spec_mod.validate(minimal(spec_version=spec_mod.SPEC_VERSION + 1))

    def test_nonsense_version_rejected(self):
        for bad in ("1", 0, -1, True, 1.5):
            with self.assertRaises(spec_mod.SpecError):
                spec_mod.validate(minimal(spec_version=bad))

    def test_follows_must_be_a_string(self):
        with self.assertRaisesRegex(spec_mod.SpecError, "'follows'"):
            spec_mod.validate(minimal(follows=["a", "b"]))


class TestFollowUpPanel(unittest.TestCase):
    """A follow-up round shows what the previous one settled."""

    def setUp(self):
        self.spec = spec_mod.validate(minimal(follows="earlier"))
        earlier = spec_mod.validate(
            minimal(
                sections=[
                    {
                        "title": "S",
                        "questions": [
                            {
                                "id": "shape",
                                "type": "single",
                                "prompt": "Which shape?",
                                "options": [
                                    {"value": "custom", "label": "Custom objects"},
                                    {"value": "standard", "label": "Standard"},
                                ],
                            },
                            {
                                "id": "when",
                                "type": "text",
                                "prompt": "By when?",
                            },
                            {
                                "id": "unasked",
                                "type": "text",
                                "prompt": "Never shown",
                                "show_if": {"question": "shape", "equals": "standard"},
                            },
                        ],
                    }
                ]
            )
        )
        self.prior = store.build_response(
            earlier, {"shape": {"value": "custom"}}
        )

    def test_prior_answers_are_rendered(self):
        html = render.render(self.spec, prior=self.prior)
        self.assertIn("Already decided", html)
        self.assertIn("Which shape?", html)
        self.assertIn("Custom objects", html)

    def test_unanswered_and_skipped_prior_questions_are_left_out(self):
        html = render.render(self.spec, prior=self.prior)
        # "By when?" was left blank and "Never shown" was never reachable;
        # restating either as a decision would be a lie.
        self.assertNotIn("By when?", html)
        self.assertNotIn("Never shown", html)

    def test_unknown_prior_answers_are_kept_as_open_items(self):
        prior = store.build_response(self.spec, {"pick": {"unknown": True}})
        html = render.render(self.spec, prior=prior)
        self.assertIn("needs research", html)

    def test_no_panel_without_a_prior_response(self):
        self.assertNotIn("Already decided", render.render(self.spec))
        self.assertNotIn("Already decided", render.render(self.spec, prior={}))

    def test_prior_text_is_escaped(self):
        prior = store.build_response(
            self.spec, {"pick": {"value": "alpha", "notes": "x"}}
        )
        prior["answers"]["pick"]["prompt"] = "<script>alert(1)</script>"
        html = render.render(self.spec, prior=prior)
        self.assertNotIn("<script>alert(1)</script>", html)


if __name__ == "__main__":
    unittest.main()


class TestRichContext(unittest.TestCase):
    """The context block carries reasoning, which is often a table or a list."""

    def test_paragraphs(self):
        html = render.rich("First para.\n\nSecond para.")
        self.assertEqual(html.count("<p>"), 2)

    def test_bullets(self):
        html = render.rich("- one\n- two")
        self.assertIn("<ul><li>one</li><li>two</li></ul>", html)

    def test_pipe_table(self):
        html = render.rich("| A | B |\n|---|---|\n| 1 | 2 |")
        self.assertIn("<table", html)
        self.assertIn("<th>A</th>", html)
        self.assertIn("<td>2</td>", html)

    def test_inline_formatting_inside_blocks(self):
        self.assertIn("<strong>bold</strong>", render.rich("a **bold** word"))
        self.assertIn("<code>x</code>", render.rich("- uses `x`"))

    def test_everything_is_escaped_first(self):
        html = render.rich("<script>alert(1)</script>\n\n| <b> |\n|---|\n| <i> |")
        self.assertNotIn("<script>", html)
        self.assertNotIn("<b>", html)
        self.assertIn("&lt;script&gt;", html)

    def test_empty_context_renders_nothing(self):
        self.assertEqual(render.rich(""), "")
        self.assertEqual(render.rich(None), "")

    def test_a_table_needs_its_divider(self):
        # Without the divider row it is prose that happens to contain pipes.
        html = render.rich("| not | a table |")
        self.assertNotIn("<table", html)


class TestFollowsAnInterview(unittest.TestCase):
    """A distilled questionnaire follows the interview it came from."""

    def setUp(self):
        self.spec = spec_mod.validate(minimal(follows="chat"))
        self.transcript = {
            "kind": "interview",
            "title": "A conversation",
            "submitted_at": "2026-08-14T00:00:00Z",
            "exchanges": [
                {"seq": 1, "prompt": "What broke?", "answer": "sessions dropped",
                 "selected": ["Reliability"], "skipped": False},
                {"seq": 2, "prompt": "Never shown", "answer": "", "skipped": True},
                {"seq": 3, "prompt": "Blank one", "answer": "", "selected": [],
                 "skipped": False},
            ],
        }

    def test_interview_answers_render_in_the_prior_panel(self):
        html = render.render(self.spec, prior=self.transcript)
        self.assertIn("Already decided", html)
        self.assertIn("What broke?", html)
        self.assertIn("sessions dropped", html)
        self.assertIn("Reliability", html)

    def test_skipped_and_empty_exchanges_are_left_out(self):
        html = render.render(self.spec, prior=self.transcript)
        self.assertNotIn("Never shown", html)
        self.assertNotIn("Blank one", html)


class TestGatePointerAdvice(unittest.TestCase):
    """The CLAUDE.md line is only needed when the gate is not the default.

    The skill states the default in its own text, so a fresh install needs no
    pointer — and telling every new user their working install has a failure is
    worse than saying nothing.
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        patcher = mock.patch.dict(
            os.environ, {"XDG_CONFIG_HOME": self.tmp.name}, clear=False
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def run_doctor(self) -> str:
        import subprocess

        root = Path(__file__).resolve().parent.parent
        result = subprocess.run(
            [sys.executable, str(root / "bin" / "docket"), "doctor"],
            capture_output=True,
            text=True,
            env=dict(os.environ, XDG_CONFIG_HOME=self.tmp.name),
            timeout=60,
        )
        return result.stdout

    def test_a_default_gate_needs_no_pointer(self):
        out = self.run_doctor()
        line = [l for l in out.splitlines() if "gate pointer" in l][0]
        self.assertIn("ok", line)
        self.assertIn("not needed", out)

    def test_a_changed_gate_asks_for_the_pointer(self):
        config.set_value("gate", 3)
        out = self.run_doctor()
        line = [l for l in out.splitlines() if "gate pointer" in l][0]
        self.assertIn("FAIL", line)
        self.assertIn("your gate is 3", out)
