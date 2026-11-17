import io
import unittest
from unittest import mock

from yojobs import progress


class FakeTTY(io.StringIO):
    def isatty(self):
        return True


class Progress(unittest.TestCase):
    def run_messages(self, verbose, stream):
        progress.set_verbose(verbose)
        with mock.patch("sys.stderr", stream):
            progress.step("[1/2] remotive")
            progress.say("    page 1")
            progress.step("[2/2] jobicy")
            progress.note("jobicy: ERROR boom")
            progress.end()
            progress.note("3 matches, 1 not sent before")
        progress.set_verbose(False)
        return stream.getvalue()

    def test_verbose_one_line_per_message(self):
        out = self.run_messages(True, io.StringIO())
        self.assertEqual(out.count("\n"), 5)
        self.assertNotIn("\r", out)
        self.assertIn("page 1", out)

    def test_quiet_terminal_redraws_one_line(self):
        out = self.run_messages(False, FakeTTY())
        self.assertIn("\r\033[K[1/2] remotive", out)
        self.assertIn("[1/2] remotive · page 1", out)      # detail joins the status line
        self.assertEqual(out.count("\n"), 2)                # only the two notes get lines
        self.assertTrue(out.endswith("3 matches, 1 not sent before\n"))

    def test_quiet_not_a_terminal_prints_only_notes(self):
        out = self.run_messages(False, io.StringIO())
        self.assertNotIn("\r", out)
        self.assertNotIn("remotive", out)
        self.assertEqual(out.count("\n"), 2)


if __name__ == "__main__":
    unittest.main()
