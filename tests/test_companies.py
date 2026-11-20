import json
import unittest
from pathlib import Path
from unittest import mock

from yojobs.sources import companies
from yojobs.sources.companies import _mode

PERSONIO_EN = b"""<?xml version="1.0" encoding="UTF-8"?><workzag-jobs>
<position><id>1</id><office>Berlin / 100% remote</office><name>Head of Platform</name>
  <jobDescriptions><jobDescription><name>Tasks</name><value><![CDATA[<p>Run Kubernetes</p>]]></value></jobDescription></jobDescriptions>
  <createdAt>2026-11-10T09:00:00+00:00</createdAt><department>Engineering</department></position>
<position><id>2</id><office>Hamburg</office><name>Teamleitung DevOps</name>
  <jobDescriptions><jobDescription><name>Aufgaben</name><value></value></jobDescription></jobDescriptions>
  <createdAt>2026-11-11T09:00:00+00:00</createdAt></position>
</workzag-jobs>"""
PERSONIO_DE = PERSONIO_EN.replace(b"<value></value>", b"<value><![CDATA[Du betreibst Kubernetes]]></value>")

RECRUITEE = {"offers": [
    {"title": "EM Infra", "company_name": "Acme GmbH", "careers_url": "https://acme.recruitee.com/o/em",
     "location": "Berlin", "city": "Berlin", "country": "Deutschland", "remote": False, "hybrid": True,
     "on_site": False, "published_at": "2026-11-10 09:00:00 UTC", "description": "<p>K8s</p>", "requirements": ""},
    {"title": "SRE Lead", "company_name": "Acme GmbH", "careers_url": "https://acme.recruitee.com/o/sre",
     "location": "Homeoffice", "country": "Deutschland", "remote": True, "hybrid": False, "on_site": False,
     "published_at": "2026-11-12 09:00:00 UTC", "description": "x", "requirements": "y"}]}


class WorkMode(unittest.TestCase):
    def test_mode(self):
        self.assertTrue(_mode("Remote"))
        self.assertTrue(_mode("remote"))
        self.assertFalse(_mode("Hybrid"))
        self.assertFalse(_mode("OnSite"))
        self.assertFalse(_mode("on-site"))
        self.assertIsNone(_mode(None))
        self.assertIsNone(_mode("unspecified"))


class Personio(unittest.TestCase):
    def test_english_with_fallback_to_original(self):
        fake = lambda url, params=None: PERSONIO_EN if params else PERSONIO_DE
        with mock.patch.object(companies, "get_bytes", fake), mock.patch.object(companies.time, "sleep"):
            a, b = companies._personio("acme")
        self.assertEqual((a.title, a.location, a.url), ("Head of Platform", "Berlin / 100% remote",
                                                         "https://acme.jobs.personio.de/job/1?language=en"))
        self.assertIn("Run Kubernetes", a.description)
        self.assertIn("Du betreibst Kubernetes", b.description)   # no English text -> original
        self.assertEqual(a.published.isoformat(), "2026-11-10T09:00:00+00:00")


class Recruitee(unittest.TestCase):
    def test_modes(self):
        with mock.patch.object(companies, "get_json", lambda url, params=None: RECRUITEE):
            hybrid, remote = companies._recruitee("acme")
        self.assertEqual((hybrid.remote, hybrid.work_mode), (False, "hybrid"))
        self.assertEqual((remote.remote, remote.work_mode), (True, "remote"))
        self.assertEqual(remote.location, "Homeoffice, Deutschland")
        self.assertEqual(hybrid.published.isoformat(), "2026-11-10T09:00:00+00:00")



LEVER_JOB = [{"text": "Lead Reliability Engineer", "hostedUrl": "https://jobs.eu.lever.co/quantinuum/1",
              "categories": {"location": "Berlin"}, "createdAt": 1763370000000, "descriptionPlain": "Kubernetes",
              "workplaceType": "hybrid"}]


