import io
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from yojobs import __main__ as m
from yojobs.models import Job
from yojobs.store import Store


def jobs(cfg, since):
    now = datetime.now(timezone.utc)
    return [Job(source="fake", title=f"Head of Platform {i}", company=c, url=f"https://x/{i}", location="Berlin",
                description="Kubernetes", published=now)
            for i, c in enumerate(["GetYourGuide", "Get Your Guide GmbH", "ACME, Inc.", "Other AG"])]


class Blocklist(unittest.TestCase):
    def test_company_key(self):
        self.assertEqual(m._company_key("Get Your Guide GmbH"), m._company_key("getyourguide"))
        self.assertEqual(m._company_key("ACME, Inc."), m._company_key("Acme"))
        self.assertNotEqual(m._company_key("Acme"), m._company_key("Acme Labs"))

    def test_blocked_jobs_are_dropped(self):
        cfg = {"sources": {"fake": {}}, "blocked_companies": ["getyourguide", "Acme"],
               "profiles": [{"groups": {"role": ["Head of"], "area": ["Platform"]}, "onsite_cities": ["Berlin"]}]}
        args = SimpleNamespace(source=None, all=False, email=False)
        with tempfile.TemporaryDirectory() as d, mock.patch.dict(m.SOURCES, {"fake": jobs}, clear=True):
            out = io.StringIO()
            with redirect_stdout(out), mock.patch("sys.stderr", io.StringIO()):
                m.run(args, cfg, Store(Path(d) / "db.sqlite"), 3)
        text = out.getvalue()
        self.assertIn("Other AG", text)
        for blocked in ("GetYourGuide", "Get Your Guide GmbH", "ACME, Inc."):
            self.assertNotIn(blocked, text)


if __name__ == "__main__":
    unittest.main()
