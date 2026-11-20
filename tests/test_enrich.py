import unittest
from pathlib import Path
from unittest import mock

from yojobs import enrich
from yojobs import filter as jobfilter
from yojobs.models import Job

HERE = Path(__file__).parent
FOUR = "https://4dayweek.io/job/engineering-manager-paas-cloud-at-sainsburys-6aa84790"
WTTJ = "https://www.welcometothejungle.com/en/companies/knime/jobs/team-lead-site-reliability-engineering_berlin_vv6qaslz"
PROFILE = {"groups": {"role": ["Engineering Manager", "Team Lead"], "area": ["Cloud", "Site Reliability"]},
           "all_of": ["Kubernetes|K8s"], "onsite_cities": ["Berlin"], "remote_regions": ["Germany", "Europe"]}


def fixture(name):
    return (HERE / name).read_text()


def enricher(pages):
    calls = []

    def page(url):
        calls.append(url)
        result = pages[url]
        if isinstance(result, Exception):
            raise result
        return result
    e = enrich.Enricher(page=page)
    e.calls = calls
    return e


class FourDayWeek(unittest.TestCase):
    def test_page_data(self):
        d = enrich.fourdayweek(fixture("fixture_4dayweek_job.html"), FOUR)
        self.assertEqual((d.location, d.remote, d.work_mode), ("London, United Kingdom", False, "hybrid"))
        self.assertIn("Kubernetes platform", d.description)
        self.assertNotIn("<p>", d.description)

    def test_other_slug_or_no_data(self):
        self.assertIsNone(enrich.fourdayweek(fixture("fixture_4dayweek_job.html"), "https://4dayweek.io/job/other-job"))
        self.assertIsNone(enrich.fourdayweek("<html></html>", FOUR))

    def test_london_hybrid_no_longer_passes(self):
        # the feed gives no location: an empty location counted as "remote, no restriction"
        job = Job(source="4dayweek", title="Engineering Manager – PaaS Cloud", company="Sainsbury's",
                  url=FOUR, has_description=False)
        self.assertTrue(jobfilter.apply(job, PROFILE))
        e = enricher({FOUR: fixture("fixture_4dayweek_job.html")})
        self.assertIn("location London", e.enrich(job))
        self.assertEqual((job.remote, job.has_description), (False, True))
        self.assertFalse(jobfilter.apply(job, PROFILE))


class JobPosting(unittest.TestCase):
    def test_wttj_page(self):
        d = enrich.job_posting(fixture("fixture_wttj_job.html"))
        self.assertEqual(d.location, "Berlin, DE; Konstanz, DE")
        self.assertIsNone(d.remote)
        self.assertIn("Kubernetes", d.description)

    def test_remote_with_regions(self):
        html = ('<script type="application/ld+json">{"@type": "JobPosting", "description": "Remote role",'
                ' "jobLocationType": "TELECOMMUTE", "applicantLocationRequirements": [{"@type": "Country", "name": "Germany"}]}'
                '</script>')
        d = enrich.job_posting(html)
        self.assertEqual((d.remote, d.location), (True, "Remote: Germany"))

    def test_graph_list_and_junk(self):
        html = ('<script type="application/ld+json">not json</script>'
                '<script type="application/ld+json">{"@graph": [{"@type": "Organization"},'
                ' {"@type": "JobPosting", "description": "x", "jobLocation": {"address": {"addressLocality": "Berlin"}}}]}</script>')
        self.assertEqual(enrich.job_posting(html).location, "Berlin")
        self.assertIsNone(enrich.job_posting("<html></html>"))

    def test_wttj_job_gets_description_but_keeps_its_place(self):
        job = Job(source="welcometothejungle", title="Team Lead Site Reliability Engineering", company="Knime",
                  url=WTTJ, location="Berlin", remote=False, has_description=False)
        e = enricher({WTTJ: fixture("fixture_wttj_job.html")})
        self.assertEqual(e.enrich(job), "description")
        self.assertEqual((job.location, job.remote), ("Berlin", False))
        self.assertTrue(jobfilter.apply(job, PROFILE))        # Kubernetes now verified from the ad


