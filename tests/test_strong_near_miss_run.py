"""A near miss with a high CV match goes out with the run's matches, marked with what it lacks."""
import io
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from yojobs import __main__ as m
from yojobs.history import History
from yojobs.models import Job
from yojobs.store import Store

PROFILE = {"groups": {"role": ["Manager"], "area": ["Infrastructure", "Platform"]},
           "all_of": ["Kubernetes"], "all_of_in": ["title", "description"],
           "match_in": ["title"], "remote_regions": ["Germany"]}


def ad(title, description):
    return Job("t", title, "Acme", f"https://x/{title}", location="Germany", remote=True,
               description=description, published=datetime.now(timezone.utc))


class StrongNearMissInRun(unittest.TestCase):
    def run_once(self, store, picked):
        jobs = [ad("Infrastructure Manager", "AI Ops on GCP."), ad("Platform Manager", "Terraform only.")]
        sent = []

        def strong(near, cfg, root, db, skip):
            return [(j, r) for j, r in near if j.title in picked and not skip(j)]
        cfg = {"sources": {"t": {}}, "profiles": [PROFILE]}
        args = SimpleNamespace(source=None, all=False, email=True)
        with mock.patch.dict(m.SOURCES, {"t": lambda cfg, since: jobs}, clear=True), \
                mock.patch.object(m.matching, "strong_near_misses", strong), \
                mock.patch.object(m.matching, "score_jobs"), \
                mock.patch.object(m.mailer, "send", lambda c, new, *a: sent.extend(new)), \
                redirect_stdout(io.StringIO()), mock.patch("sys.stderr", io.StringIO()):
            m.run(args, cfg, store, 3)
        return sent

    def test_strong_one_is_emailed_and_not_kept_for_the_weekly(self):
        with tempfile.TemporaryDirectory() as d:
            store = Store(Path(d) / "db.sqlite")
            sent = self.run_once(store, {"Infrastructure Manager"})
            self.assertEqual([j.title for j in sent], ["Infrastructure Manager"])
            self.assertIn("near miss: no Kubernetes in the ad", sent[0].notes)
            near = [n["title"] for n in History(store.db).pending_near_misses()]
            self.assertEqual(near, ["Platform Manager"])            # the weak one waits for the weekly
            self.assertEqual(self.run_once(store, {"Infrastructure Manager"}), [])  # sent once only
