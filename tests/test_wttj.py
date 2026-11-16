import unittest

from yojobs.sources.welcometothejungle import _job


class SitemapUrl(unittest.TestCase):
    def test_parse(self):
        j = _job("https://www.welcometothejungle.com/en/companies/trawa/jobs/"
                 "engineering-manager-platform-and-it-compliance_berlin_2u2iuuho", "2026-10-22T00:16:51+00:00")
        self.assertEqual(j.title, "Engineering Manager Platform And It Compliance")
        self.assertEqual(j.company, "Trawa")
        self.assertEqual(j.location, "Berlin")
        self.assertFalse(j.has_description)
        self.assertIsNone(j.remote)

    def test_company_suffix_and_no_city(self):
        j = _job("https://www.welcometothejungle.com/fr/companies/alten-1/jobs/chef-de-projet-h-f_huvdonep", "2026-11-07")
        self.assertEqual(j.company, "Alten")
        self.assertEqual(j.location, "")


if __name__ == "__main__":
    unittest.main()
