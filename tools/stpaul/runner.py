"""Where the pipeline runs, and what a tool does when it is run anywhere else.

The pipeline runs on GitHub Actions. Fetching Scripture, refreshing the
review data, building and publishing are workflows, and each runs because
something happened: a push, an approval, a schedule. None of them runs
because someone remembered to, and nobody should be asked to run one.

This is not tidiness. A step that needs a key, a network or a particular
machine, done by hand, turns into a request to a person. When the ESV fetch
could not reach Crossway from a drafting session, the result was an email
asking the pastor to change a network policy, register an API key and set
an environment variable. None of that was the pastor's to do. On a runner
the network is open and the key is a secret.

So a tool whose job belongs to a workflow checks where it is. Anywhere but
a runner, it stops and says what does the job instead. --local lets the
maintainer work on the tool itself. It is not a shortcut, and it is never
something to tell a pastor or a reviewer to use.
"""

from __future__ import annotations

import argparse
import os


def on_runner() -> bool:
    """True on GitHub Actions, which sets GITHUB_ACTIONS=true on every runner."""
    return os.environ.get("GITHUB_ACTIONS") == "true"


def add_local_flag(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--local", action="store_true",
        help="run outside GitHub Actions. For working on this tool, never "
             "a way to do the workflow's job by hand")


def refusal(tool: str, instead: str, local: bool) -> str | None:
    """Why this run should not happen here, or None when it may."""
    if local or on_runner():
        return None
    return (
        f"{tool} is not run by hand. {instead}\n"
        f"If that has not happened, the workflow or its settings need looking "
        f"at, which is the maintainer's job. Nobody else needs to install, "
        f"configure or run anything.\n"
        f"Working on {tool} itself? Add --local."
    )
