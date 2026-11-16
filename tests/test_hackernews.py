import unittest

from yojobs.sources.hackernews import parse_post


class FirstLine(unittest.TestCase):
    def test_remote_worldwide(self):
        c, role, loc, remote = parse_post("Simple Analytics | DevOps Engineer | REMOTE (worldwide, any timezone) | Full-time | €5,000/month | https://x.io")
        self.assertEqual(c, "Simple Analytics")
        self.assertEqual(role, "DevOps Engineer")
        self.assertTrue(remote)
        self.assertIn("worldwide", loc.lower())

    def test_remote_us_only(self):
        _, _, loc, remote = parse_post("Synteq | Growth Lead & Systems Administrator | Austin, TX | REMOTE (US) | Full-time")
        self.assertTrue(remote)
        self.assertEqual(loc, "Remote, US only")

    def test_berlin_onsite(self):
        _, role, loc, remote = parse_post("Acme | Engineering Manager, Platform | Berlin | ONSITE")
        self.assertEqual(role, "Engineering Manager, Platform")
        self.assertEqual(loc, "Berlin")
        self.assertFalse(remote)

    def test_remote_eu(self):
        _, _, loc, remote = parse_post("Acme | Head of Infrastructure | REMOTE (EU, CET ±3)")
        self.assertTrue(remote)
        self.assertTrue(loc.startswith("Remote, "))
        self.assertIn("EU", loc)

    def test_onsite_elsewhere(self):
        _, _, loc, remote = parse_post("Acme | SRE Manager | Utrecht, The Netherlands | HYBRID")
        self.assertFalse(remote)
        self.assertIn("Utrecht", loc)


if __name__ == "__main__":
    unittest.main()
