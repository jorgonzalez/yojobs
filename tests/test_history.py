import tempfile
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from yojobs import filter as jf
from yojobs import weekly
from yojobs.history import History, SourceRun
from yojobs.models import Job
from yojobs.store import Store

PROFILE = {"groups": {"role": ["Manager", "Head of"], "area": ["Platform", "DevOps"]},
           "all_of": ["Kubernetes|K8s"], "match_in": ["title"], "onsite_cities": ["Berlin"],
           "remote_regions": ["Europe"]}


def job(title, description="", url=None, company="C", location="Berlin"):
    return Job(source="x", title=title, company=company, url=url or f"https://x/{title}", location=location,
               description=description, published=datetime(2026, 11, 16, tzinfo=timezone.utc))


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.tmp.name) / "db.sqlite")
        self.h = History(self.store.db)

    def tearDown(self):
        self.store.db.close()
        self.tmp.cleanup()

    def runs(self, *rows, source="linkedin"):
        for i, (status, fetched) in enumerate(rows):
            self.h.record([SourceRun(source, status, fetched)], when=f"2026-11-1{i}T08:00:00+00:00")


class Health(Base):
    def test_three_errors_warn_once(self):
        self.runs(("ok", 50), ("ERROR", 0), ("ERROR", 0), ("ERROR", 0))
        broken, _ = self.h.health_changes(["linkedin"], 3)
        self.assertIn("linkedin", broken)
        self.h.mark_alerted(list(broken), [])
        self.assertEqual(self.h.health_changes(["linkedin"], 3), ({}, []))   # not again

    def test_zero_jobs_counts(self):
        self.runs(("ok", 0), ("ok", 0), ("ok", 0))
        self.assertIn("no jobs", self.h.health_changes(["linkedin"], 3)[0]["linkedin"])

    def test_one_good_run_is_fine_and_recovers(self):
        self.runs(("ERROR", 0), ("ERROR", 0), ("ERROR", 0))
        self.h.mark_alerted(["linkedin"], [])
        self.h.record([SourceRun("linkedin", "ok", 40)], when="2026-11-17T08:00:00+00:00")
        self.assertEqual(self.h.health_changes(["linkedin"], 3), ({}, ["linkedin"]))

    def test_needs_enough_history(self):
        self.runs(("ERROR", 0), ("ERROR", 0))
        self.assertEqual(self.h.health_changes(["linkedin"], 3), ({}, []))


class BoardHealth(Base):
    def board_runs(self, *failed_flags):
        for i, failed in enumerate(failed_flags):
            parts = [("greenhouse:gone", "HTTPError: HTTP Error 404: Not Found")] if failed else []
            self.h.record([SourceRun("companies", "ok", 9000, parts_failed=parts)],
                          when=f"2026-11-1{i}T08:00:00+00:00")

    def test_board_failing_three_runs_warns_once(self):
        self.board_runs(False, True, True, True)
        broken, _ = self.h.health_changes(["companies"], 3)
        self.assertEqual(list(broken), ["companies/greenhouse:gone"])
        self.assertIn("404", broken["companies/greenhouse:gone"])
        self.h.mark_alerted(list(broken), [])
        self.assertEqual(self.h.health_changes(["companies"], 3), ({}, []))

    def test_board_with_one_good_run_is_fine_and_recovers(self):
        self.board_runs(True, True, True)
        self.h.mark_alerted(["companies/greenhouse:gone"], [])
        self.h.record([SourceRun("companies", "ok", 9000)], when="2026-11-17T08:00:00+00:00")
        self.assertEqual(self.h.health_changes(["companies"], 3), ({}, ["companies/greenhouse:gone"]))

    def test_weekly_lists_failing_boards(self):
        now = datetime.now(timezone.utc)
        for i in range(2):
            self.h.record([SourceRun("companies", "ok", 9000, parts_failed=[("ashby:old", "HTTPError: 404")])],
                          when=(now.replace(microsecond=0) - timedelta(hours=i)).isoformat())
        subject, text, html, _ = weekly.build(self.h, {})
        self.assertIn("1 failing board", subject)
        self.assertIn("ashby:old", text)
        self.assertIn("failed 2 of 2 runs", text)


class Weekly(Base):
    def test_due_on_day_or_first_day_after(self):
        cfg = {"day": "monday"}
        self.assertTrue(self.h.weekly_due(cfg, date(2026, 11, 16)))   # Monday, never sent
        self.h.mark_weekly_sent(date(2026, 11, 16))
        self.assertFalse(self.h.weekly_due(cfg, date(2026, 11, 16)))  # once
        self.assertFalse(self.h.weekly_due(cfg, date(2026, 11, 22)))  # Sunday
        self.assertTrue(self.h.weekly_due(cfg, date(2026, 11, 24)))   # laptop off Monday -> Tuesday
        self.assertFalse(self.h.weekly_due({"enabled": False}, date(2026, 11, 24)))

    def test_build_lists_near_misses_once(self):
        self.h.add_near_misses([(job("Head of Platform", "no k word here"), "no Kubernetes in the ad")])
        subject, text, html, urls = weekly.build(self.h, {})
        self.assertIn("1 near misses", subject)
        self.assertIn("Head of Platform", text)
        self.h.mark_digested(urls)
        self.assertEqual(weekly.build(self.h, {})[3], [])

    def test_near_miss_already_emailed_is_skipped(self):
        j = job("Head of Platform")
        self.h.add_near_misses([(j, "no Kubernetes in the ad")])
        self.store.mark_seen([job("Head of Platform", url="https://other/portal")])  # same job, other portal
        self.assertEqual(self.h.pending_near_misses(), [])


class NearMiss(unittest.TestCase):
    def test_only_missing_required_words(self):
        self.assertEqual(jf.near_miss(job("Head of Platform", "We run AWS."), PROFILE), "no Kubernetes in the ad")
        self.assertEqual(jf.near_miss(job("Senior DevOps Engineer", "AWS"), PROFILE), "")       # not leadership
        self.assertEqual(jf.near_miss(job("Head of Platform", "AWS", location="Paris"), PROFILE), "")  # place
        self.assertEqual(jf.near_miss(job("Head of Platform", ""), PROFILE), "ad text not available")


if __name__ == "__main__":
    unittest.main()
