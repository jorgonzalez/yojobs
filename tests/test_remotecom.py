import unittest
from pathlib import Path
from unittest import mock

from yojobs import filter as jf
from yojobs.sources import remotecom

HERE = Path(__file__).parent
SEARCH = (HERE / "fixture_remotecom_search.html").read_text()
JOB = (HERE / "fixture_remotecom_job.html").read_text()
PROFILE = {"groups": {"role": ["Engineering Manager", "Head of"], "area": ["Platform", "Engineering"]},
           "match_in": ["title"], "onsite_cities": ["Berlin"], "remote_regions": ["Germany", "Europe", "Worldwide"]}


class Parse(unittest.TestCase):
    def test_records(self):
        jobs = [remotecom.to_job(o) for o in remotecom.records(SEARCH)]
        self.assertEqual([j.location for j in jobs], ["Worldwide", "United States", "Europe"])
        self.assertTrue(all(j.remote for j in jobs))
        self.assertEqual(jobs[0].salary, "USD 170,000-200,000")      # cents -> whole amounts
        self.assertTrue(jobs[2].url.startswith("https://remote.com/jobs/"))

    def test_where_they_hire_decides(self):
        jobs = {j.location: j for j in (remotecom.to_job(o) for o in remotecom.records(SEARCH))}
        self.assertTrue(jf.place_ok(jobs["Worldwide"], PROFILE))
        self.assertTrue(jf.place_ok(jobs["Europe"], PROFILE))
        self.assertFalse(jf.place_ok(jobs["United States"], PROFILE))

    def test_ad_text(self):
        self.assertGreater(len(remotecom.ad_text(JOB).split()), 100)
        self.assertEqual(remotecom.ad_text("<html></html>"), "")


class Fetch(unittest.TestCase):
    def run_fetch(self, fail=(), known=()):
        urls = []

        def fake_get(url, params=None):
            urls.append(url)
            if any(f in url for f in fail):
                raise TimeoutError("slow")
            return (SEARCH if "/jobs/all?" in url else JOB).encode()
        cfg = {"searches": [{"term": "Engineering Manager"}, {"term": "Engineering Manager"}, {"term": "Head of Platform"}],
               "_title_ok": lambda j: jf.title_ok(j, PROFILE), "_known": lambda j: j.url in known,
               "delay_seconds": 0, "_problems": []}
        with mock.patch.object(remotecom, "get_bytes", fake_get), mock.patch.object(remotecom, "say"), \
                mock.patch.object(remotecom.time, "sleep"):
            jobs = remotecom.fetch(cfg, None)
        return urls, jobs, cfg["_problems"]

    def test_searches_then_ads_only_for_candidates(self):
        urls, jobs, problems = self.run_fetch()
        searches = [u for u in urls if "/jobs/all?" in u]
        self.assertEqual(searches, ["https://remote.com/jobs/all?query=Engineering+Manager",
                                    "https://remote.com/jobs/all?query=Head+of+Platform"])     # terms deduped
        ads = [u for u in urls if "/jobs/all?" not in u]
        self.assertEqual(len(ads), 2)                     # Worldwide + Europe pass; the US-only job isn't opened
        self.assertEqual({j.found_by for j in jobs}, {"Engineering Manager · remote.com"})
        self.assertTrue(all(j.description for j in jobs if j.location != "United States"))

    def test_known_jobs_not_reopened_and_failures_reported(self):
        jobs = [remotecom.to_job(o) for o in remotecom.records(SEARCH)]
        urls, _, _ = self.run_fetch(known={jobs[0].url})
        self.assertEqual(len([u for u in urls if "/jobs/all?" not in u]), 1)
        _, _, problems = self.run_fetch(fail=("query=Head",))
        self.assertEqual(problems[0][0], "Head of Platform")
        with self.assertRaises(RuntimeError):
            self.run_fetch(fail=("query=",))


if __name__ == "__main__":
    unittest.main()
