import tempfile
import unittest
from pathlib import Path
from unittest import mock

from yojobs import discovery, weekly
from yojobs.history import History
from yojobs.models import Job
from yojobs.store import Store


def fake_probes(boards):
    """boards = {(system, id): reported name or ""}: everything else answers 'no board'."""
    return {system: (lambda bid, system=system: boards.get((system, bid))) for system in discovery.PROBES}


class FindBoard(unittest.TestCase):
    def find(self, company, boards):
        with mock.patch.object(discovery, "PROBES", fake_probes(boards)), mock.patch.object(discovery.time, "sleep"):
            return discovery.find_board(company)

    def test_name_reported_and_matching(self):
        self.assertEqual(self.find("Distribusion Technologies GmbH", {("greenhouse", "distribusion"): "Distribusion"}),
                         "greenhouse:distribusion")

    def test_wrong_company_rejected(self):
        self.assertEqual(self.find("Remote", {("greenhouse", "remote"): "General Assembly Remote Jobs"}), "")

    def test_no_name_only_for_the_full_name(self):
        self.assertEqual(self.find("Acme Cloud", {("ashby", "acmecloud"): ""}), "ashby:acmecloud")
        self.assertEqual(self.find("Acme Cloud", {("ashby", "acme"): ""}), "")       # first word only: not trusted

    def test_lever_eu(self):
        self.assertEqual(self.find("Quantinuum", {("lever:eu", "quantinuum"): ""}), "lever:eu:quantinuum")

    def test_covered_by_an_eu_board(self):
        self.assertTrue(discovery.covered("Quantinuum", ["lever:eu:quantinuum"]))
        self.assertTrue(discovery.covered("Mistral AI", ["ashby:mistral.ai"]))


class Run(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.tmp.name) / "db.sqlite")
        self.h = History(self.store.db)

    def tearDown(self):
        self.store.db.close()
        self.tmp.cleanup()

    def test_checks_new_companies_once_and_suggests(self):
        jobs = [Job(source="linkedin", title="EM Infrastructure", company="Distribusion Technologies", url="https://a"),
                Job(source="linkedin", title="Head of Platform", company="Mimica", url="https://b"),        # already configured
                Job(source="linkedin", title="EM Cloud", company="Blocked Corp", url="https://c")]          # blocked
        self.store.mark_seen(jobs[1:])
        self.h.add_near_misses([(jobs[0], "no Kubernetes in the ad")])
        cfg = {"sources": {"companies": {"boards": ["ashby:mimica"]}}, "blocked_companies": ["Blocked Corp"]}
        asked = []

        def probe_gh(bid):
            asked.append(bid)
            return "Distribusion" if bid == "distribusion" else None
        probes = fake_probes({})
        probes["greenhouse"] = probe_gh
        with mock.patch.object(discovery, "PROBES", probes), mock.patch.object(discovery.time, "sleep"), \
                mock.patch.object(discovery, "say"):
            found = discovery.run(self.store.db, cfg)
            again = discovery.run(self.store.db, cfg)                                  # remembered: no new probes
        self.assertEqual(found, [{"board": "greenhouse:distribusion", "company": "Distribusion Technologies",
                                  "example": "EM Infrastructure"}])
        self.assertEqual(again, found)
        self.assertEqual(asked, ["distribusiontechnologies", "distribusion-technologies", "distribusion"])
        # once it's in companies.yaml it's no longer suggested
        cfg["sources"]["companies"]["boards"].append("greenhouse:distribusion")
        with mock.patch.object(discovery, "say"):
            self.assertEqual(discovery.run(self.store.db, cfg), [])
        text = weekly.build(self.h, {}, discoveries=found)[1]
        self.assertIn("greenhouse: distribusion", text)


if __name__ == "__main__":
    unittest.main()
