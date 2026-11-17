"""Optional CV match score, computed by a local Ollama model (nothing leaves the Mac).

Off unless config/matching.yaml says `enabled: true`. Only jobs about to be
emailed (new matches) are scored, each once: scores are remembered in the database
per CV + wishes + model, so a job is scored again only if one of those changes.
The score only informs and sorts the email; it never hides a job.

cv/ (git-ignored):
  your CV, any name: cv.md / cv.txt / cv.docx / cv.pdf are used first; otherwise the
  newest .md / .txt / .docx / .pdf file in the folder (e.g. "CV_Name_2026.pdf")
  wishes.md                           optional: what you want and don't want

Check the setup:  python -m yojobs --cv-check
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import List, Optional, Tuple

from .models import Job
from .progress import note, say

DEFAULTS = {
    "enabled": False,
    "model": "gpt-oss:20b",
    "ollama_url": "http://localhost:11434",
    "cv_dir": "cv",
    "think": "low",            # gpt-oss reasoning effort: low is ~20 s per job on an M2 and good enough
    "timeout_seconds": 300,
    "max_jobs_per_run": 20,    # more new jobs than this are emailed without a score
    # Room for CV + wishes + ad + answer. Ollama's default can be as low as 2048 tokens,
    # which silently cuts the prompt (a ~1,000-word CV plus an ad is ~4,500 tokens).
    "context_tokens": 16384,
}
CV_NAMES = ["cv.md", "cv.txt", "cv.docx", "cv.pdf"]
CV_SUFFIXES = (".md", ".txt", ".docx", ".pdf")
PROMPT_VERSION = 2  # bump when the prompt changes, so cached scores are recomputed

SCHEMA = {"type": "object", "required": ["score", "strengths", "gaps", "summary"], "properties": {
    "score": {"type": "integer", "minimum": 0, "maximum": 100},
    "strengths": {"type": "array", "items": {"type": "string"}, "maxItems": 3},
    "gaps": {"type": "array", "items": {"type": "string"}, "maxItems": 3},
    "summary": {"type": "string"}}}

PROMPT = """You compare a candidate's CV with a job ad and rate the fit from 0 to 100.

Rules:
- Use only facts written in the CV. Never invent experience the CV doesn't state.
- Strengths: the job's main requirements that the CV clearly meets.
- Gaps: only the job's main, must-have requirements that the CV doesn't show (e.g. a
  required language, technology or kind of experience). Ignore nice-to-haves, tools
  named in passing and the company's own products. No gaps is a valid answer.
- Take the candidate's wishes into account: a job that goes against them scores low
  even if the skills match.
- Strengths and gaps: at most 3 each, short phrases (max 6 words).
- Summary: one sentence addressed to the candidate as "you".
- Score guide: 85-100 excellent fit, 70-84 good, 50-69 partial, below 50 weak.

=== CV ===
{cv}

=== CANDIDATE'S WISHES ===
{wishes}

=== JOB ===
Title: {title}
Company: {company}
Location: {location}

{description}
"""


def settings(cfg: dict) -> dict:
    return {**DEFAULTS, **(cfg.get("matching") or {})}


# --- CV ----------------------------------------------------------------------

def _extract(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in (".md", ".txt"):
        return path.read_text(errors="replace")
    if suffix == ".docx":  # macOS built-in converter
        out = subprocess.run(["textutil", "-convert", "txt", "-stdout", str(path)],
                             capture_output=True, text=True, check=True)
        return out.stdout
    if suffix == ".pdf":
        try:
            from pypdf import PdfReader  # optional: .venv/bin/pip install pypdf
        except ImportError:
            raise RuntimeError("reading a PDF CV needs pypdf: .venv/bin/pip install pypdf "
                               "(or save your CV as cv/cv.txt or cv/cv.md)")
        return "\n".join(page.extract_text() or "" for page in PdfReader(str(path)).pages)
    raise RuntimeError(f"unsupported CV format: {path.name}")


def load_cv(root: Path, s: dict) -> Tuple[Optional[Path], str, str]:
    """-> (CV file, CV text, wishes text); file is None when there's no CV."""
    folder = root / s["cv_dir"]
    cv_file = next((folder / n for n in CV_NAMES if (folder / n).exists()), None)
    if not cv_file and folder.is_dir():  # any name: the newest CV-like file
        others = [f for f in folder.iterdir() if f.is_file() and f.suffix.lower() in CV_SUFFIXES
                  and f.name.lower() != "wishes.md" and not f.name.startswith(".")]
        cv_file = max(others, key=lambda f: f.stat().st_mtime, default=None)
    if not cv_file:
        return None, "", ""
    wishes_file = folder / "wishes.md"
    wishes = wishes_file.read_text(errors="replace").strip() if wishes_file.exists() else ""
    return cv_file, _extract(cv_file).strip(), wishes


# --- Ollama ------------------------------------------------------------------

def _post(url: str, body: dict, timeout: float) -> dict:
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read())


def ollama_models(s: dict) -> Optional[List[str]]:
    """Installed model names, or None if Ollama isn't reachable."""
    try:
        with urllib.request.urlopen(s["ollama_url"].rstrip("/") + "/api/tags", timeout=5) as resp:
            return [m["name"] for m in json.loads(resp.read()).get("models", [])]
    except (urllib.error.URLError, OSError, ValueError):
        return None


