import unittest
from unittest import mock

from yojobs.sources import rss, wpjobmanager

FEED = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:content="http://purl.org/rss/1.0/modules/content/"
     xmlns:job_listing="https://wpjobmanager.com"><channel>
<item><title>Head of Platform Engineering</title><link>https://euroremotejobs.com/job/head-of-platform/</link>
<pubDate>Mon, 16 Nov 2026 16:54:56 +0000</pubDate><description><![CDATA[Short teaser...]]></description>
<content:encoded><![CDATA[<p>Lead our <strong>Kubernetes</strong> platform team.</p>]]></content:encoded>
<job_listing:location><![CDATA[Europe]]></job_listing:location><job_listing:company><![CDATA[Acme]]></job_listing:company>
<job_listing:job_type><![CDATA[Full Time]]></job_listing:job_type><job_listing:salary><![CDATA[EUR 120k]]></job_listing:salary>
</item></channel></rss>"""


class Feed(unittest.TestCase):
    def test_item_fields(self):
        with mock.patch.object(rss, "get_bytes", lambda url, params=None: FEED):
            (job,) = wpjobmanager.fetch_euroremotejobs({}, None)
        self.assertEqual((job.title, job.company, job.location, job.salary),
                         ("Head of Platform Engineering", "Acme", "Europe", "EUR 120k"))
        self.assertEqual(job.description, "Lead our Kubernetes platform team.")  # full ad, not the teaser
        self.assertTrue(job.remote)
        self.assertEqual(job.published.isoformat(), "2026-11-16T16:54:56+00:00")

    def test_country_lists_lose_the_generic_europe(self):
        self.assertEqual(wpjobmanager.clean_location("United Kingdom, Europe"), "United Kingdom")
        self.assertEqual(wpjobmanager.clean_location("Germany, Europe"), "Germany")
        self.assertEqual(wpjobmanager.clean_location("Europe"), "Europe")
        self.assertEqual(wpjobmanager.clean_location("Europe, EMEA"), "Europe, EMEA")

    def test_uk_only_is_dropped_by_the_region_rule(self):
        from yojobs import filter as jf
        profile = {"remote_regions": ["Germany", "Europe"], "onsite_cities": ["Berlin"]}
        uk = wpjobmanager.to_job("euroremotejobs", {"title": "x", "location": "United Kingdom, Europe"})
        de = wpjobmanager.to_job("euroremotejobs", {"title": "x", "location": "Germany, Europe"})
        self.assertFalse(jf.place_ok(uk, profile))
        self.assertTrue(jf.place_ok(de, profile))

    def test_urls_respect_robots(self):
        seen = []
        with mock.patch.object(rss, "get_bytes", lambda url, params=None: seen.append(url) or FEED):
            wpjobmanager.fetch_jobspresso({}, None)
            wpjobmanager.fetch_euroremotejobs({}, None)
        self.assertEqual(seen[0], "https://jobspresso.co/feed/job_feed/")      # no "?" (disallowed there)
        self.assertIn("posts_per_page=100", seen[1])


if __name__ == "__main__":
    unittest.main()
