import re
import unittest
from pathlib import Path

from yojobs import __version__
from yojobs.http import USER_AGENT

ROOT = Path(__file__).resolve().parent.parent


class Version(unittest.TestCase):
    def test_semver(self):
        self.assertRegex(__version__, r"^\d+\.\d+\.\d+$")

    def test_changelog_has_this_version(self):
        self.assertIn(f"## v{__version__} ", (ROOT / "CHANGELOG.md").read_text())

    def test_user_agent(self):
        self.assertIn(f"yojobs/{__version__}", USER_AGENT)


if __name__ == "__main__":
    unittest.main()
