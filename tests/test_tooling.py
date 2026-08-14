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

from qsurface import config, paths, render, spec as spec_mod, store  # noqa: E402

from test_qsurface import minimal  # noqa: E402


class TestProjectPaths(unittest.TestCase):
    """State follows the project being worked on, not the installed tool."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve()
        self.addCleanup(self.tmp.cleanup)
        # QSURFACE_PROJECT would short-circuit the discovery being tested.
        patcher = mock.patch.dict(os.environ, {}, clear=False)
        patcher.start()
        os.environ.pop("QSURFACE_PROJECT", None)
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
            paths.responses_dir(nested), self.root / ".question-surface" / "responses"
        )
        self.assertEqual(
            paths.questionnaires_dir(nested),
            self.root / ".question-surface" / "questionnaires",
        )

    def test_environment_override_wins(self):
        with mock.patch.dict(os.environ, {"QSURFACE_PROJECT": str(self.root)}):
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
