import threading
import time
import unittest
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from unittest import mock

import pandas as pd

from yojobs.sources import linkedin


class Handler(BaseHTTPRequestHandler):
    hits = {"/429": 0, "/503": 0}

    def do_GET(self):
        Handler.hits[self.path] = Handler.hits.get(self.path, 0) + 1
        code = 429 if self.path == "/429" else 503 if self.path == "/503" else 200
        self.send_response(code)
        if code == 429:
            self.send_header("Retry-After", "300")   # what made searches stall for minutes
        self.end_headers()
        self.wfile.write(b"x")

    def log_message(self, *a):
        pass


class GentleSession(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = HTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.base = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()

    def session(self):
        from jobdrop.util import create_session
        self.throttle = linkedin.Throttle()
        return linkedin.gentle_session_factory(create_session, self.throttle)(
            is_tls=False, has_retry=True, delay=5, clear_cookies=True)

    def test_429_fails_fast_and_is_recorded(self):
        Handler.hits["/429"] = 0
        t0 = time.monotonic()
        r = self.session().get(self.base + "/429", timeout=5)
        self.assertEqual(r.status_code, 429)
        self.assertLess(time.monotonic() - t0, 2)      # no Retry-After wait, no retries
        self.assertEqual(Handler.hits["/429"], 1)
        self.assertTrue(self.throttle.hit)

    def test_server_errors_are_still_retried_briefly(self):
        Handler.hits["/503"] = 0
        with mock.patch("time.sleep"):                  # skip the 2/4 s backoff in tests
            self.session().get(self.base + "/503", timeout=5)
        self.assertEqual(Handler.hits["/503"], 3)       # 1 + 2 retries
        self.assertFalse(self.throttle.hit)


class State:
    def __init__(self, **values):
        self.values = values

    def get(self, name, default=None):
        return self.values.get(name, default)

    def set(self, name, value):
        self.values[name] = value


class Rotation(unittest.TestCase):
    searches = [{"term": t, "location": "Berlin"} for t in "ABCDE"]

    def run_fetch(self, state, throttle_at=None):
        throttle, calls = linkedin.Throttle(), []

        def fake_scrape(**kw):
            calls.append(kw["search_term"])
            if len(calls) == throttle_at:
                throttle.hit = True
            return pd.DataFrame([])
        cfg = {"searches": self.searches, "_problems": [], "_state": state}
        with mock.patch.object(linkedin.time, "sleep"), mock.patch.object(linkedin, "say"), \
                mock.patch.object(linkedin, "note"):
            linkedin._fetch(cfg, datetime.now(timezone.utc) - timedelta(days=1),
                            fake_scrape, lambda level: None, None, None, throttle)
        return calls

    def test_starts_at_saved_search(self):
        s = self.searches
        self.assertEqual([x["term"] for x in linkedin.rotated(s, linkedin.search_key(s[2]))], list("CDEAB"))
        self.assertEqual(linkedin.rotated(s, None), s)
        self.assertEqual(linkedin.rotated(s, "gone|Berlin|"), s)   # search removed from the config
        self.assertEqual(linkedin.rotated([], None), [])

    def test_key_tells_places_apart(self):
        self.assertNotEqual(linkedin.search_key({"term": "A", "location": "Germany"}),
                            linkedin.search_key({"term": "A", "location": "Germany", "remote": True}))

    def test_throttled_run_continues_with_the_interrupted_search(self):
        state = State()
        self.assertEqual(self.run_fetch(state, throttle_at=2), ["A", "B"])
        self.assertEqual(self.run_fetch(state, throttle_at=1), ["B"])
        self.assertEqual(self.run_fetch(state), list("BCDEA"))

    def test_complete_run_moves_the_start_on(self):
        state = State()
        self.assertEqual(self.run_fetch(state), list("ABCDE"))
        self.assertEqual(self.run_fetch(state), list("BCDEA"))

    def test_throttled_in_last_search(self):
        state = State(**{linkedin.STATE_KEY: linkedin.search_key(self.searches[3])})
        self.assertEqual(self.run_fetch(state, throttle_at=5), list("DEABC"))
        self.assertEqual(state.get(linkedin.STATE_KEY), linkedin.search_key(self.searches[2]))

    def test_without_state(self):
        self.assertEqual(self.run_fetch(None), list("ABCDE"))


class SearchesPerRun(unittest.TestCase):
    searches = [{"term": t, "location": "Berlin"} for t in "ABCDEF"]

    def run_fetch(self, state, throttle_at=None, hours=None):
        throttle, calls = linkedin.Throttle(), []

        def fake_scrape(**kw):
            calls.append(kw["search_term"])
            if hours is not None:
                hours.append(kw["hours_old"])
            if len(calls) == throttle_at:
                throttle.hit = True
            return pd.DataFrame([])
        cfg = {"searches": self.searches, "searches_per_run": 2, "_problems": [], "_state": state}
        with mock.patch.object(linkedin.time, "sleep"), mock.patch.object(linkedin, "say"), \
                mock.patch.object(linkedin, "note"):
            linkedin._fetch(cfg, datetime.now(timezone.utc) - timedelta(days=3),
                            fake_scrape, lambda level: None, None, None, throttle)
        return calls, cfg

    def test_two_a_run_in_turn(self):
        state = State()
        self.assertEqual([self.run_fetch(state)[0] for _ in range(4)],
                         [["A", "B"], ["C", "D"], ["E", "F"], ["A", "B"]])

    def test_throttled_pair_is_repeated_from_the_interrupted_search(self):
        state = State()
        self.assertEqual(self.run_fetch(state, throttle_at=2)[0], ["A", "B"])
        self.assertEqual(self.run_fetch(state)[0], ["B", "C"])
        self.assertEqual(self.run_fetch(state)[0], ["D", "E"])

    def test_each_search_looks_back_to_its_last_complete_run(self):
        state, hours = State(), []
        self.run_fetch(state, hours=hours)                       # A, B never done: general 3 days
        self.assertEqual(hours, [73, 73])
        self.assertIn(linkedin.DONE_KEY + linkedin.search_key(self.searches[0]), state.values)
        four_days = (datetime.now(timezone.utc) - timedelta(days=4)).isoformat()
        long_ago = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
        state.values.update({linkedin.DONE_KEY + linkedin.search_key(self.searches[2]): four_days,
                             linkedin.DONE_KEY + linkedin.search_key(self.searches[3]): long_ago})
        hours.clear()
        _, cfg = self.run_fetch(state, hours=hours)              # C: 4 days + margin; D: capped at 7 days
        self.assertEqual(hours, [99, 169])
        self.assertLess(cfg["_window_start"], datetime.now(timezone.utc) - timedelta(days=6))

    def test_throttled_search_is_not_marked_done(self):
        state = State()
        self.run_fetch(state, throttle_at=2)
        self.assertIn(linkedin.DONE_KEY + linkedin.search_key(self.searches[0]), state.values)
        self.assertNotIn(linkedin.DONE_KEY + linkedin.search_key(self.searches[1]), state.values)

    def test_next_start(self):
        s = self.searches
        self.assertEqual(linkedin.next_start(s, 2, False), linkedin.search_key(s[2]))
        self.assertEqual(linkedin.next_start(s, 6, False), linkedin.search_key(s[1]))   # all done: move on by one
        self.assertEqual(linkedin.next_start(s, 2, True), linkedin.search_key(s[1]))


class StopsWhenThrottled(unittest.TestCase):
    def test_remaining_searches_are_skipped_and_reported(self):
        throttle, calls = linkedin.Throttle(), []

        def fake_scrape(**kw):
            calls.append(kw["search_term"])
            if len(calls) == 2:
                throttle.hit = True                    # LinkedIn says 429 during the 2nd search
            return pd.DataFrame([])
        cfg = {"searches": [{"term": t, "location": "Berlin"} for t in "ABCDE"], "_problems": []}
        since = datetime.now(timezone.utc) - timedelta(days=1)
        with mock.patch.object(linkedin.time, "sleep"), mock.patch.object(linkedin, "say"), \
                mock.patch.object(linkedin, "note"), mock.patch.object(linkedin, "rotated", lambda s, start=None: s):
            jobs = linkedin._fetch(cfg, since, fake_scrape, lambda level: None, None, None, throttle)
        self.assertEqual((calls, jobs), (["A", "B"], []))
        self.assertEqual(cfg["_problems"][0][0], "throttled")
        self.assertIn("skipped the other 3", cfg["_problems"][0][1])



class Pauses(unittest.TestCase):
    def test_range_from_config(self):
        self.assertEqual(linkedin.pause_range(None, (20, 40)), (20, 40))
        self.assertEqual(linkedin.pause_range([30, 60], (20, 40)), (30.0, 60.0))
        self.assertEqual(linkedin.pause_range([60, 30], (20, 40)), (30.0, 60.0))
        self.assertEqual(linkedin.pause_range(10, (20, 40)), (10.0, 10.0))
        self.assertEqual(linkedin.pause_range("soon", (20, 40)), (20, 40))

    def test_searches_are_spread_out(self):
        throttle = linkedin.Throttle()
        cfg = {"searches": [{"term": t, "location": "Berlin"} for t in "ABC"], "_problems": []}
        since = datetime.now(timezone.utc) - timedelta(days=1)
        with mock.patch.object(linkedin.time, "sleep") as sleep, mock.patch.object(linkedin, "say"), \
                mock.patch.object(linkedin, "note"), mock.patch.object(linkedin, "rotated", lambda s, start=None: s):
            linkedin._fetch(cfg, since, lambda **kw: pd.DataFrame([]), lambda level: None, None, None, throttle)
        waits = [c.args[0] for c in sleep.call_args_list]
        self.assertEqual(len(waits), 2)                          # between the 3 searches, not before the first
        self.assertTrue(all(20 <= w <= 40 for w in waits), waits)

        cfg = dict(cfg, search_pause=[1, 2])
        with mock.patch.object(linkedin.time, "sleep") as sleep, mock.patch.object(linkedin, "say"), \
                mock.patch.object(linkedin, "note"), mock.patch.object(linkedin, "rotated", lambda s, start=None: s):
            linkedin._fetch(cfg, since, lambda **kw: pd.DataFrame([]), lambda level: None, None, None, throttle)
        self.assertTrue(all(1 <= c.args[0] <= 2 for c in sleep.call_args_list))


PAGE = """<html><body><h1 class="top-card-layout__title topcard__title">Engineering Manager - Infrastructure</h1>
<span class="topcard__flavor topcard__flavor--bullet">Cracow Metropolitan Area</span>
<div class="description__text"><div class="show-more-less-html__markup"><p>Fully remote and global, we are
growing. You will guide a remote team of four infrastructure engineers running Kubernetes.</p></div></div></body></html>"""


class JobPage(unittest.TestCase):
    def test_description_and_location(self):
        desc, loc = linkedin.parse_job_page(PAGE)
        self.assertEqual(loc, "Cracow Metropolitan Area")
        self.assertIn("Fully remote and global", desc)

    def test_failures_give_empty(self):
        class Bad:
            def get(self, *a, **k):
                raise TimeoutError()
        self.assertEqual(linkedin.job_page(Bad(), "1"), ("", ""))


class Lean(unittest.TestCase):
    def run_fetch(self, last_full_run, known_urls=()):
        seen = {"hours_old": [], "pages": []}
        rows = pd.DataFrame([{"job_url": f"https://www.linkedin.com/jobs/view/{i}", "title": "Engineering Manager Platform",
                              "company": "Acme", "location": "Berlin", "date_posted": None, "id": f"li-{i}"} for i in (1, 2, 3)])

        def fake_scrape(**kw):
            seen["hours_old"].append(kw["hours_old"])
            return rows

        class FakeLinkedIn:
            session = None
            scraper_input = None
        cfg = {"searches": [{"term": "EM Platform", "location": "Berlin"}],
               "_title_ok": lambda j: True, "_last_full_run": last_full_run,
               "_known": lambda j: j.url in known_urls}
        since = datetime.now(timezone.utc) - timedelta(days=3)
        with mock.patch.object(linkedin.time, "sleep"), mock.patch.object(linkedin, "say"), \
                mock.patch.object(linkedin, "note"), \
                mock.patch.object(linkedin, "job_page", lambda session, jid: seen["pages"].append(jid) or ("text", "")):
            linkedin._fetch(cfg, since, fake_scrape, lambda level: None, FakeLinkedIn, mock.MagicMock(), linkedin.Throttle())
        return seen

    def test_lookback_since_last_full_run(self):
        yesterday = datetime.now(timezone.utc) - timedelta(hours=24)
        self.assertEqual(self.run_fetch(yesterday)["hours_old"], [27])       # 24 h + 2 h margin + 1
        self.assertEqual(self.run_fetch(None)["hours_old"], [73])            # never ran: general 3 days
        long_ago = datetime.now(timezone.utc) - timedelta(days=10)
        self.assertEqual(self.run_fetch(long_ago)["hours_old"], [73])        # missed days: capped at 3 days

    def test_known_jobs_are_not_reopened(self):
        pages = self.run_fetch(None, known_urls={"https://www.linkedin.com/jobs/view/2"})["pages"]
        self.assertEqual(pages, ["1", "3"])

    def test_found_by_records_the_search(self):
        rows = pd.DataFrame([{"job_url": "https://www.linkedin.com/jobs/view/9", "title": "EM Platform", "company": "A",
                              "location": "Berlin", "date_posted": None, "id": "li-9"}])
        cfg = {"searches": [{"term": "EM Platform", "location": "Germany", "remote": True}], "_title_ok": lambda j: False}
        with mock.patch.object(linkedin.time, "sleep"), mock.patch.object(linkedin, "say"), mock.patch.object(linkedin, "note"):
            jobs = linkedin._fetch(cfg, datetime.now(timezone.utc) - timedelta(days=1), lambda **kw: rows,
                                   lambda level: None, None, None, linkedin.Throttle())
        self.assertEqual(jobs[0].found_by, "EM Platform · Germany (remote)")

if __name__ == "__main__":
    unittest.main()
