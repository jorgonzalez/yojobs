import unittest
from unittest import mock

from yojobs.sources import rss, weworkremotely as wwr


def item(title, region, hq):
    desc = f"\n\n<p>\n  <strong>Headquarters:</strong> {hq}\n</p>\n<div><p>Run Kubernetes.</p></div>"
    return (f"<item><title>{title}</title><region>{region}</region>"
            f"<link>https://weworkremotely.com/remote-jobs/{abs(hash(title))}</link>"
            f"<pubDate>Mon, 23 Nov 2026 18:32:28 +0000</pubDate>"
            f"<description><![CDATA[{desc}]]></description></item>")


FEED = ("<rss><channel>"
        + item("Reddit: Engineering Manager, Ranking Platform", "Anywhere in the World", "Remote - United States")
        + item("Pinterest: Manager II, Engineering", "Anywhere in the World", "San Francisco, CA, US; Remote, CA, US")
        + item("Acme: Head of Platform", "Anywhere in the World", "San Francisco, CA")      # a head office
        + item("Beta: Platform Lead", "Europe Only", "Remote")                              # names no place
        + "</channel></rss>").encode()


class WeWorkRemotely(unittest.TestCase):
    def setUp(self):
        with mock.patch.object(rss, "get_bytes", lambda url, params=None: FEED):
            self.jobs = wwr.fetch({}, None)

    def test_remote_headquarters_line_is_the_location(self):
        reddit, pinterest, _, _ = self.jobs
        self.assertEqual((reddit.company, reddit.title), ("Reddit", "Engineering Manager, Ranking Platform"))
        self.assertEqual(reddit.location, "Remote - United States")
        self.assertEqual(pinterest.location, "San Francisco, CA, US; Remote, CA, US")
        self.assertTrue(all(j.remote for j in self.jobs))
        self.assertTrue(reddit.description.startswith("Headquarters: Remote - United States"))

    def test_head_office_or_bare_remote_keeps_the_region(self):
        _, _, acme, beta = self.jobs
        self.assertEqual(acme.location, "Anywhere in the World")
        self.assertEqual(beta.location, "Europe Only")

    def test_us_only_jobs_fail_a_europe_profile(self):
        from yojobs import filter as jobfilter
        profile = {"groups": {"role": ["Manager", "Lead", "Head of"], "area": ["Platform"]},
                   "onsite_cities": ["Berlin"], "remote_regions": ["Germany", "Europe", "Anywhere"]}
        passed = [j.company for j in self.jobs if jobfilter.apply(j, profile)]
        self.assertEqual(passed, ["Acme", "Beta"])


if __name__ == "__main__":
    unittest.main()
