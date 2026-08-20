#!/usr/bin/env python3
"""Tests for `claude-speak again` — reading the last reply back.

    python3 -m unittest discover tests

The reply is kept by the Stop hook rather than dug out of Claude Code's
transcript afterwards: what gets stored is the text that was actually spoken,
already cleaned and already cut to maxChars, so a repeat is the same words
rather than nearly the same words. One file per project, keyed by the label
play and clear use.

Nothing here plays audio: notify is off, which stops the hook before the ding,
and the meeting guard is off so it never shells out to pactl.
"""

import json
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import cspaths  # noqa: E402

HOOK = os.path.join(ROOT, "scripts", "speak-hook.py")
CLI = os.path.join(ROOT, "scripts", "csconfig.py")


class Base(unittest.TestCase):

    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.cfg = os.path.join(self.dir, "config.json")
        self.env = dict(os.environ,
                        CLAUDE_SPEAK_HOME=self.dir,
                        CLAUDE_SPEAK_CONFIG=self.cfg)
        self.write_cfg({})

    def write_cfg(self, extra):
        base = {"notify": False, "meetingGuard": False, "holdSound": "off"}
        base.update(extra)
        with open(self.cfg, "w") as fh:
            json.dump(base, fh)

    def reply(self, text, cwd="/tmp/some-project"):
        payload = json.dumps({"session_id": "s", "cwd": cwd,
                              "last_assistant_message": text})
        return subprocess.run([sys.executable, HOOK], input=payload,
                              capture_output=True, text=True, env=self.env)

    def last(self, label):
        return subprocess.run([sys.executable, CLI, "last", "get", label],
                              capture_output=True, text=True, env=self.env)


class Remembering(Base):

    def test_the_reply_is_kept_under_the_project_name(self):
        self.reply("All nineteen tests pass.")
        self.assertEqual(self.last("some-project").stdout, "All nineteen tests pass.")

    def test_what_is_kept_is_what_was_spoken(self):
        """Cleaned, not raw: a repeat must not read the markdown aloud."""
        self.reply("# Heading\n\n- first\n- second\n\n```py\nx = 1\n```")
        said = self.last("some-project").stdout
        self.assertNotIn("#", said)
        self.assertNotIn("```", said)
        self.assertIn("Code block", said)

    def test_the_maxChars_cut_is_kept_too(self):
        self.write_cfg({"maxChars": 40})
        self.reply("This sentence is quite long. " * 6)
        said = self.last("some-project").stdout
        self.assertTrue(said.endswith("Rest is on screen."), said)

    def test_the_newest_reply_wins(self):
        self.reply("first")
        self.reply("second")
        self.assertEqual(self.last("some-project").stdout, "second")

    def test_projects_do_not_share(self):
        self.reply("from api", cwd="/tmp/api-server")
        self.reply("from web", cwd="/tmp/web-client")
        self.assertEqual(self.last("api-server").stdout, "from api")
        self.assertEqual(self.last("web-client").stdout, "from web")

    def test_held_replies_are_kept_as_well(self):
        """Hold mode means you have not heard it yet — again still applies."""
        self.write_cfg({"holdReplies": True})
        self.reply("stashed, not spoken")
        self.assertEqual(self.last("some-project").stdout, "stashed, not spoken")

    def test_nothing_is_kept_while_switched_off(self):
        self.write_cfg({"enabled": False})
        self.reply("never spoken")
        self.assertEqual(self.last("some-project").returncode, 1)

    def test_an_empty_reply_leaves_no_trace(self):
        self.reply("")
        self.assertEqual(self.last("some-project").returncode, 1)


class Asking(Base):

    def test_a_project_never_heard_from_fails_quietly(self):
        out = self.last("never-seen")
        self.assertEqual(out.returncode, 1)
        self.assertEqual(out.stdout, "")

    def test_drop_forgets_it(self):
        self.reply("something")
        subprocess.run([sys.executable, CLI, "last", "drop", "some-project"],
                       capture_output=True, env=self.env)
        self.assertEqual(self.last("some-project").returncode, 1)

    def test_dropping_nothing_is_not_an_error(self):
        out = subprocess.run([sys.executable, CLI, "last", "drop", "never-seen"],
                             capture_output=True, env=self.env)
        self.assertEqual(out.returncode, 0)

    def test_an_unknown_action_says_so(self):
        out = subprocess.run([sys.executable, CLI, "last", "sing"],
                             capture_output=True, text=True, env=self.env)
        self.assertEqual(out.returncode, 2)
        self.assertIn("unknown last action", out.stderr)


class LabelsAreFilenames(unittest.TestCase):
    """A project name is a directory basename and can hold anything."""

    def test_a_traversal_cannot_escape(self):
        for label in ("..", "../..", "."):
            with self.subTest(label):
                self.assertEqual(os.path.dirname(cspaths.last_file(label)),
                                 cspaths.LAST)

    def test_awkward_names_still_get_a_file(self):
        self.assertTrue(cspaths.last_file("my project").endswith("my_project.txt"))
        self.assertTrue(cspaths.last_file("").endswith("claude.txt"))


if __name__ == "__main__":
    unittest.main()