def ask(s: dict, cv: str, wishes: str, job: Job) -> dict:
    prompt = PROMPT.format(cv=cv, wishes=wishes or "(none given)", title=job.title, company=job.company,
                           location=job.location, description=job.description[:12000])
    body = {"model": s["model"], "messages": [{"role": "user", "content": prompt}], "stream": False,
            "format": SCHEMA, "options": {"temperature": 0, "num_ctx": int(s["context_tokens"])}}
    if s.get("think"):
        body["think"] = s["think"]
    out = _post(s["ollama_url"].rstrip("/") + "/api/chat", body, float(s["timeout_seconds"]))
    content = (out.get("message") or {}).get("content") or ""
    if not content.strip():
        raise RuntimeError(f"the model returned no answer (done_reason: {out.get('done_reason', '?')}); "
                           f"if the prompt was cut off, raise context_tokens in config/matching.yaml")
    result = json.loads(content)
    result["score"] = max(0, min(100, int(result["score"])))
    return {k: result.get(k) for k in ("score", "strengths", "gaps", "summary")}


# --- cache -------------------------------------------------------------------

class Cache:
    def __init__(self, db: sqlite3.Connection):
        self.db = db
        db.execute("""CREATE TABLE IF NOT EXISTS cv_matches (
                          url TEXT NOT NULL, fingerprint TEXT NOT NULL, result TEXT NOT NULL,
                          created TEXT NOT NULL, PRIMARY KEY (url, fingerprint))""")
        db.commit()

    def get(self, url: str, fp: str) -> Optional[dict]:
        row = self.db.execute("SELECT result FROM cv_matches WHERE url = ? AND fingerprint = ?", (url, fp)).fetchone()
        return json.loads(row[0]) if row else None

    def put(self, url: str, fp: str, result: dict) -> None:
        self.db.execute("INSERT OR REPLACE INTO cv_matches VALUES (?, ?, ?, datetime('now'))",
                        (url, fp, json.dumps(result)))
        self.db.commit()


def fingerprint(cv: str, wishes: str, s: dict) -> str:
    return hashlib.sha256(f"{PROMPT_VERSION}|{s['model']}|{s.get('think')}|{cv}|{wishes}".encode()).hexdigest()[:16]


# --- main entry --------------------------------------------------------------

def score_jobs(jobs: List[Job], cfg: dict, root: Path, db: sqlite3.Connection) -> None:
    """Set job.match = {score, strengths, gaps, summary} where possible. Never raises:
    any problem only means no scores this run."""
    s = settings(cfg)
    if not s["enabled"] or not jobs:
        return
    try:
        cv_file, cv, wishes = load_cv(root, s)
    except Exception as exc:
        note(f"CV match: can't read the CV ({exc}); no scores this run")
        return
    if not cv_file:
        note(f"CV match is enabled but there's no CV (.md/.txt/.docx/.pdf) in {s['cv_dir']}/; no scores")
        return
    models = ollama_models(s)
    if models is None:
        note(f"CV match: Ollama isn't running at {s['ollama_url']}; no scores this run")
        return
    if s["model"] not in models and f"{s['model']}:latest" not in models:
        note(f"CV match: model {s['model']} isn't installed (ollama pull {s['model']}); no scores")
        return

    cache, fp = Cache(db), fingerprint(cv, wishes, s)
    todo = [j for j in jobs if j.description][: int(s["max_jobs_per_run"])]
    for n, job in enumerate(todo, 1):
        cached = cache.get(job.url, fp)
        if cached:
            job.match = cached
            continue
        say(f"CV match {n}/{len(todo)}: {job.title[:60]}")
        t0 = time.time()
        try:
            job.match = ask(s, cv, wishes, job)
        except Exception as exc:  # one failure must not stop the run
            note(f"CV match failed for {job.title[:50]}: {type(exc).__name__}: {exc}")
            continue
        cache.put(job.url, fp, job.match)
        say(f"CV match {n}/{len(todo)}: {job.match['score']}% ({time.time() - t0:.0f}s)")


def by_score(jobs: List[Job]) -> List[Job]:
    """Scored jobs first, best first; unscored keep their order after them."""
    return sorted(jobs, key=lambda j: -(j.match or {}).get("score", -1))


def check(cfg: dict, root: Path) -> int:
    """--cv-check: show what matching would use, without scoring anything."""
    s = settings(cfg)
    print(f"matching enabled: {s['enabled']}  (config/matching.yaml)")
    try:
        cv_file, cv, wishes = load_cv(root, s)
    except Exception as exc:
        print(f"CV: can't read it: {exc}")
        return 1
    print(f"CV: {cv_file.relative_to(root) if cv_file else 'none found in ' + s['cv_dir'] + '/'}"
          + (f" ({len(cv.split())} words)" if cv_file else ""))
    print(f"wishes: {'cv/wishes.md (' + str(len(wishes.split())) + ' words)' if wishes else 'none (optional)'}")
    models = ollama_models(s)
    if models is None:
        print(f"Ollama: not reachable at {s['ollama_url']} (start the Ollama app)")
    else:
        ok = s["model"] in models or f"{s['model']}:latest" in models
        print(f"Ollama: running; model {s['model']} {'installed' if ok else 'NOT installed (ollama pull ' + s['model'] + ')'}")
    return 0
