import tempfile
import unittest
from datetime import date
from pathlib import Path

from yojobs import logs

YOJOBS = b"""07:03:17  [18/22] linkedin
2026-08-01 07:09 emailed 0 new of 2 matches
  remotive        ok    16 fetched
2026-08-01 07:07:17,987 - ERROR - Jobdrop:LinkedIn - 429
2026-09-10 06:59:01  Scheduled run starting (first run today)
Traceback (most recent call last):
  File "x.py", line 1
2026-11-19 07:09 emailed 1 new of 3 matches
"""
OLLAMA = b"""time=2026-08-01T12:44:51.493+01:00 level=INFO msg="server config"
llama_model_loader: - kv   0
[GIN] 2026/09/15 - 07:05:12 | 200 |  1.2s | POST "/api/chat"
slot print_timing: id  0
"""


class Dates(unittest.TestCase):
    def test_formats(self):
        self.assertEqual(logs.line_date(b"2026-11-19 07:07:18  [3/22] himalayas"), date(2026, 11, 19))
        self.assertEqual(logs.line_date(b"2026-11-19 07:07:17,987 - ERROR - x"), date(2026, 11, 19))
        self.assertEqual(logs.line_date(b"time=2026-11-17T12:44:51.493+01:00 level=INFO"), date(2026, 11, 17))
        self.assertEqual(logs.line_date(b"[GIN] 2026/11/19 - 07:05:12 | 200"), date(2026, 11, 19))
        for undated in [b"07:03:17  [18/22] linkedin", b"  remotive  ok", b"2026-13-40 x", b""]:
            self.assertIsNone(logs.line_date(undated))


class Trim(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def file(self, name, data):
        p = self.dir / name
        p.write_bytes(data)
        return p

    def test_keep_days_cuts_at_the_first_recent_dated_line(self):
        p = self.file("yojobs.log", YOJOBS)
        done = logs.trim(p, 90, 50, today=date(2026, 11, 19))            # cutoff 2026-08-21
        self.assertIn("4 lines older than 2026-08-21", done)
        self.assertTrue(p.read_bytes().startswith(b"2026-09-10 06:59:01  Scheduled run starting"))
        self.assertIn(b"Traceback", p.read_bytes())                        # undated lines follow their dated line

    def test_ollama_formats(self):
        p = self.file("ollama.log", OLLAMA)
        logs.trim(p, 90, 50, today=date(2026, 11, 19))
        self.assertTrue(p.read_bytes().startswith(b"[GIN] 2026/09/15"))

    def test_nothing_old_nothing_done(self):
        p = self.file("yojobs.log", YOJOBS)
        self.assertEqual(logs.trim(p, 365, 50, today=date(2026, 11, 19)), "")
        self.assertEqual(p.read_bytes(), YOJOBS)

    def test_keep_days_off_by_default(self):
        p = self.file("yojobs.log", YOJOBS)
        self.assertEqual(logs.trim(p, None, 50, today=date(2026, 11, 19)), "")

    def test_all_old_or_undated(self):
        p = self.file("a.log", b"2020-01-01 x\n  y\n")
        logs.trim(p, 90, 50, today=date(2026, 11, 19))
        self.assertEqual(p.read_bytes(), b"")
        q = self.file("b.log", b"no dates here\nat all\n")
        self.assertEqual(logs.trim(q, 90, 50, today=date(2026, 11, 19)), "")   # can't tell: left alone

    def test_size_limit_keeps_the_newest_half(self):
        p = self.file("big.log", b"".join(b"2026-11-19 line %06d\n" % i for i in range(100_000)))   # ~2.3 MB
        done = logs.trim(p, None, 1, today=date(2026, 11, 19))
        data = p.read_bytes()
        self.assertIn("over 1 MB", done)
        self.assertLessEqual(len(data), 500_100)
        self.assertTrue(data.startswith(b"[... older log lines trimmed ...]\n2026-11-19 line "))
        self.assertTrue(data.endswith(b"line 099999\n"))

    def test_same_file_is_rewritten_in_place(self):
        p = self.file("yojobs.log", YOJOBS)
        inode = p.stat().st_ino
        with open(p, "ab") as writer:                                      # like launchd / ollama serve
            logs.trim(p, 90, 50, today=date(2026, 11, 19))
            writer.write(b"2026-11-19 08:00:00  still writing\n")
        self.assertEqual(p.stat().st_ino, inode)
        self.assertTrue(p.read_bytes().endswith(b"still writing\n"))

    def test_trim_all_skips_missing_files(self):
        p = self.file("yojobs.log", YOJOBS)
        done = logs.trim_all({"keep_days": 90, "files": [str(p), str(self.dir / "missing.log")]},
                             today=date(2026, 11, 19))
        self.assertEqual(len(done), 1)


if __name__ == "__main__":
    unittest.main()
