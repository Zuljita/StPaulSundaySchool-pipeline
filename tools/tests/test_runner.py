"""Tools whose job belongs to a workflow refuse to run anywhere else.

The refusal is the point, so it is tested from outside: each tool's main(),
off a runner, returns 2 and says what does the job, before it reads or
writes anything. GITHUB_ACTIONS=true, which every runner sets, lets it
through, and so does --local, which is for working on the tool itself.
"""

from __future__ import annotations

import contextlib
import importlib
import io
import os
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from stpaul import runner  # noqa: E402

GUARDED = {
    "fetch_scripture": ["fetch_scripture.py", "--all"],
    "make_review": ["make_review.py"],
    "publish_site": ["publish_site.py"],
    "publish_r2": ["publish_r2.py"],
    "approve": ["approve.py", "2026-01-04-test", "--reviewer", "A Reviewer"],
}


def off_a_runner():
    env = {k: v for k, v in os.environ.items() if k != "GITHUB_ACTIONS"}
    return mock.patch.dict(os.environ, env, clear=True)


class RunnerTestCase(unittest.TestCase):

    def test_off_a_runner_it_refuses_and_says_what_does_the_job(self):
        with off_a_runner():
            self.assertFalse(runner.on_runner())
            message = runner.refusal("tool.py", "A workflow does it.", local=False)
        self.assertIn("tool.py is not run by hand. A workflow does it.", message)
        self.assertIn("--local", message)

    def test_on_a_runner_it_may_run(self):
        with mock.patch.dict(os.environ, {"GITHUB_ACTIONS": "true"}):
            self.assertIsNone(runner.refusal("tool.py", "A workflow does it.", local=False))

    def test_local_lets_the_maintainer_work_on_it(self):
        with off_a_runner():
            self.assertIsNone(runner.refusal("tool.py", "A workflow does it.", local=True))

    def test_every_guarded_tool_stops_before_doing_anything(self):
        for name, argv in GUARDED.items():
            with self.subTest(tool=name):
                module = importlib.import_module(name)
                err = io.StringIO()
                with off_a_runner(), mock.patch.object(sys, "argv", argv), \
                        contextlib.redirect_stderr(err):
                    code = module.main()
                self.assertEqual(code, 2)
                self.assertIn("is not run by hand", err.getvalue())

    def test_the_refusal_asks_nothing_of_anyone_but_the_maintainer(self):
        """Nobody is told to install, configure or run anything."""
        with off_a_runner():
            message = runner.refusal("tool.py", "A workflow does it.", local=False)
        self.assertIn("Nobody else needs to install, configure or run anything", message)
        self.assertNotIn("pastor", message.lower())


if __name__ == "__main__":
    unittest.main()
