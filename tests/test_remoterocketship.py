import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

from yojobs import filter as jf
from yojobs.sources import remoterocketship as rrs

HERE = Path(__file__).parent
SITEMAP = (HERE / "fixture_remoterocketship_sitemap.xml").read_text()
JOB = (HERE / "fixture_remoterocketship_job.html").read_text()
PROFILE = {"groups": {"role": ["Manager", "Engineering Manager"], "area": ["DevOps", "Platform"]},
           "match_in": ["title"], "onsite_cities": ["Berlin"],
           "remote_regions": ["Germany", "Europe", "EMEA", "Worldwide"]}
LONG_AGO = datetime(2020, 1, 1, tzinfo=timezone.utc)


class Entries(unittest.TestCase):
    def test_only_allowed_places(self):
        jobs = rrs.entries(SITEMAP, LONG_AGO, rrs.PLACES)
        self.assertEqual(sorted(j.location for j in jobs), ["Europe", "Germany", "Worldwide"])  # Spain-only dropped
        devops = next(j for j in jobs if j.location == "Europe")
        self.assertEqual(devops.title, "Devops Manager")
        self.assertTrue(devops.remote)
        self.assertTrue(devops.published)

    def test_window(self):
        self.assertEqual(rrs.entries(SITEMAP, datetime.now(timezone.utc) + timedelta(days=1), rrs.PLACES), [])

    def test_job_page(self):
        job = rrs.entries(SITEMAP, LONG_AGO, rrs.PLACES)[0]
        rrs.enrich(job, rrs.job_posting(JOB))
        self.assertGreater(len(job.description.split()), 100)
        self.assertIn("Germany", job.location)          # the exact countries allowed
        self.assertEqual(job.company, "Magnify Labs")


class Fetch(unittest.TestCase):
    def test_sitemaps_then_pages_only_for_new_candidates(self):
        urls = []

        def fake_get(url, params=None):
            urls.append(url)
            return (SITEMAP if url.endswith(".xml") else JOB).encode()
        jobs0 = rrs.entries(SITEMAP, LONG_AGO, rrs.PLACES)
        known = {next(j.url for j in jobs0 if j.location == "Germany")}
        cfg = {"sitemaps": ["a.xml", "b.xml"], "delay_seconds": 0, "_problems": [],
               "_title_ok": lambda j: jf.title_ok(j, PROFILE), "_known": lambda j: j.url in known}
        with mock.patch.object(rrs, "get_bytes", fake_get), mock.patch.object(rrs, "say"), \
                mock.patch.object(rrs.time, "sleep"):
            jobs = rrs.fetch(cfg, LONG_AGO)
        self.assertEqual(len(jobs), 3)                                   # same URLs in both sitemaps: deduped
        pages = [u for u in urls if not u.endswith(".xml")]
        self.assertEqual(len(pages), 1)                                  # DevOps Manager only (EM Germany is known)

    def test_all_sitemaps_failing_is_an_error(self):
        def fail(url, params=None):
            raise TimeoutError()
        with mock.patch.object(rrs, "get_bytes", fail), mock.patch.object(rrs, "say"), \
                mock.patch.object(rrs.time, "sleep"):
            with self.assertRaises(RuntimeError):
                rrs.fetch({"delay_seconds": 0, "_problems": []}, LONG_AGO)


if __name__ == "__main__":
    unittest.main()