class Ats(unittest.TestCase):
    def test_ashby_link_uses_the_api(self):
        board = {"jobs": [{"id": "60c147b4-ee4b-4d0b-aeef-57f2b018bf84", "descriptionPlain": "Kubernetes on GCP",
                           "location": "Berlin", "secondaryLocations": [{"location": "Remote - Germany"}],
                           "workplaceType": "Hybrid"}]}
        job = Job(source="startupmap", title="Engineering Manager Platform", company="trawa",
                  url="https://jobs.ashbyhq.com/trawa/60c147b4-ee4b-4d0b-aeef-57f2b018bf84", has_description=False)
        e = enricher({})
        with mock.patch.object(enrich, "get_json", return_value=board) as get:
            self.assertIn("work mode Hybrid", e.enrich(job))
        get.assert_called_once_with("https://api.ashbyhq.com/posting-api/job-board/trawa")
        self.assertEqual((job.description, job.location, job.remote), ("Kubernetes on GCP", "Berlin, Remote - Germany", False))
        self.assertEqual(e.calls, [])                          # no page opened

    def test_ashby_board_with_spaces(self):
        with mock.patch.object(enrich, "get_json", return_value={"jobs": []}) as get:
            enrich.Enricher(page=None).details(
                "https://jobs.ashbyhq.com/Superhuman%20Platform%20Inc/19eb6017-53bd-40a6-808e-65ffbcb68745")
        get.assert_called_once_with("https://api.ashbyhq.com/posting-api/job-board/Superhuman Platform Inc")

    def test_greenhouse_and_lever_links(self):
        with mock.patch.object(enrich, "get_json", return_value={"content": "&lt;p&gt;K8s&lt;/p&gt;",
                                                                 "location": {"name": "Berlin"}}) as get:
            d = enrich.Enricher(page=None).details("https://job-boards.greenhouse.io/acme/jobs/123?gh_src=x")
        get.assert_called_once_with("https://boards-api.greenhouse.io/v1/boards/acme/jobs/123")
        self.assertEqual((d.description, d.location), ("K8s", "Berlin"))
        lever = {"descriptionPlain": "Intro", "lists": [{"text": "You", "content": "<li>run K8s</li>"}],
                 "categories": {"allLocations": ["Berlin"]}, "workplaceType": "remote"}
        with mock.patch.object(enrich, "get_json", return_value=lever) as get:
            d = enrich.Enricher(page=None).details("https://jobs.eu.lever.co/acme/0f6c6d3e-1111-2222-3333-444455556666")
        get.assert_called_once_with("https://api.eu.lever.co/v0/postings/acme/0f6c6d3e-1111-2222-3333-444455556666")
        self.assertEqual((d.location, d.remote), ("Berlin", True))
        self.assertIn("You: run K8s", d.description)


class Limits(unittest.TestCase):
    def job(self, url):
        return Job(source="4dayweek", title="EM", company="x", url=url, has_description=False)

    def test_blocked_site_is_not_asked_again(self):
        a, b = "https://site.example/a", "https://site.example/b"
        e = enricher({a: enrich.Blocked("HTTP 429"), b: "<html></html>"})
        with mock.patch.object(enrich.time, "sleep"), mock.patch.object(enrich, "note"):
            self.assertEqual(e.enrich(self.job(a)), "failed (HTTP 429)")
            self.assertIn("said HTTP 429", e.enrich(self.job(b)))
        self.assertEqual(e.calls, [a])

    def test_limit_and_pause(self):
        pages = {f"https://site.example/{i}": "<html></html>" for i in range(4)}
        e = enricher(pages)
        e.limit = 2
        with mock.patch.object(enrich.time, "sleep") as sleep:
            results = [e.enrich(self.job(u)) for u in pages]
        self.assertEqual(results[:2], ["nothing found"] * 2)
        self.assertTrue(all("limit" in r for r in results[2:]))
        self.assertEqual(sleep.call_count, 1)                  # between the 2 lookups, not before the first

    def test_errors_leave_the_job_alone(self):
        url = "https://site.example/x"
        job = self.job(url)
        e = enricher({url: ValueError("odd page")})
        self.assertTrue(e.enrich(job).startswith("failed (ValueError"))
        self.assertEqual((job.description, job.has_description), ("", False))

    def test_only_wanted_jobs_that_need_details(self):
        jobs = [self.job("https://site.example/1"), Job(source="x", title="EM", company="y", url="https://site.example/2"),
                self.job("https://site.example/3")]
        e = enricher({"https://site.example/1": "<html></html>"})
        with mock.patch.object(enrich, "say"):
            n = enrich.enrich_jobs(jobs, lambda j: j.url.endswith("1") or j.url.endswith("2"), e)
        self.assertEqual((n, e.calls), (1, ["https://site.example/1"]))


if __name__ == "__main__":
    unittest.main()
