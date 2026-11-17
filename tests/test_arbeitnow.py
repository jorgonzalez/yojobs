import unittest

from yojobs.sources.arbeitnow import to_job

BASE = {"slug": "x", "company_name": "Acme GmbH", "title": "Head of Platform (m/w/d)", "url": "https://www.arbeitnow.com/jobs/x",
        "location": "Berlin", "created_at": 1794900663, "tags": ["DevOps"], "job_types": ["Full time"],
        "description": "<p>We run Kubernetes on GCP.</p>", "remote": False}


class ToJob(unittest.TestCase):
    def test_fields(self):
        j = to_job(BASE)
        self.assertEqual((j.title, j.company, j.location), ("Head of Platform (m/w/d)", "Acme GmbH", "Berlin"))
        self.assertEqual(j.description, "We run Kubernetes on GCP.")
        self.assertEqual(j.tags, ["DevOps", "Full time"])
        self.assertEqual(j.published.year, 2026)
        self.assertIs(j.remote, False)

    def test_remote_flag_and_description(self):
        self.assertIs(to_job(dict(BASE, remote=True)).remote, True)
        j = to_job(dict(BASE, description="This position is fully remote within Germany."))
        self.assertIs(j.remote, True)
        self.assertEqual(j.source_notes, ["remote per description, check"])


if __name__ == "__main__":
    unittest.main()
