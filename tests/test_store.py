"""Run: .venv/bin/python -m unittest discover tests"""
import sqlite3
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from yojobs.models import Job
from yojobs.store import Store, job_key, norm_company, norm_title


def job(title, company="Acme GmbH", url=None, source="x"):
    return Job(source, title, company, url or f"https://example.com/{abs(hash((title, company, source)))}")


class Normalization(unittest.TestCase):
    def test_company_legal_suffixes(self):
        for c in ["Acme", "ACME GmbH", "Acme, Inc.", "Acme Ltd", "Acme B.V.", "acme gmbh & co. kg", "Acme SE"]:
            self.assertEqual(norm_company(c), "acme", c)

    def test_company_suffix_only_name_kept(self):
        self.assertEqual(norm_company("Group"), "group")

    def test_title_variants_equal(self):
        base = norm_title("Senior DevOps Engineer")
        for t in [
            "Sr. DevOps Engineer",
            "Senior DevOps Engineer (m/w/d)",
            "Senior DevOps Engineer (f/m/x)",
            "Senior DevOps Engineer - Remote",
            "Senior DevOps Engineer – Germany",
            "Senior DevOps Engineer (Remote, EU)",
            "Senior DevOps Engineer | Berlin or Remote",
            "Senior DevOps Engineer, Remote - Europe",
            "Senior DevOps Engineer (100% Remote)",
            "SENIOR DEVOPS ENGINEER",
        ]:
            self.assertEqual(norm_title(t), base, t)

    def test_titles_that_must_stay_different(self):
        self.assertNotEqual(norm_title("DevOps Engineer - Platform"), norm_title("DevOps Engineer - Data"))
        self.assertNotEqual(norm_title("Engineering Manager, Platform"), norm_title("Engineering Manager"))
        self.assertNotEqual(norm_title("Senior SRE"), norm_title("Junior SRE"))
        self.assertNotEqual(norm_title("DevOps Engineer (Kubernetes)"), norm_title("DevOps Engineer"))


