import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from yojobs import filter as jf
from yojobs import weekly
from yojobs.history import History
from yojobs.models import Job
from yojobs.store import Store

PROFILE = {"groups": {"role": ["Manager", "Lead"], "area": ["Platform", "Infrastructure"]},
           "none_of": ["SAP", "Account Manager"], "exclude_in": ["title"], "match_in": ["title"],
           "all_of": ["Kubernetes"], "onsite_cities": ["Berlin"], "remote_regions": ["Europe"]}


def near(title, company="C", location="Berlin", description="We run VMs.", url=None):
    return Job(source="x", title=title, company=company, url=url or f"https://x/{company}/{title}", location=location,
               description=description, published=datetime(2026, 11, 18, tzinfo=timezone.utc))


def keep(n):
    return jf.still_near_miss(Job(source=n["source"], title=n["title"], company=n["company"], url=n["url"],
                                  location=n["location"], description=n["description"]), PROFILE)


class StillNearMiss(unittest.TestCase):
    def test_title_rules_only(self):
        self.assertTrue(jf.still_near_miss(near("Platform Lead"), PROFILE))
        self.assertFalse(jf.still_near_miss(near("SAP Basis & Platform Service Manager"), PROFILE))
        self.assertFalse(jf.still_near_miss(near("Key Account Manager – Infrastructure"), PROFILE))
        self.assertFalse(jf.still_near_miss(near("Platform Engineer"), PROFILE))   # no role word
        # the place isn't re-checked: a remote job's flag isn't stored with the near miss
        self.assertTrue(jf.still_near_miss(near("Platform Lead", location="Remote, Europe",
                                                description="Two office days a month in Paris."), PROFILE))


class Build(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.tmp.name) / "db.sqlite")
        self.h = History(self.store.db)

    def tearDown(self):
        self.store.db.close()
        self.tmp.cleanup()

    def test_rules_of_today_and_one_per_job(self):
        self.h.add_near_misses([(j, "no Kubernetes in the ad") for j in (
            near("Engineering Manager Platform", company="Acme"),
            near("Engineering Manager, Platform (m/f/d)", company="Acme GmbH", url="https://y/1"),  # same job
            near("SAP Basis & Platform Service Manager", company="Gambit"),                         # rule since
            near("Infrastructure Lead", company="Other"))])
        scored = []
        subject, text, _, urls = weekly.build(self.h, {}, keep=keep, score=lambda ns: scored.extend(ns))
        self.assertIn("2 near misses", subject)
        self.assertNotIn("SAP", text)
        self.assertEqual(sorted(n["company"] for n in scored), ["Acme", "Other"])   # only these are CV-scored
        self.assertEqual(len(urls), 3)                       # all marked done, so dropped ones don't come back
        self.h.mark_digested(urls)
        self.assertEqual(weekly.build(self.h, {}, keep=keep)[3], [])

    def test_flagged_company_is_marked(self):
        self.h.add_near_misses([(near("Platform Lead", company=c), "no Kubernetes in the ad")
                                for c in ("Cair Paravel GmbH", "Other")])
        flag = lambda company: "Narnian company" if company.startswith("Cair") else ""  # noqa: E731
        _, text, html_body, _ = weekly.build(self.h, {}, flag=flag)
        self.assertIn("no Kubernetes in the ad · ⚠ Narnian company", text)
        self.assertIn("⚠ Narnian company", html_body)
        self.assertEqual(text.count("⚠"), 1)

    def test_same_key_from_another_portal_is_done_too(self):
        self.h.add_near_misses([(near("Platform Lead", url=u), "no Kubernetes in the ad")
                                for u in ("https://a/1", "https://b/1")])
        urls = weekly.build(self.h, {})[3]
        self.assertEqual(len(urls), 1)
        self.h.mark_digested(urls)
        self.assertEqual(weekly.build(self.h, {})[3], [])    # the other portal's copy doesn't come back

    def test_without_keep_nothing_is_dropped(self):
        self.h.add_near_misses([(near("SAP Platform Manager"), "no Kubernetes in the ad")])
        self.assertIn("SAP", weekly.build(self.h, {})[1])


if __name__ == "__main__":
    unittest.main()
