import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from yojobs.schedule import RunLock, State, is_due

CFG = {"earliest": "06:30", "latest": "22:00", "min_gap_hours": 5, "max_runs_per_day": 3}


def at(day, hhmm):
    h, m = map(int, hhmm.split(":"))
    return datetime(2026, 11, day, h, m)


class Schedule(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.state = State(Path(self.tmp.name) / "state.json")

    def tearDown(self):
        self.tmp.cleanup()

    def due(self, when):
        return is_due(CFG, self.state, when)[0]

    def test_morning_first_run(self):
        self.assertFalse(self.due(at(17, "06:00")))   # too early
        self.assertTrue(self.due(at(17, "06:30")))    # laptop opened at 6:30
        self.assertTrue(self.due(at(17, "09:15")))    # or later in the morning

    def test_gap_between_runs(self):
        self.state.record_run(at(17, "07:00"))
        self.assertFalse(self.due(at(17, "07:30")))
        self.assertFalse(self.due(at(17, "11:59")))
        self.assertTrue(self.due(at(17, "12:00")))

    def test_laptop_off_for_hours_runs_once_when_back(self):
        self.state.record_run(at(17, "07:00"))
        self.assertTrue(self.due(at(17, "17:00")))     # off 9:00-17:00 -> one run now
        self.state.record_run(at(17, "17:00"))
        self.assertFalse(self.due(at(17, "17:30")))    # no catch-up of the missed one

    def test_max_runs_per_day(self):
        for t in ("06:30", "11:30", "16:30"):
            self.state.record_run(at(17, t))
        self.assertFalse(self.due(at(17, "21:45")))

    def test_too_late(self):
        self.assertFalse(self.due(at(17, "22:30")))

    def test_new_day_starts_fresh(self):
        for t in ("06:30", "11:30", "16:30"):
            self.state.record_run(at(17, t))
        self.assertTrue(self.due(at(18, "06:45")))     # next morning, no carry-over

    def test_state_survives_reload(self):
        self.state.record_run(at(17, "07:00"))
        again = State(self.state.path)
        self.assertEqual(again.last_run, at(17, "07:00"))


class Lock(unittest.TestCase):
    def test_second_run_is_refused(self):
        with tempfile.TemporaryDirectory() as d:
            a, b = RunLock(Path(d) / "x.lock"), RunLock(Path(d) / "x.lock")
            self.assertTrue(a.acquire())
            self.assertFalse(b.acquire())
            a.release()
            self.assertTrue(b.acquire())
            b.release()


if __name__ == "__main__":
    unittest.main()