class Dedupe(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "seen.sqlite"
        self.store = Store(self.path, key_days=60)

    def tearDown(self):
        self.tmp.cleanup()

    def test_same_platform_later_date(self):
        a = job("Senior DevOps Engineer", url="https://wwr/1")
        self.store.mark_seen([a])
        self.assertEqual(self.store.filter_new([job("Senior DevOps Engineer", url="https://wwr/1")]), [])

    def test_same_platform_reposted_new_url(self):
        self.store.mark_seen([job("Senior DevOps Engineer", url="https://wwr/1")])
        self.assertEqual(self.store.filter_new([job("Sr DevOps Engineer (m/w/d)", url="https://wwr/1-4")]), [])

    def test_two_platforms(self):
        self.store.mark_seen([job("Senior DevOps Engineer", "Acme GmbH", "https://himalayas/a")])
        again = job("Senior DevOps Engineer - Remote, Germany", "ACME", "https://jobicy/b")
        self.assertEqual(self.store.filter_new([again]), [])

    def test_two_platforms_same_run(self):
        a = job("Senior DevOps Engineer", "Acme GmbH", "https://himalayas/a")
        b = job("Senior DevOps Engineer (Remote)", "Acme", "https://jobicy/b")
        self.assertEqual(self.store.filter_new([a, b]), [a])

    def test_different_company_not_merged(self):
        self.store.mark_seen([job("Senior DevOps Engineer", "Acme")])
        other = job("Senior DevOps Engineer", "Globex")
        self.assertEqual(self.store.filter_new([other]), [other])

    def test_reopened_after_expiry(self):
        old = job("Senior DevOps Engineer", url="https://wwr/1")
        self.store.mark_seen([old])
        past = (datetime.now(timezone.utc) - timedelta(days=61)).isoformat(timespec="seconds")
        self.store.db.execute("UPDATE seen SET first_seen = ?", (past,))
        self.store.db.commit()
        reopened = job("Senior DevOps Engineer", url="https://wwr/99")
        self.assertEqual(self.store.filter_new([reopened]), [reopened])
        # but the exact old URL stays blocked forever
        self.assertEqual(self.store.filter_new([job("Senior DevOps Engineer", url="https://wwr/1")]), [])

    def test_sort_matches_says_why(self):
        self.store.mark_seen([job("Hands-on Engineering Manager, Infrastructure", "Miaplaza", "https://himalayas/m", "himalayas")])
        sent = job("Hands-on Engineering Manager, Infrastructure (Remote)", "Miaplaza Inc", "https://arbeitnow/m", "arbeitnow")
        fresh = job("DevOps Manager", "Consensys", source="remoterocketship")
        repeat = job("DevOps Manager (Remote)", "Consensys", source="startupmap")
        new, outcomes = self.store.sort_matches([sent, fresh, repeat])
        self.assertEqual(new, [fresh])
        kinds = [(j.source, kind) for j, kind, _ in outcomes]
        self.assertEqual(kinds, [("arbeitnow", "sent"), ("remoterocketship", "new"), ("startupmap", "duplicate")])
        self.assertEqual(outcomes[0][2][:2], ("Hands-on Engineering Manager, Infrastructure", "himalayas"))
        self.assertEqual(outcomes[2][2][:2], ("DevOps Manager", "remoterocketship"))
        self.assertTrue(self.store.is_seen(sent))
        self.assertFalse(self.store.is_seen(fresh))

    def test_rekey_old_database(self):
        self.store.mark_seen([job("Senior DevOps Engineer (m/w/d)", url="https://a/1")])
        self.store.db.execute("UPDATE seen SET key = 'old-format'")
        self.store.db.commit()
        reopened = Store(self.path)  # re-open recomputes keys
        self.assertEqual(reopened.filter_new([job("Sr. DevOps Engineer", url="https://b/2")]), [])



class SimilarTitles(unittest.TestCase):
    def test_pairs(self):
        from yojobs.store import similar_titles
        same = [("Hands-on Engineering Manager, Infrastructure", "Hands-on Engineering Manager DevOps (GCP/Kubernetes)"),
                ("Engineering Manager Platform And It Compliance", "Engineering Manager - Platform and IT & Compliance"),
                ("Senior Engineering Manager, Platform", "Engineering Manager Platform (m/w/d)"),
                ("Head of Platform (Infrastructure & DevOps)", "Head of Platform – Infrastructure, DevOps")]
        different = [("Engineering Manager Banking Platform", "Engineering Manager Ai Engineering Ai Platform"),
                     ("Engineering Manager Platform", "Engineering Manager Data"),
                     ("Head of Platform", "Head of Infrastructure"),
                     ("Manager", "Manager"),          # too few words to judge
                     ("Engineering Manager (Platform)", "Engineering Manager (Data)")]
        for a, b in same:
            self.assertTrue(similar_titles(a, b), (a, b))
        for a, b in different:
            self.assertFalse(similar_titles(a, b), (a, b))

    def test_seen_across_portals(self):
        import tempfile
        from pathlib import Path as P
        with tempfile.TemporaryDirectory() as d:
            store = Store(P(d) / "db.sqlite")
            first = Job(source="himalayas", title="Hands-on Engineering Manager, Infrastructure", company="Miaplaza",
                        url="https://himalayas.app/x")
            again = Job(source="arbeitnow", title="Remote Hands-on Engineering Manager (DevOps, GCP, Kubernetes)",
                        company="MiaPlaza Inc.", url="https://www.arbeitnow.com/y")
            other = Job(source="arbeitnow", title="Engineering Manager Data", company="Miaplaza", url="https://z")
            store.mark_seen([first])
            self.assertEqual(store.filter_new([again, other]), [other])
            # and within one run
            store2 = Store(P(d) / "db2.sqlite")
            self.assertEqual(store2.filter_new([first, again, other]), [first, other])

if __name__ == "__main__":
    unittest.main()
