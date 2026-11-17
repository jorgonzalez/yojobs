import io
import tempfile
from contextlib import redirect_stdout
import unittest
from pathlib import Path

from yojobs.config import ConfigError, load_config, normalize, read_raw

ROOT = Path(__file__).resolve().parent.parent


def folder(files):
    d = tempfile.TemporaryDirectory()
    for name, text in files.items():
        (Path(d.name) / name).write_text(text)
    return d


class Folder(unittest.TestCase):
    def test_example_loads(self):
        cfg = load_config(ROOT / "config.example")
        self.assertEqual(cfg["profiles"][0]["name"], "platform-leadership")
        self.assertEqual(len(cfg["sources"]["linkedin"]["searches"]), 20)
        self.assertEqual(len(cfg["sources"]["indeed"]["searches"]), 16)
        self.assertGreater(len(cfg["sources"]["companies"]["boards"]), 100)

    def test_same_key_in_two_files_is_an_error(self):
        with folder({"a.yaml": "max_age_days: 3\n", "b.yaml": "max_age_days: 5\n"}) as d:
            with self.assertRaises(ConfigError) as e:
                read_raw(Path(d))
        self.assertIn("a.yaml", str(e.exception))
        self.assertIn("b.yaml", str(e.exception))

    def test_single_file_still_works(self):
        with folder({"config.yaml": "max_age_days: 2\nsources: {remotive: {enabled: false}}\n"
                                    "profiles: [{name: p, groups: {a: [x]}, all_of: [k], none_of: [y]}]\n"}) as d:
            cfg = load_config(Path(d) / "config.yaml")
        self.assertEqual(cfg["max_age_days"], 2)
        self.assertEqual(cfg["sources"]["remotive"], {"enabled": False})
        self.assertEqual(cfg["profiles"][0]["all_of"], ["k"])


class Normalize(unittest.TestCase):
    def test_sources_on_off(self):
        cfg = normalize({"sources": {"a": True, "b": False, "c": {"enabled": True, "max_pages": 2}}})
        self.assertEqual(cfg["sources"], {"a": {"enabled": True}, "b": {"enabled": False},
                                          "c": {"enabled": True, "max_pages": 2}})

    def test_searches_places_outer_terms_inner(self):
        cfg = normalize({"sources": {"linkedin": True, "indeed": True}, "searches": [
            {"terms": ["A", "B"], "places": [{"location": "Berlin"}, {"location": "Germany", "remote": True}]},
            {"terms": ["C"], "places": [{"location": "EU", "remote": True}], "only": ["linkedin"]}]})
        li = [(s["term"], s["location"]) for s in cfg["sources"]["linkedin"]["searches"]]
        self.assertEqual(li, [("A", "Berlin"), ("B", "Berlin"), ("A", "Germany"), ("B", "Germany"), ("C", "EU")])
        self.assertEqual(len(cfg["sources"]["indeed"]["searches"]), 4)
        self.assertTrue(cfg["sources"]["linkedin"]["searches"][2]["remote"])

    def test_companies_grouped_by_system(self):
        cfg = normalize({"sources": {"companies": True}, "companies": {"greenhouse": ["a", "b"], "ashby": ["c"]}})
        self.assertEqual(cfg["sources"]["companies"]["boards"], ["greenhouse:a", "greenhouse:b", "ashby:c"])
        with self.assertRaises(ConfigError):
            normalize({"companies": {"workday": ["x"]}})

    def test_profile_renames_and_groups(self):
        cfg = normalize({"profile": {"title_must_have": {"r": ["Head of"]}, "ad_must_mention": ["K8s"],
                                     "exclude_titles": {"sales": ["Sales"], "it": ["IT Manager"]},
                                     "where": {"onsite_cities": ["Berlin"], "remote_regions": ["EU"]}}})
        p = cfg["profiles"][0]
        self.assertEqual((p["groups"], p["all_of"], p["none_of"]), ({"r": ["Head of"]}, ["K8s"], ["Sales", "IT Manager"]))
        self.assertEqual((p["onsite_cities"], p["remote_regions"]), (["Berlin"], ["EU"]))


class Split(unittest.TestCase):
    def test_round_trip(self):
        from yojobs.config_split import run
        old = ("max_age_days: 3\nblocked_companies: [Acme]\n"
               "sources:\n  remotive: {enabled: true}\n  linkedin: {enabled: true, searches: ["
               "{term: A, location: Berlin}, {term: B, location: Berlin}, {term: A, location: EU, remote: true}]}\n"
               "  indeed: {enabled: true, searches: [{term: A, location: Berlin}, {term: B, location: Berlin}]}\n"
               "  companies: {enabled: true, boards: ['ashby:x', 'greenhouse:y']}\n"
               "profiles: [{name: p, groups: {r: [Head of]}, all_of: ['K|L'], none_of: [Sales], onsite_cities: [Berlin]}]\n")
        with folder({"config.yaml": old}) as d:
            src, dest = Path(d) / "config.yaml", Path(d) / "config"
            with redirect_stdout(io.StringIO()):
                self.assertEqual(run(src, dest), 0)
            self.assertEqual(sorted(f.name for f in dest.iterdir()),
                             ["blocklist.yaml", "companies.yaml", "profile.yaml", "searches.yaml",
                              "settings.yaml", "sources.yaml"])
            a, b = load_config(src), load_config(dest)
            a["sources"]["companies"]["boards"].sort(); b["sources"]["companies"]["boards"].sort()
            self.assertEqual(a, b)
            with redirect_stdout(io.StringIO()):
                self.assertEqual(run(src, dest), 1)  # refuses to overwrite


if __name__ == "__main__":
    unittest.main()
