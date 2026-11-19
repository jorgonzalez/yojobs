import unittest

from yojobs.__main__ import match_report
from yojobs.models import Job


def job(title, company, source):
    return Job(source, title, company, f"https://example.com/{source}")


class MatchReport(unittest.TestCase):
    def test_lines_and_summary(self):
        outcomes = [
            (job("DevOps Manager", "Consensys", "remoterocketship"), "new", ("", "", "")),
            (job("EM, Infrastructure (Remote)", "Miaplaza", "arbeitnow"), "sent",
             ("EM, Infrastructure", "himalayas", "2026-11-17T06:57:33+00:00")),
            (job("EM, Infrastructure", "Miaplaza", "himalayas"), "sent",
             ("EM, Infrastructure", "himalayas", "2026-11-17T06:57:33+00:00")),
            (job("DevOps Manager (Remote)", "Consensys", "startupmap"), "duplicate",
             ("DevOps Manager", "remoterocketship", "")),
        ]
        lines = match_report(outcomes)
        self.assertEqual(lines[0], "  matches:")
        self.assertIn("emailed now", lines[1])
        self.assertIn('already sent 17 Nov (as "EM, Infrastructure", from himalayas)', lines[2])
        self.assertTrue(lines[3].endswith("already sent 17 Nov"))          # same ad: nothing to add
        self.assertIn('same job as "DevOps Manager" (remoterocketship) in this run', lines[4])
        self.assertEqual(lines[-1], "  summary: 4 matches: 1 new (emailed), 2 already sent before, 1 duplicate in this run")

    def test_no_matches(self):
        self.assertEqual(match_report([]), ["  summary: 0 matches: 0 new, 0 already sent before, 0 duplicates in this run"])

    def test_preview_wording(self):
        lines = match_report([(job("DevOps Manager", "Consensys", "x"), "new", ("", "", ""))], emailed=False)
        self.assertNotIn("emailed", "\n".join(lines))


if __name__ == "__main__":
    unittest.main()
