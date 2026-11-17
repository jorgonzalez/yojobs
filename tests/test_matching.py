import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from yojobs import matching
from yojobs.mailer import match_line, render
from yojobs.models import Job

ROOT_CFG = {"matching": {"enabled": True}}
ANSWER = {"score": 82, "strengths": ["Kubernetes leadership"], "gaps": ["Go"], "summary": "You fit well."}


def job(title="Head of Platform", description="We run Kubernetes.", url=None):
    return Job(source="x", title=title, company="C", url=url or f"https://x/{title}", location="Berlin",
               description=description)


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.db = sqlite3.connect(":memory:")

    def tearDown(self):
        self.db.close()
        self.tmp.cleanup()

    def cv(self, text="# Me\nPlatform lead, Kubernetes.", wishes=None):
        (self.root / "cv").mkdir(exist_ok=True)
        (self.root / "cv" / "cv.md").write_text(text)
        if wishes:
            (self.root / "cv" / "wishes.md").write_text(wishes)


class Scoring(Base):
    def run_scoring(self, jobs, models=("gpt-oss:20b",), answer=ANSWER):
        calls = []

        def fake_post(url, body, timeout):
            calls.append(body)
            return {"message": {"content": json.dumps(answer)}}
        with mock.patch.object(matching, "ollama_models", return_value=list(models) if models is not None else None), \
                mock.patch.object(matching, "_post", fake_post), mock.patch.object(matching, "note") as note:
            matching.score_jobs(jobs, ROOT_CFG, self.root, self.db)
        return calls, note

    def test_off_by_default(self):
        j = job()
        matching.score_jobs([j], {}, self.root, self.db)
        self.assertIsNone(j.match)

    def test_scores_and_caches(self):
        self.cv(wishes="Leadership roles only")
        j = job()
        calls, _ = self.run_scoring([j])
        self.assertEqual(j.match["score"], 82)
        self.assertIn("Leadership roles only", calls[0]["messages"][0]["content"])
        self.assertEqual(calls[0]["format"], matching.SCHEMA)
        again = job()
        calls, _ = self.run_scoring([again])
        self.assertEqual((len(calls), again.match["score"]), (0, 82))   # cached: no second call

    def test_cv_change_rescores(self):
        self.cv()
        self.run_scoring([job()])
        self.cv(text="# Me\nNow a different CV.")
        calls, _ = self.run_scoring([job()])
        self.assertEqual(len(calls), 1)

    def test_no_ad_text_no_score(self):
        self.cv()
        j = job(description="")
        calls, _ = self.run_scoring([j])
        self.assertEqual((len(calls), j.match), (0, None))

    def test_problems_only_mean_no_scores(self):
        j = job()
        calls, note = self.run_scoring([j])                      # no CV
        self.assertIsNone(j.match)
        self.assertIn("no CV", note.call_args[0][0])
        self.cv()
        calls, note = self.run_scoring([j], models=None)         # Ollama not running
        self.assertIsNone(j.match)
        self.assertIn("isn't running", note.call_args[0][0])
        calls, note = self.run_scoring([j], models=["llama3:8b"])  # model missing
        self.assertIn("isn't installed", note.call_args[0][0])

    def test_score_is_clamped(self):
        self.cv()
        j = job()
        self.run_scoring([j], answer=dict(ANSWER, score=140))
        self.assertEqual(j.match["score"], 100)


class Output(unittest.TestCase):
    def test_sorting_and_lines(self):
        a, b, c = job("A"), job("B"), job("C")
        a.match, b.match = dict(ANSWER, score=60), dict(ANSWER, score=90)
        self.assertEqual([j.title for j in matching.by_score([a, c, b])], ["B", "A", "C"])
        self.assertEqual(match_line(b.match), "CV match 90% · strong: Kubernetes leadership · gaps: Go")
        text, html = render([b, c], [])
        self.assertIn("CV match 90%", text)
        self.assertIn("You fit well.", text)
        self.assertIn("CV match 90%", html)


class CvFiles(Base):
    def test_first_supported_file_wins(self):
        (self.root / "cv").mkdir()
        (self.root / "cv" / "cv.txt").write_text("text cv")
        (self.root / "cv" / "cv.md").write_text("markdown cv")
        f, text, wishes = matching.load_cv(self.root, matching.settings(ROOT_CFG))
        self.assertEqual((f.name, text, wishes), ("cv.md", "markdown cv", ""))


    def test_any_file_name(self):
        import os
        (self.root / "cv").mkdir()
        (self.root / "cv" / "wishes.md").write_text("wishes")
        (self.root / "cv" / ".DS_Store").write_text("junk")
        old, new = self.root / "cv" / "Old_CV.txt", self.root / "cv" / "CV_Name_2026.txt"
        old.write_text("old"); new.write_text("new")
        os.utime(old, (1, 1))
        f, text, wishes = matching.load_cv(self.root, matching.settings(ROOT_CFG))
        self.assertEqual((f.name, text, wishes), ("CV_Name_2026.txt", "new", "wishes"))

if __name__ == "__main__":
    unittest.main()
