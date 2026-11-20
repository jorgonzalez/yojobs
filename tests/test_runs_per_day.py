import io
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from yojobs import __main__ as m
from yojobs.history import History, SourceRun
from yojobs.mailer import render
from yojobs.store import Store


class RunsToday(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.tmp.name) / "db.sqlite")
        self.h = History(self.store.db)

    def tearDown(self):
        self.store.db.close()
        self.tmp.cleanup()

    def test_counts_todays_runs_throttled_included(self):
        now = datetime.now(timezone.utc)
        self.h.record([SourceRun("linkedin", "ok", 300)], when=(now - timedelta(days=1)).isoformat())   # yesterday
        self.assertEqual(self.h.runs_today("linkedin"), 0)
        self.h.record([SourceRun("linkedin", "ERROR", 0, error="offline")],
                      when=(now - timedelta(minutes=40)).isoformat())                                  # error: no
        self.assertEqual(self.h.runs_today("linkedin"), 0)
        self.h.record([SourceRun("linkedin", "ok", 0, parts_failed=[("throttled", "429")])],
                      when=(now - timedelta(minutes=30)).isoformat())                                  # throttled
        self.assertEqual(self.h.runs_today("linkedin"), 1)
        # the throttled run is not a full run: tomorrow's lookback still starts at yesterday's
        self.assertLess(self.h.last_full_run("linkedin"), now - timedelta(hours=23))


class SkipInRun(unittest.TestCase):
    def run_once(self, store, source_arg=None):
        calls = []

        def fake(cfg, since):
            calls.append(1)
            return []
        cfg = {"sources": {"linkedin": {"runs_per_day": 1}}, "profiles": []}
        args = SimpleNamespace(source=source_arg, all=False, email=True)
        with mock.patch.dict(m.SOURCES, {"linkedin": fake}, clear=True), mock.patch.object(m.mailer, "send"), \
                redirect_stdout(io.StringIO()), mock.patch("sys.stderr", io.StringIO()):
            m.run(args, cfg, store, 3)
        return len(calls)

    def test_once_a_day_unless_asked_explicitly(self):
        with tempfile.TemporaryDirectory() as d:
            store = Store(Path(d) / "db.sqlite")
            self.assertEqual(self.run_once(store), 1)          # first run today: runs (and is recorded)
            self.assertEqual(self.run_once(store), 0)          # second: skipped
            self.assertEqual(self.run_once(store, ["linkedin"]), 1)   # --source linkedin: always runs

    def test_skip_is_not_a_source_problem_in_the_email(self):
        text, html = render([], [("linkedin", "skip", "already ran 1x today (runs_per_day)")])
        self.assertNotIn("Source problems", text)


if __name__ == "__main__":
    unittest.main()