class Lever(unittest.TestCase):
    def urls(self, board):
        seen = []
        def fake(url, params=None):
            seen.append(url)
            return LEVER_JOB
        with mock.patch.object(companies, "get_json", fake):
            jobs = companies._lever(board)
        return seen, jobs

    def test_us_and_eu_servers(self):
        self.assertEqual(self.urls("spotify")[0], ["https://api.lever.co/v0/postings/spotify"])
        urls, jobs = self.urls("eu:quantinuum")
        self.assertEqual(urls, ["https://api.eu.lever.co/v0/postings/quantinuum"])
        self.assertEqual((jobs[0].company, jobs[0].url), ("Quantinuum", "https://jobs.eu.lever.co/quantinuum/1"))


class Teamtailor(unittest.TestCase):
    FEED = (Path(__file__).parent / "fixture_teamtailor.xml").read_bytes()

    def test_feed(self):
        urls = []
        with mock.patch.object(companies, "get_bytes", lambda url, params=None: urls.append(url) or self.FEED):
            jobs = companies._teamtailor("career")
            companies._teamtailor("careers.example.com")
        self.assertEqual(urls, ["https://career.teamtailor.com/jobs.rss", "https://careers.example.com/jobs.rss"])
        first = jobs[0]
        self.assertEqual((first.company, first.location), ("Teamtailor", "Chicago, United States"))
        self.assertEqual((first.remote, first.work_mode), (False, "hybrid"))
        self.assertEqual(first.published.isoformat(), "2026-11-11T16:34:36+00:00")
        self.assertTrue(first.description)
        self.assertEqual(jobs[2].work_mode, "onsite")

    def test_fully_remote(self):
        feed = self.FEED.replace(b"<remoteStatus>hybrid</remoteStatus>", b"<remoteStatus>fully</remoteStatus>", 1)
        with mock.patch.object(companies, "get_bytes", lambda url, params=None: feed):
            first = companies._teamtailor("career")[0]
        self.assertEqual((first.remote, first.work_mode), (True, "remote"))

    def test_config_accepts_teamtailor(self):
        from yojobs.config import normalize
        cfg = normalize({"sources": {"companies": True}, "companies": {"teamtailor": ["acme", "careers.example.com"]}})
        self.assertEqual(cfg["sources"]["companies"]["boards"], ["teamtailor:acme", "teamtailor:careers.example.com"])


class Pinpoint(unittest.TestCase):
    FEED = json.loads((Path(__file__).parent / "fixture_pinpoint.json").read_text())

    def test_feed(self):
        urls = []
        with mock.patch.object(companies, "get_json", lambda url, params=None: urls.append(url) or self.FEED):
            jobs = companies._pinpoint("careers.admgroup.com")
            other = companies._pinpoint("acme")
        self.assertEqual(urls, ["https://careers.admgroup.com/postings.json", "https://acme.pinpointhq.com/postings.json"])
        first, second = jobs
        self.assertEqual((first.title, first.company, first.location), ("Infrastructure Lead", "Admgroup", "Europe"))
        self.assertEqual((first.remote, first.work_mode, first.published), (True, "Fully remote", None))
        self.assertIn("Kubernetes", first.description)
        self.assertNotIn("<li>", first.description)
        self.assertEqual((second.remote, second.location), (False, "Camden, London"))
        self.assertEqual(other[0].company, "Acme")

    def test_filters(self):
        from yojobs import filter as jobfilter
        profile = {"groups": {"role": ["Lead"], "area": ["Infrastructure"]}, "all_of": ["Kubernetes"],
                   "onsite_cities": ["Berlin"], "remote_regions": ["Europe"]}
        with mock.patch.object(companies, "get_json", lambda url, params=None: self.FEED):
            remote, london = companies._pinpoint("careers.admgroup.com")
        self.assertTrue(jobfilter.apply(remote, profile))
        self.assertFalse(jobfilter.apply(london, profile))      # hybrid, London

    def test_config_accepts_pinpoint(self):
        from yojobs.config import normalize
        cfg = normalize({"sources": {"companies": True}, "companies": {"pinpoint": ["careers.admgroup.com"]}})
        self.assertEqual(cfg["sources"]["companies"]["boards"], ["pinpoint:careers.admgroup.com"])


if __name__ == "__main__":
    unittest.main()
