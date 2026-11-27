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
    # Near misses (failed only the required words, e.g. no "Kubernetes" in the ad) with at
    # least this CV match are emailed right away instead of waiting for the weekly email.
    # 0 turns it off. At most near_misses_per_run new ones are scored per run.
    "near_miss_min_score": 75,
    "near_misses_per_run": 5,
    # Room for CV + wishes + ad + answer. Ollama's default can be as low as 2048 tokens,
    # which silently cuts the prompt (a ~1,000-word CV plus an ad is ~4,500 tokens).
    "context_tokens": 16384,
    # What the model rates (1 to 5 of CRITERIA, one request either way); yojobs computes
    # the score from the ratings, which is far more stable than asking for a number.
    "criteria": ["role", "skills"],
}
CV_NAMES = ["cv.md", "cv.txt", "cv.docx", "cv.pdf"]
CV_SUFFIXES = (".md", ".txt", ".docx", ".pdf")
PROMPT_VERSION = 3  # bump when the prompt changes, so cached scores are recomputed

# name -> (question for the model, levels from best to worst)
FIT = ["strong", "good", "partial", "weak"]
CRITERIA = {
    "role": ("Role fit: can the candidate do this job? Skills, experience and seniority "
             "against the job's requirements.", FIT),
    "skills": ("Skills fit: the technical and domain skills the job requires.", FIT),
    "seniority": ("Seniority fit: the leadership level, scope and team size the job asks for.", FIT),
    "gaps": ("Must-have gaps: how much of what the job requires does the CV not show?",
             ["none", "minor", "some", "major"]),
    "wishes": ("Wishes fit: does the job offer what the candidate wants and avoid what they "
               "don't want (see the candidate's wishes)?", ["matches", "neutral", "some conflict", "conflicts"]),
}
LEVEL_VALUE = [1.0, 0.75, 0.45, 0.15]   # fit criteria: best .. worst
WISHES_FACTOR = [1.0, 0.88, 0.62, 0.3]  # wishes multiplies: a conflict keeps the score low


def criteria(s: dict) -> List[str]:
    """The configured criteria, or the default if the setting is invalid."""
    chosen = [c for c in dict.fromkeys(s.get("criteria") or []) if c in CRITERIA]
    if not chosen or len(chosen) != len(s.get("criteria") or []):
        note(f"CV match: criteria must be 1-5 of {', '.join(CRITERIA)}; using {DEFAULTS['criteria']}")
        return list(DEFAULTS["criteria"])
    return chosen


def schema(names: List[str]) -> dict:
    props = {n: {"type": "string", "enum": CRITERIA[n][1]} for n in names}
    props.update({"strengths": {"type": "array", "items": {"type": "string"}, "maxItems": 3},
                  "gaps_list": {"type": "array", "items": {"type": "string"}, "maxItems": 3},
                  "summary": {"type": "string"}})
    return {"type": "object", "required": list(props), "properties": props}


def compute_score(ratings: dict) -> int:
    """Average of the fit criteria, multiplied by the wishes factor."""
    fit = [LEVEL_VALUE[CRITERIA[n][1].index(v)] for n, v in ratings.items() if n != "wishes"]
    score = sum(fit) / len(fit) if fit else 1.0
    if "wishes" in ratings:
        score *= WISHES_FACTOR[CRITERIA["wishes"][1].index(ratings["wishes"])]
    return round(100 * score)


