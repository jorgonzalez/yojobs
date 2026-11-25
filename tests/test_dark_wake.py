import argparse
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import yojobs.__main__ as main
from yojobs.schedule import dark_wake

FULL = "Current System Capabilities are: CPU Graphics Audio Network \nCurrent Power State: 4\n"
DARK = "Current System Capabilities are: CPU Network Disk \nCurrent Power State: 4\n"


def pmset(out):
    return lambda *a, **k: SimpleNamespace(stdout=out)


class DarkWake(unittest.TestCase):
    def test_reads_pmset(self):
        self.assertFalse(dark_wake(pmset(FULL)))
        self.assertTrue(dark_wake(pmset(DARK)))

    def test_unknown_never_blocks_runs(self):
        self.assertFalse(dark_wake(pmset("")))                      # odd output
        def missing(*a, **k):
            raise FileNotFoundError("pmset")
        self.assertFalse(dark_wake(missing))                        # not on macOS
        def slow(*a, **k):
            raise subprocess.TimeoutExpired("pmset", 10)
        self.assertFalse(dark_wake(slow))


class ScheduledRun(unittest.TestCase):
    def scheduled(self, dark, check_only=False):
        notes, runs = [], []
        args = argparse.Namespace(check_schedule=check_only)
        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.object(main, "ROOT", Path(tmp)), \
                mock.patch.object(main, "dark_wake", lambda: dark), \
                mock.patch.object(main, "is_due", lambda *a: (True, "first run today")), \
                mock.patch.object(main.logs, "trim_all", lambda cfg: []), \
                mock.patch.object(main, "note", notes.append), \
                mock.patch.object(main, "run", lambda *a, **k: runs.append(a) or (0, False)):
            code = main.scheduled(args, {}, SimpleNamespace(is_empty=lambda: True))
        return code, notes, runs

    def test_no_run_in_a_power_nap_wake(self):
        code, notes, runs = self.scheduled(dark=True)
        self.assertEqual((code, runs), (0, []))
        self.assertIn("Power Nap", notes[0])
        self.assertIn("not due", notes[0])

    def test_check_schedule_says_why(self):
        _, notes, runs = self.scheduled(dark=True, check_only=True)
        self.assertEqual(runs, [])
        self.assertIn("Scheduled run not due: the Mac is in a Power Nap wake", notes[0])

    def test_full_wake_runs(self):
        _, notes, runs = self.scheduled(dark=False)
        self.assertEqual(len(runs), 1)
        self.assertIn("Scheduled run starting", notes[0])


if __name__ == "__main__":
    unittest.main()
