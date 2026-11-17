import unittest

from yojobs import filter as jf
from yojobs.sources.welcometothejungle import _job

BASE = "https://www.welcometothejungle.com/{}/companies/{}/jobs/{}"
PROFILE = {"groups": {"role": ["Director", "Manager"], "area": ["Infrastructure", "Platform"]},
           "match_in": ["title"], "onsite_cities": ["Berlin"], "remote_regions": ["Europe", "Germany"]}


class SitemapUrl(unittest.TestCase):
    def test_title_city_id(self):
        j = _job(BASE.format("en", "trawa", "engineering-manager-platform-and-it-compliance_berlin_2u2iuuho"),
                 "2026-10-22T00:16:51+00:00")
        self.assertEqual(j.title, "Engineering Manager Platform And It Compliance")
        self.assertEqual(j.company, "Trawa")
        self.assertEqual(j.location, "Berlin")
        self.assertFalse(j.has_description)

    def test_title_city(self):  # the most common form: no id at all
        j = _job(BASE.format("en", "front-1", "director-of-it-corporate-security-infrastructure_san-francisco"), "2026-11-16")
        self.assertEqual(j.title, "Director Of It Corporate Security Infrastructure")
        self.assertEqual(j.company, "Front")
        self.assertEqual(j.location, "San Francisco")

    def test_title_city_ats_id(self):
        j = _job(BASE.format("fr", "thales", "responsable-integration-f-h_elancourt_THALE_Pd6Aa9k"), "2026-11-07")
        self.assertEqual((j.title, j.location), ("Responsable Integration F H", "Elancourt"))
        j = _job(BASE.format("fr", "burger-king-1",
                             "alternance-equipier-cap-h-f-_-echirolles-grand-place-38_echirolles_BKF_eoWOpWZ"), "2026-11-07")
        self.assertEqual(j.location, "Echirolles")
        self.assertEqual(j.company, "Burger King")

    def test_uuid_only_is_skipped(self):
        self.assertIsNone(_job(BASE.format("fr", "alten-1", "3e7b6203-022d-4108-8f5f-70ee2c91a6f3"), "2026-11-07"))

    def test_only_berlin_passes(self):
        sf = _job(BASE.format("en", "front-1", "director-of-platform-infrastructure_san-francisco"), "2026-11-16")
        berlin = _job(BASE.format("en", "acme", "director-of-platform-infrastructure_berlin"), "2026-11-16")
        nowhere = _job(BASE.format("en", "acme", "director-of-platform-infrastructure_x_y_z"), "2026-11-16")
        nowhere.location = ""
        self.assertFalse(jf.apply(sf, PROFILE))
        self.assertTrue(jf.apply(berlin, PROFILE))
        self.assertFalse(jf.apply(nowhere, PROFILE))   # unknown place is not "remote"


if __name__ == "__main__":
    unittest.main()
