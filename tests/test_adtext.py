import io
import json
import sqlite3
import tempfile
import unittest
import urllib.error
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

from yojobs import adtext, matching
from yojobs.models import Job

AD = ("We are looking for an Engineering Manager to lead our platform team of eight engineers. "
      "You will own our Kubernetes infrastructure on GCP, the developer platform and on-call health. "
      "You bring several years of leading infrastructure teams and hands-on Kubernetes experience.")
JSONLD_PAGE = ("<html><head><title>Ignored title</title><script type='application/ld+json'>"
               + json.dumps({"@context": "https://schema.org", "@type": "JobPosting", "title": "Engineering Manager, Platform",
                             "hiringOrganization": {"@type": "Organization", "name": "Acme"},
                             "jobLocation": {"address": {"addressLocality": "Berlin", "addressCountry": "DE"}},
                             "description": f"<p>{AD}</p>"})
               + "</script></head><body><nav>menu</nav><p>Apply now</p></body></html>")
PLAIN_PAGE = (f"<html><head><title>Head of SRE | Example</title><style>p{{}}</style></head>"
              f"<body><nav>Home Jobs</nav><h1>Head of SRE</h1><p>{AD}</p><script>var x=1</script></body></html>")
CHALLENGE = "<html><head><title>Just a moment...</title></head><body>Checking your browser. cf-chl</body></html>"


class Html(unittest.TestCase):
    def test_jobposting_data_first(self):
        j = adtext.from_html(JSONLD_PAGE, "https://x")
        self.assertEqual((j.title, j.company, j.location), ("Engineering Manager, Platform", "Acme", "Berlin, DE"))
        self.assertIn("Kubernetes infrastructure", j.description)
        self.assertNotIn("menu", j.description)

    def test_visible_text_fallback(self):
        j = adtext.from_html(PLAIN_PAGE)
        self.assertEqual(j.title, "Head of SRE | Example")
        self.assertIn("Kubernetes infrastructure", j.description)
        self.assertNotIn("var x", j.description)
        self.assertNotIn("Home Jobs", j.description)   # nav removed


class Links(unittest.TestCase):
    def test_greenhouse_uses_the_api(self):
        seen = []
        with mock.patch.object(adtext, "get_json", lambda url, params=None: seen.append(url) or
                               {"title": "SRE Lead", "location": {"name": "Remote, Europe"},
                                "content": "&lt;p&gt;" + AD + "&lt;/p&gt;"}):
            j = adtext.from_url("https://job-boards.greenhouse.io/acme/jobs/12345?gh_src=x")
        self.assertEqual(seen, ["https://boards-api.greenhouse.io/v1/boards/acme/jobs/12345"])
        self.assertEqual((j.title, j.location), ("SRE Lead", "Remote, Europe"))
        self.assertTrue(j.description.startswith("We are looking"))

    def test_ashby_finds_the_job_on_its_board(self):
        uid = "aefd66e4-d812-48b3-a9f6-160e19882136"
        board = [Job(source="companies", title="Other", company="C", url="https://jobs.ashbyhq.com/c/other"),
                 Job(source="companies", title="EM Platform", company="C", url=f"https://jobs.ashbyhq.com/c/{uid}",
                     description=AD)]
        from yojobs.sources import companies
        with mock.patch.object(companies, "_ashby", lambda b: board):
            j = adtext.from_url(f"https://jobs.ashbyhq.com/c/{uid}/application")
        self.assertEqual(j.title, "EM Platform")

    def test_other_page_and_blocks(self):
        with mock.patch.object(adtext, "get_bytes", lambda url, params=None: JSONLD_PAGE.encode()):
            self.assertEqual(adtext.from_url("https://careers.example.com/job/1").company, "Acme")
        with mock.patch.object(adtext, "get_bytes", lambda url, params=None: CHALLENGE.encode()):
            with self.assertRaises(adtext.BlockedError):
                adtext.from_url("https://protected.example.com/job/1")

        def forbidden(url, params=None):
            raise urllib.error.HTTPError(url, 403, "Forbidden", {}, None)
        with mock.patch.object(adtext, "get_bytes", forbidden):
            with self.assertRaises(adtext.BlockedError):
                adtext.from_url("https://protected.example.com/job/2")


class Files(unittest.TestCase):
    def test_text_html_and_stdin(self):
        with tempfile.TemporaryDirectory() as d:
            txt, page = Path(d) / "ad.txt", Path(d) / "saved.html"
            txt.write_text("Head of Platform\n\n" + AD)
            page.write_text(JSONLD_PAGE)
            self.assertEqual(adtext.load(str(txt)).title, "Head of Platform")
            self.assertEqual(adtext.load(str(page)).company, "Acme")
        with mock.patch("sys.stdin", io.StringIO("SRE Team Lead\n" + AD)):
            self.assertEqual(adtext.load("-").title, "SRE Team Lead")
        with self.assertRaises(RuntimeError):
            adtext.load("/no/such/file.pdf")


class MatchOne(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "cv").mkdir()
        (self.root / "cv" / "cv.md").write_text("Platform lead, Kubernetes, GCP")
        self.ad = self.root / "ad.html"
        self.ad.write_text(JSONLD_PAGE)

    def tearDown(self):
        self.tmp.cleanup()

    def run_match(self, arg, models=("gpt-oss:20b",)):
        answer = {"score": 87, "strengths": ["Kubernetes"], "gaps": [], "summary": "You fit."}
        out = io.StringIO()
        with mock.patch.object(matching, "ollama_models", return_value=list(models) if models else None), \
                mock.patch.object(matching, "_post", lambda *a: {"message": {"content": json.dumps(answer)}}), \
                mock.patch.object(matching, "note"), redirect_stdout(out):
            code = matching.match_one({"matching": {"enabled": False}}, self.root, arg)  # works even when off
        return code, out.getvalue()

    def test_scores_a_saved_page(self):
        code, out = self.run_match(str(self.ad))
        self.assertEqual(code, 0)
        self.assertIn("Engineering Manager, Platform — Acme", out)
        self.assertIn("CV match 87%", out)

    def test_ollama_down_and_blocked(self):
        code, out = self.run_match(str(self.ad), models=None)
        self.assertEqual(code, 1)
        self.assertIn("isn't running", out)
        with mock.patch.object(adtext, "get_bytes", lambda url, params=None: CHALLENGE.encode()):
            code, out = self.run_match("https://protected.example.com/job/1")
        self.assertEqual(code, 1)
        self.assertIn("save the page", out)


if __name__ == "__main__":
    unittest.main()