PROMPT = """You compare a candidate's CV with a job ad. Rate it on these criteria:

{criteria}

Rules:
- Use only facts written in the CV. Never invent experience the CV doesn't state.
- Before calling anything missing, search the CV for it, including other wordings
  (e.g. "cloud cost optimisation" = FinOps). If the CV shows it, it is not missing.
- The candidate's wishes: what the job offers that the candidate wants (e.g. remote
  work, async culture) counts in favour. Only rate a conflict when the job clearly goes
  against a wish (e.g. on-site in a city the candidate won't move to).
- strengths: the job's main requirements the CV clearly meets (max 3, max 6 words each).
- gaps_list: only must-have requirements the CV doesn't show (max 3, max 6 words each);
  ignore nice-to-haves, tools named in passing and the company's own products. Empty is fine.
- summary: one sentence addressed to the candidate as "you".

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
    names = criteria(s)
    listing = "\n".join(f"- {n}: {CRITERIA[n][0]} One of: {', '.join(CRITERIA[n][1])}." for n in names)
    prompt = PROMPT.format(criteria=listing, cv=cv, wishes=wishes or "(none given)", title=job.title,
                           company=job.company, location=job.location, description=job.description[:12000])
    body = {"model": s["model"], "messages": [{"role": "user", "content": prompt}], "stream": False,
            "format": schema(names), "options": {"temperature": 0, "num_ctx": int(s["context_tokens"])}}
    if s.get("think"):
        body["think"] = s["think"]
    out = _post(s["ollama_url"].rstrip("/") + "/api/chat", body, float(s["timeout_seconds"]))
    content = (out.get("message") or {}).get("content") or ""
    if not content.strip():
        raise RuntimeError(f"the model returned no answer (done_reason: {out.get('done_reason', '?')}); "
                           f"if the prompt was cut off, raise context_tokens in config/matching.yaml")
    result = json.loads(content)
    ratings = {n: result[n] for n in names}
    return {"score": compute_score(ratings), "ratings": ratings, "strengths": result.get("strengths") or [],
            "gaps": result.get("gaps_list") or [], "summary": result.get("summary") or ""}


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
    key = f"{PROMPT_VERSION}|{s['model']}|{s.get('think')}|{','.join(s.get('criteria') or [])}|{cv}|{wishes}"
    return hashlib.sha256(key.encode()).hexdigest()[:16]


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


def strong_near_misses(near: List[Tuple[Job, str]], cfg: dict, root: Path, db: sqlite3.Connection,
                       skip=lambda job: False) -> List[Tuple[Job, str]]:
    """The near misses (job, reason) whose CV match reaches near_miss_min_score: good jobs
    held back only by a missing required word. Only ads with text, not skip(job) (already
    sent or already a near miss), up to near_misses_per_run; scores are cached like the
    alerts' ones. Never raises (no scores = none)."""
    s = settings(cfg)
    limit, per_run = int(s.get("near_miss_min_score") or 0), int(s.get("near_misses_per_run") or 0)
    if not s["enabled"] or limit <= 0 or per_run <= 0:
        return []
    todo = [(j, r) for j, r in near if j.description and not skip(j)][:per_run]
    try:
        score_jobs([j for j, _ in todo], {**cfg, "matching": {**s, "max_jobs_per_run": per_run}}, root, db)
    except Exception as exc:
        note(f"CV match of near misses failed: {type(exc).__name__}: {exc}")
        return []
    return [(j, r) for j, r in todo if (j.match or {}).get("score", -1) >= limit]


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


def match_one(cfg: dict, root: Path, arg: str) -> int:
    """--match <link | file | ->: score one ad against the CV and print the result.
    Works even when automatic matching is off; nothing is saved or emailed."""
    from . import adtext  # lazy: only needed here
    s = settings(cfg)
    try:
        cv_file, cv, wishes = load_cv(root, s)
    except Exception as exc:
        print(f"Can't read the CV: {exc}")
        return 1
    if not cv_file:
        print(f"No CV in {s['cv_dir']}/ (a .md, .txt, .docx or .pdf file).")
        return 1
    models = ollama_models(s)
    if models is None:
        print(f"Ollama isn't running at {s['ollama_url']} (start it: ./scripts/ollama-ctl.sh start).")
        return 1
    if s["model"] not in models and f"{s['model']}:latest" not in models:
        print(f"Model {s['model']} isn't installed (ollama pull {s['model']}).")
        return 1
    try:
        job = adtext.load(arg)
    except adtext.BlockedError as exc:
        print(f"Couldn't read the ad: {exc}.\nInstead, {adtext.SAVE_HINT}")
        return 1
    except Exception as exc:
        print(f"Couldn't read the ad: {type(exc).__name__}: {exc}")
        return 1
    words = len(job.description.split())
    print(f"Ad:      {job.title or '(no title found)'}" + (f" — {job.company}" if job.company else ""))
    if job.location:
        print(f"Where:   {job.location}")
    print(f"Text:    {words} words" + ("  (very little: the page may not have loaded the ad; "
                                       "try saving it from the browser)" if words < 80 else ""))
    if not words:
        return 1
    note(f"Asking {s['model']} (usually 15-40 s)...")
    try:
        m = ask(s, cv, wishes, job)
    except Exception as exc:
        print(f"The model couldn't score it: {type(exc).__name__}: {exc}")
        return 1
    print(f"\nCV match {m['score']}%  (" + ", ".join(f"{k}: {v}" for k, v in m["ratings"].items()) + ")")
    if m.get("strengths"):
        print("  strong: " + ", ".join(m["strengths"]))
    if m.get("gaps"):
        print("  gaps:   " + ", ".join(m["gaps"]))
    if m.get("summary"):
        print(f"  {m['summary']}")
    return 0
