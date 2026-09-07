"""Where the pipeline looks for things.

The pipeline and the curriculum are separate repositories, so every path
that refers to *content* has to resolve against the data root rather than
against the pipeline checkout. Getting one wrong is quiet rather than
loud: the lint baseline resolved against the pipeline root simply found
no baseline, made all 372 known violations look new, and turned the whole
check into noise that still exited zero locally.
"""

from __future__ import annotations

import importlib
import os
import sys
import tempfile
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))


class DataRootTestCase(unittest.TestCase):
    def _reload(self, data_root: str | None):
        """Re-import the model with STPAUL_DATA set to a given value."""
        old = os.environ.get("STPAUL_DATA")
        if data_root is None:
            os.environ.pop("STPAUL_DATA", None)
        else:
            os.environ["STPAUL_DATA"] = data_root
        try:
            import stpaul.model as m
            return importlib.reload(m)
        finally:
            if old is None:
                os.environ.pop("STPAUL_DATA", None)
            else:
                os.environ["STPAUL_DATA"] = old

    def test_env_var_wins(self):
        with tempfile.TemporaryDirectory() as td:
            m = self._reload(td)
            self.assertEqual(m.DATA_ROOT, Path(td).resolve())
            for attr in ("CONTENT_DIR", "APPROVALS_DIR", "STANDARDS_DIR", "DIST_DIR"):
                self.assertTrue(
                    str(getattr(m, attr)).startswith(str(Path(td).resolve())),
                    f"{attr} does not follow the data root")

    def test_content_paths_never_point_into_the_pipeline(self):
        """The pipeline holds no curriculum, so nothing may resolve into it."""
        with tempfile.TemporaryDirectory() as td:
            m = self._reload(td)
            pipeline = TOOLS.parent
            for attr in ("CONTENT_DIR", "APPROVALS_DIR", "STANDARDS_DIR",
                         "ARCHIVE_DIR", "DIST_DIR"):
                self.assertFalse(
                    str(getattr(m, attr)).startswith(str(pipeline)),
                    f"{attr} resolves inside the pipeline checkout")

    def test_lint_baseline_follows_the_data_root(self):
        """The regression that prompted this file."""
        with tempfile.TemporaryDirectory() as td:
            self._reload(td)
            import lint
            importlib.reload(lint)
            self.assertEqual(lint.BASELINE_PATH.parent,
                             Path(td).resolve() / "standards")

    def test_drift_scratch_paths_follow_the_data_root(self):
        with tempfile.TemporaryDirectory() as td:
            self._reload(td)
            import drift
            importlib.reload(drift)
            for p in (drift.SNAPSHOT, drift.OCR_DIR):
                self.assertTrue(str(p).startswith(str(Path(td).resolve())), p)

    def tearDown(self):
        # Leave the modules resolved the way the rest of the suite expects.
        self._reload(os.environ.get("STPAUL_DATA"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
