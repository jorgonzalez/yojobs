"""company_lists: files of company names with action warn (note in the email) or block."""
import io
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import yaml

from yojobs import __main__ as m
from yojobs import company_lists
from yojobs.config import load_config
from yojobs.models import Job
from yojobs.store import Store

NARNIA = """# companies founded in Narnia
Cair Paravel Systems | Cair Paravel     # founded in Narnia, HQ in Archenland
Lantern Waste Labs

Via
"""
PROFILE = {"title_must_have": {"role": ["Head of"], "area": ["Platform"]}, "where": {"onsite_cities": ["Berlin"]}}


def config_dir(d, lists, blocked=()):
    root = Path(d) / "config"
    (root / "company_lists").mkdir(parents=True)
    (root / "company_lists" / "narnia.txt").write_text(NARNIA)
    (root / "blocklist.yaml").write_text(yaml.safe_dump({"blocked_companies": list(blocked), "company_lists": lists}))
    (root / "profile.yaml").write_text(yaml.safe_dump({"profile": PROFILE}))
    return root


class Lists(unittest.TestCase):
    def test_names_aliases_and_comments(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "l.txt"
            p.write_text(NARNIA)
            self.assertEqual(company_lists.read_names(p),
                             ["Cair Paravel Systems", "Cair Paravel", "Lantern Waste Labs", "Via"])

    def test_warn_list_flags_whole_names_only(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = load_config(config_dir(d, [{"file": "company_lists/narnia.txt", "label": "Narnian company"}]))
        self.assertNotIn("company_lists", cfg)
        self.assertEqual(company_lists.flag(cfg, "Lantern Waste Labs GmbH"), "Narnian company")
        self.assertEqual(company_lists.flag(cfg, "cair paravel"), "Narnian company")
        self.assertEqual(company_lists.flag(cfg, "Via"), "Narnian company")
        self.assertEqual(company_lists.flag(cfg, "Viaplay"), "")             # whole names only
        self.assertEqual(company_lists.flag(cfg, "Archenland Ltd"), "")
        self.assertEqual(company_lists.flag({}, "Via"), "")                  # no lists

    def test_block_list_joins_the_blocklist(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = load_config(config_dir(d, [{"file": "company_lists/narnia.txt", "action": "block"}],
                                         blocked=["Telmar Inc"]))
        self.assertEqual(cfg["blocked_companies"][0], "Telmar Inc")
        self.assertIn("Lantern Waste Labs", cfg["blocked_companies"])
        self.assertEqual(cfg["flagged_companies"], {})

    def test_config_problems_stop_with_a_message(self):
        for lists in ([{"file": "company_lists/missing.txt"}],
                      [{"file": "company_lists/narnia.txt", "action": "hide"}],
                      [{"label": "no file"}]):
            with tempfile.TemporaryDirectory() as d, self.assertRaises(SystemExit) as cm:
                load_config(config_dir(d, lists))
            self.assertIn("company_lists", str(cm.exception))


class InRun(unittest.TestCase):
    def test_warned_job_is_emailed_with_a_note(self):
        now = datetime.now(timezone.utc)
        found = [Job("fake", "Head of Platform", c, f"https://x/{c}", location="Berlin",
                     description="Kubernetes", published=now) for c in ("Cair Paravel GmbH", "Other AG")]
        cfg = {"sources": {"fake": {}}, "flagged_companies": {company_lists.company_key("Cair Paravel"): "Narnian company"},
               "profiles": [{"groups": {"role": ["Head of"], "area": ["Platform"]}, "onsite_cities": ["Berlin"]}]}
        sent = []
        args = SimpleNamespace(source=None, all=False, email=True)
        with tempfile.TemporaryDirectory() as d, mock.patch.dict(m.SOURCES, {"fake": lambda c, s: found}, clear=True), \
                mock.patch.object(m.mailer, "send", lambda c, new, *a: sent.extend(new)), \
                redirect_stdout(io.StringIO()), mock.patch("sys.stderr", io.StringIO()):
            m.run(args, cfg, Store(Path(d) / "db.sqlite"), 3)
        notes = {j.company: j.notes for j in sent}
        self.assertIn("⚠ Narnian company", notes["Cair Paravel GmbH"])
        self.assertNotIn("⚠ Narnian company", notes["Other AG"])


if __name__ == "__main__":
    unittest.main()
