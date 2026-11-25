import argparse
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import yojobs.__main__ as main
from yojobs.schedule import dark_wake, keep_awake, stop_awake

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


class KeepAwake(unittest.TestCase):
    def test_caffeinate_waits_for_this_process(self):
        import os
        calls = []
        proc = keep_awake(lambda cmd, **k: calls.append(cmd) or "proc")
        self.assertEqual(proc, "proc")
        self.assertEqual(calls, [["caffeinate", "-i", "-w", str(os.getpid())]])

    def test_missing_caffeinate(self):
        def missing(*a, **k):
            raise FileNotFoundError("caffeinate")
        self.assertIsNone(keep_awake(missing))
        stop_awake(None)                                            # nothing to stop

    def test_stop(self):
        proc = mock.Mock()
        stop_awake(proc)
        proc.terminate.assert_called_once()
        proc.wait.side_effect = subprocess.TimeoutExpired("caffeinate", 5)
        stop_awake(proc)                                            # never raises


class ScheduledRun(unittest.TestCase):
    def scheduled(self, dark, check_only=False, caffeinate=True):
        notes, runs, self.awake = [], [], []
        args = argparse.Namespace(check_schedule=check_only)
        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.object(main, "ROOT", Path(tmp)), \
                mock.patch.object(main, "dark_wake", lambda: dark), \
                mock.patch.object(main, "is_due", lambda *a: (True, "first run today")), \
                mock.patch.object(main.logs, "trim_all", lambda cfg: []), \
                mock.patch.object(main, "note", notes.append), \
                mock.patch.object(main, "keep_awake", lambda: self.awake.append("on") or ("proc" if caffeinate else None)), \
                mock.patch.object(main, "stop_awake", lambda p: self.awake.append(("off", p))), \
                mock.patch.object(main, "run", lambda *a, **k: runs.append(a) or (0, False)):
            code = main.scheduled(args, {}, SimpleNamespace(is_empty=lambda: True))
        return code, notes, runs

    def test_no_run_in_a_power_nap_wake(self):
        code, notes, runs = self.scheduled(dark=True)
        self.assertEqual((code, runs, self.awake), (0, [], []))       # nothing kept awake
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
        self.assertEqual(self.awake, ["on", ("off", "proc")])         # awake during the run, then released

    def test_run_goes_ahead_without_caffeinate(self):
        _, notes, runs = self.scheduled(dark=False, caffeinate=False)
        self.assertEqual(len(runs), 1)
        self.assertIn("caffeinate unavailable", notes[0])


if __name__ == "__main__":
    unittest.main()
