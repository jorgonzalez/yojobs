import unittest
from pathlib import Path

from yojobs.sources.euremotejobs import parse_cards

PAGE = (Path(__file__).parent / "fixture_euremotejobs.html").read_text()


class Cards(unittest.TestCase):
    def test_parse(self):
        jobs = parse_cards(PAGE)
        self.assertEqual(len(jobs), 60)
        j = next(j for j in jobs if j.title == "Technical Product Manager")
        self.assertEqual(j.company, "Upscrolled")
        self.assertEqual(j.location, "EMEA")
        self.assertTrue(j.remote)
        self.assertEqual(j.published.strftime("%Y-%m-%d"), "2026-10-24")
        self.assertTrue(all(j.url.startswith("https://euremotejobs.com/job/") for j in jobs))

    def test_location_not_specified_is_empty(self):
        self.assertIn("", {j.location for j in parse_cards(PAGE)})


if __name__ == "__main__":
    unittest.main()
