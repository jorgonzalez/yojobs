import unittest

from yojobs.remote import remote_evidence, remote_region


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



class RemoteRegion(unittest.TestCase):
    def test_regions_named_with_remote(self):
        self.assertEqual(remote_region("Fully remote and global, we are in the middle of it."), "global")
        self.assertEqual(remote_region("This role is remote within the EU (CET +/- 2h)."), "EU, CET")

    def test_no_allowed_region(self):
        self.assertEqual(remote_region("Why Join? Fully remote role based in Barcelona, Spain"), "")
        self.assertEqual(remote_region("Full remote flexibility, work from wherever you like."), "")
        self.assertEqual(remote_region("Offices in Germany. The role is on-site in Munich."), "")  # no "remote"

if __name__ == "__main__":
    unittest.main()
