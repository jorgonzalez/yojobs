import unittest

from yojobs.remote import remote_evidence


class RemoteEvidence(unittest.TestCase):
    def test_remote(self):
        self.assertEqual(remote_evidence("Engineering Manager - Platform Core *EU/UK remote*", ""), "title")
        for d in ["This is a fully remote role.", "100% remote", "We are remote-first.", "Vollständig remote",
                  "Remote (Germany)", "You can work remote within Germany.", "work from anywhere in the EU",
                  "This is a remote position.", "100% Homeoffice möglich", "Du arbeitest komplett im Homeoffice",
                  "ortsunabhängig in ganz Deutschland"]:
            self.assertEqual(remote_evidence("DevOps Manager", d), "description", d)

    def test_not_remote(self):
        for d in ["", "Our office is in Munich, hybrid with 3 office days.",
                  "We support remote collaboration tools.", "Occasional remote work possible.",
                  "2 Tage Homeoffice pro Woche", "mobiles Arbeiten möglich"]:
            self.assertEqual(remote_evidence("DevOps Manager", d), "", d)


if __name__ == "__main__":
    unittest.main()
