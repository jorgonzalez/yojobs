import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock

from yojobs import weekly
from yojobs.sources import stapply

NOW = datetime.now(timezone.utc)
POSTED = (NOW - timedelta(hours=5)).isoformat()
ROWS = [
    {"url": "https://x.bamboohr.com/careers/1", "title": "Platform Engineering Lead", "company": "Acme",
     "location": "Remote", "locations": None, "country_iso": None, "is_remote": True, "workplace_type": "remote",
     "posted_at": POSTED},
    {"url": "https://x.bamboohr.com/careers/2", "title": "Team Lead SRE", "company": "Knime",
     "location": "Konstanz, Germany",
     "locations": '[{"label":"Konstanz, Germany"},{"label":"Berlin, Germany","country_iso":"DE"}]',
     "country_iso": "DE", "is_remote": None, "workplace_type": "hybrid", "posted_at": POSTED},
    {"url": "https://x.bamboohr.com/careers/3", "title": "Accountant", "company": "Acme", "location": "Berlin",
     "locations": None, "country_iso": "DE", "is_remote": False, "workplace_type": None, "posted_at": POSTED},
]
COLUMNS = {"url", "title", "company", "location", "locations", "country_iso", "is_remote", "workplace_type",
           "posted_at", "is_stale", "description"}


def manifest(sha="abc"):
    return {"generated_at": "2026-11-20T15:30:00+00:00",
            "by_ats": {"bamboohr": {"parquet": "https://storage.example/bamboohr/jobs.parquet",
                                    "parquet_sha256": sha}}}


class FakeDB:
    def __init__(self, columns=COLUMNS):
        self.cols, self.calls = columns, []

    def columns(self, url):
        return self.cols

    def rows(self, sql, params):
        self.calls.append((sql, params))
        if "description" in sql.split("FROM")[0]:
            return [{"url": u, "description": "We run Kubernetes."} for u in params[0]]
        return ROWS


class FakeState(dict):
    def set(self, name, value):
        self[name] = value


def run(db, state=None, sha="abc", **cfg):
    cfg = dict({"slices": ["bamboohr"], "_db": db, "_state": state if state is not None else FakeState(),
                "_title_ok": lambda j: "Lead" in j.title, "_known": lambda j: False, "_problems": []}, **cfg)
    with mock.patch.object(stapply, "get_json", return_value=manifest(sha)), mock.patch.object(stapply, "say"), \
            mock.patch.object(stapply, "note"):
        return stapply.fetch(cfg, NOW - timedelta(days=1)), cfg


class Fetch(unittest.TestCase):
    def test_jobs_and_ad_text_only_for_fitting_titles(self):
        db = FakeDB()
        jobs, cfg = run(db)
        self.assertEqual([j.title for j in jobs], ["Platform Engineering Lead", "Team Lead SRE", "Accountant"])
        self.assertEqual([j.has_description for j in jobs], [True, True, False])
        self.assertEqual(db.calls[1][1], [["https://x.bamboohr.com/careers/1", "https://x.bamboohr.com/careers/2"]])
        self.assertEqual({j.source for j in jobs} | {j.found_by for j in jobs}, {"stapply", "bamboohr"})
        self.assertEqual(cfg["_window_start"], NOW - timedelta(days=1))

    def test_fields(self):
        lead, knime, other = run(FakeDB())[0]
        self.assertEqual((lead.remote, lead.work_mode), (True, "remote"))
        self.assertEqual((knime.location, knime.remote), ("Konstanz, Germany; Berlin, Germany", False))
        self.assertIsNone(other.remote)
        self.assertEqual(lead.published.isoformat()[:16], POSTED[:16])

    def test_known_jobs_get_no_ad_text(self):
        db = FakeDB()
        jobs, _ = run(db, _known=lambda j: j.company == "Knime")
        self.assertEqual(db.calls[1][1], [["https://x.bamboohr.com/careers/1"]])

    def test_each_snapshot_read_once_then_since_last_read(self):
        state = FakeState()
        run(FakeDB(), state)
        db = FakeDB()
        jobs, cfg = run(db, state)                       # same snapshot: nothing read
        self.assertEqual((jobs, db.calls), ([], []))
        self.assertNotIn("_window_start", cfg)
        state[stapply.DONE_KEY]["bamboohr"]["at"] = (NOW - timedelta(days=30)).isoformat()
        jobs, cfg = run(db, state, sha="new")            # next snapshot: back to the last read, max 7 days
        self.assertEqual(len(jobs), 3)
        self.assertAlmostEqual(cfg["_window_start"].timestamp(), (NOW - timedelta(days=7)).timestamp(), delta=60)
        self.assertEqual(db.calls[0][1], [cfg["_window_start"].strftime("%Y-%m-%d")])
        self.assertEqual(state[stapply.DONE_KEY]["bamboohr"]["sha"], "new")

    def test_missing_columns_become_null(self):
        db = FakeDB(COLUMNS - {"locations", "workplace_type", "is_stale", "description"})
        jobs, _ = run(db)
        sql = db.calls[0][0]
        self.assertIn("NULL AS locations", sql)
        self.assertNotIn("is_stale", sql)
        self.assertEqual(len(db.calls), 1)               # no ad text column: no second query
        self.assertFalse(any(j.has_description for j in jobs))

    def test_failed_slice_is_reported_and_retried(self):
        db = FakeDB(set())
        state = FakeState()
        jobs, cfg = run(db, state)
        self.assertEqual(jobs, [])
        self.assertEqual(cfg["_problems"][0][0], "stapply:bamboohr")
        self.assertNotIn(stapply.DONE_KEY, state)

    def test_unknown_slice(self):
        self.assertEqual(run(FakeDB(), slices=["nope"])[0], [])

    def test_place_filter_in_sql(self):
        db = FakeDB()
        run(db)
        sql = db.calls[0][0]
        for part in ("country_iso = 'DE'", "coalesce(is_remote, false)", "NOT coalesce(is_stale, false)",
                     "posted_at >= ?"):
            self.assertIn(part, sql)


class Weekly(unittest.TestCase):
    def test_slices_in_searches_table(self):
        self.assertEqual(weekly.search_labels({"stapply": {"enabled": True, "slices": ["eures"]}}),
                         {"stapply": ["eures"]})
        self.assertEqual(weekly.search_labels({"stapply": {"enabled": True}})["stapply"], stapply.DEFAULT_SLICES)
        self.assertEqual(weekly.search_labels({"stapply": {"enabled": False}}), {})
        self.assertEqual(weekly.search_labels({}), {})


class NoDuckDB(unittest.TestCase):
    def test_clear_error(self):
        with mock.patch.dict("sys.modules", {"duckdb": None}):
            with self.assertRaisesRegex(RuntimeError, "pip install duckdb"):
                stapply.DuckDB()


if __name__ == "__main__":
    unittest.main()
