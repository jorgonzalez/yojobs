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


class Rotation(unittest.TestCase):
    def test_start_moves_between_runs(self):
        s = list("abcdefgh")
        first, later = linkedin.rotated(s, now=0), linkedin.rotated(s, now=5 * 3600)
        self.assertEqual(sorted(first), s)
        self.assertNotEqual(first[0], later[0])
        self.assertEqual(linkedin.rotated([], now=0), [])


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
                mock.patch.object(linkedin, "note"), mock.patch.object(linkedin, "rotated", lambda s: s):
            jobs = linkedin._fetch(cfg, since, fake_scrape, lambda level: None, None, None, throttle)
        self.assertEqual((calls, jobs), (["A", "B"], []))
        self.assertEqual(cfg["_problems"][0][0], "throttled")
        self.assertIn("skipped the other 3", cfg["_problems"][0][1])



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

if __name__ == "__main__":
    unittest.main()
