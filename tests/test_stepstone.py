import unittest
from pathlib import Path
from unittest import mock

from yojobs import filter as jf
from yojobs.config import normalize
from yojobs.sources import stepstone

PAGE = (Path(__file__).parent / "fixture_stepstone.html").read_text()
PROFILE = {"groups": {"role": ["Manager", "Team Lead", "Teamleiter"], "area": ["SRE", "DevOps", "Infrastructure"]},
           "all_of": ["Kubernetes|K8s"], "match_in": ["title"], "onsite_cities": ["Berlin"],
           "remote_regions": ["Europe"]}


class Parse(unittest.TestCase):
    def test_records_and_fields(self):
        jobs = [stepstone.to_job(o) for o in stepstone.records(PAGE)]
        self.assertEqual(len(jobs), 3)
        em = next(j for j in jobs if j.title.startswith("Engineering Manager"))
        self.assertEqual(em.title, "Engineering Manager SRE & DevOps (d/f/m)")
        self.assertNotIn("?", em.url)                          # tracking parameters dropped
        self.assertIn("Kubernetes", em.description)
        self.assertEqual(em.tags, ["Kubernetes", "Terraform"])
        self.assertEqual((em.remote, em.work_mode), (False, "hybrid"))
        self.assertEqual(em.published.year, 2026)

    def test_match_only_with_kubernetes_in_excerpt(self):
        jobs = {j.title[:20]: j for j in (stepstone.to_job(o) for o in stepstone.records(PAGE))}
        self.assertTrue(jf.apply(jobs["Engineering Manager "], PROFILE))
        self.assertFalse(jf.apply(next(j for t, j in jobs.items() if "Network" in j.title), PROFILE))

    def test_slug(self):
        self.assertEqual(stepstone.slug("SRE Team Lead"), "sre-team-lead")
        self.assertEqual(stepstone.slug("München"), "muenchen")


    def test_german_summary_of_an_english_ad_is_not_skipped(self):
        """StepStone's excerpt is German even for English ads; the benefits text decides."""
        profile = dict(PROFILE, skip_ad_languages=["de"])
        summary = ("Kleinanzeigen ist Deutschlands meistbesuchte Plattform. Gesucht wird ein Engineering Manager "
                   "SRE & DevOps, um zwei Teams mit etwa 10 Ingenieuren zu führen und die Plattform sowie die "
                   "Pipelines zu verantworten. Erfahrung mit Kubernetes und Terraform ist wichtig für die Rolle "
                   "und wir bieten eine moderne Umgebung mit vielen Möglichkeiten für dich und dein Team.")
        english = ("<ul><li>We offer flexible working hours and a hybrid setup in our Berlin office</li>"
                   "<li>You get a learning budget, a great team and the chance to shape our platform</li>"
                   "<li>We are an equal opportunity employer and we value diversity in all of our teams</li></ul>")
        german = ("<ul><li>Wir bieten flexible Arbeitszeiten und ein modernes Büro in Berlin für dich</li>"
                  "<li>Du bekommst ein Weiterbildungsbudget und ein tolles Team mit vielen Möglichkeiten</li>"
                  "<li>Wir sind ein Arbeitgeber, der Vielfalt schätzt und die Chancengleichheit fördert</li></ul>")
        base = {"title": "Engineering Manager SRE & DevOps (d/f/m)", "companyName": "kleinanzeigen.de GmbH",
                "url": "https://www.stepstone.de/stellenangebote--x-1-inline.html", "location": "Berlin",
                "textSnippet": summary, "skills": [{"name": "Kubernetes"}]}
        self.assertTrue(jf.apply(stepstone.to_job(dict(base, jobBenefitsHtml=english)), profile))
        self.assertFalse(jf.apply(stepstone.to_job(dict(base, jobBenefitsHtml=german)), profile))

class Fetch(unittest.TestCase):
    def run_fetch(self, fail=()):
        urls = []

        def fake_get(url, params=None):
            urls.append(url)
            if any(f in url for f in fail):
                raise TimeoutError("slow")
            return PAGE.encode()
        cfg = normalize({"sources": {"stepstone": True}, "searches": [
            {"terms": ["SRE Team Lead", "Head of SRE"], "places": [{"location": "Berlin"},
                                                                  {"location": "Germany", "remote": True}]}]})
        scfg = dict(cfg["sources"]["stepstone"], delay_seconds=0, _problems=[])
        with mock.patch.object(stepstone, "get_bytes", fake_get), mock.patch.object(stepstone, "say"):
            jobs = stepstone.fetch(scfg, None)
        return urls, jobs, scfg["_problems"]

    def test_city_searches_only_and_dedupe(self):
        urls, jobs, problems = self.run_fetch()
        self.assertEqual(urls, ["https://www.stepstone.de/jobs/sre-team-lead/in-berlin",
                                "https://www.stepstone.de/jobs/head-of-sre/in-berlin"])   # no remote/Germany search
        self.assertEqual(len(jobs), 3)                                                    # same jobs on both pages
        self.assertEqual(problems, [])

    def test_one_failed_search_is_reported_not_fatal(self):
        urls, jobs, problems = self.run_fetch(fail=("head-of-sre",))
        self.assertEqual(len(jobs), 3)
        self.assertEqual(problems[0][0], "Head of SRE in Berlin")

    def test_all_failed_is_an_error(self):
        with self.assertRaises(RuntimeError):
            self.run_fetch(fail=("in-berlin",))


if __name__ == "__main__":
    unittest.main()
