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


class FullRunsToday(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.tmp.name) / "db.sqlite")
        self.h = History(self.store.db)

    def tearDown(self):
        self.store.db.close()
        self.tmp.cleanup()

    def test_counts_only_unthrottled_runs_of_today(self):
        now = datetime.now(timezone.utc)
        self.h.record([SourceRun("linkedin", "ok", 300)], when=(now - timedelta(days=1)).isoformat())   # yesterday
        self.assertEqual(self.h.full_runs_today("linkedin"), 0)
        self.h.record([SourceRun("linkedin", "ok", 0, parts_failed=[("throttled", "429")])],
                      when=(now - timedelta(minutes=30)).isoformat())                                  # throttled
        self.assertEqual(self.h.full_runs_today("linkedin"), 0)
        self.h.record([SourceRun("linkedin", "ok", 300)], when=now.isoformat())                        # full run
        self.assertEqual(self.h.full_runs_today("linkedin"), 1)


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
