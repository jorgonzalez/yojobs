# yojobs

A local, scheduled job alert: it searches many job sites and company career pages,
filters the jobs by your keywords and location rules, and emails you each new match
once, with no cloud service involved.

- **Sources:** about 15 job boards (remote boards, European/startup boards, Hacker News,
  LinkedIn, Indeed) plus company career pages on Greenhouse, Lever and Ashby.
- **Filters:** AND / OR / NOT keywords, required words anywhere in the ad (e.g.
  "Kubernetes"), on-site cities and allowed remote regions.
- **Email:** one message per run with only the jobs you haven't been sent before,
  readable on any device.
- **Scheduling:** macOS launchd, a few times a day, only while the laptop is on.

Runs on macOS (the Keychain and launchd are macOS-specific). Python 3.10+.

## Setup

```sh
python3.12 -m venv .venv               # Python 3.10+ (e.g. brew install python@3.12)
.venv/bin/pip install -r requirements.txt
cp -R config.example config            # then edit config/settings.yaml (email) and config/profile.yaml
```

### Configuration (`config/`)

| file | what's in it |
|---|---|
| `settings.yaml` | how yojobs runs: look-back, schedule, email, database, weekly summary, health |
| `profile.yaml` | what you're looking for: title words, required and excluded words, places, languages |
| `blocklist.yaml` | companies you never want to see |
| `sources.yaml` | which portals are on/off, and their options |
| `searches.yaml` | LinkedIn/Indeed search terms × places |
| `companies.yaml` | company career pages, by hiring system |
| `matching.yaml` | optional CV match with a local AI model (off by default) |

Every `.yaml` file in `config/` is read; the same setting in two files is an error.
`config/` is git-ignored: your email address and searches never go into the repo.
`config.example/` documents every option and has more example profiles.

Older setups with a single `config.yaml` still work (used when there's no `config/`).
To convert one: `.venv/bin/python -m yojobs --split-config` writes `config/` and checks
that it loads to exactly the same configuration before keeping it.

### Email (Gmail)

Enable 2-step verification on your Google account, create an App Password at
https://myaccount.google.com/apppasswords, then store it in the macOS Keychain:

```sh
security add-generic-password -U -s yojobs-smtp -a you@gmail.com -w
```

Paste the App Password when asked (spaces are ignored). Use the same address as
`email: username:` in `config/settings.yaml`. The password lives only in the Keychain.

## Run

```sh
.venv/bin/python -m yojobs                      # preview: all enabled sources, nothing saved
.venv/bin/python -m yojobs --source jobicy      # one source (repeatable)
.venv/bin/python -m yojobs --days 7             # override max_age_days
.venv/bin/python -m yojobs --all                # no keyword filter (debug)
.venv/bin/python -m yojobs --email              # email jobs not sent before, then remember them
.venv/bin/python -m yojobs --email --days 30    # catch-up email for the last month
.venv/bin/python -m yojobs --weekly             # preview the weekly summary (add --email to send it)
```

Preview mode prints matches sorted by score, then date, and marks jobs not emailed yet
with `*`.

Progress goes to stderr; results go to stdout:
- default: one status line, redrawn in place, showing the portal being checked and
  what it's doing (`[3/15] himalayas · search: Kubernetes`). Only errors and the
  summary get lines of their own.
- `-v` / `--verbose`: every step on its own timestamped line (every search, page and
  company board).
- scheduled runs are always verbose, so `~/Library/Logs/yojobs.log` has the full detail.

The first run (empty `seen.sqlite`) looks back `first_run_days` (30) instead of
`max_age_days` (3).

Only one run at a time: manual and automatic runs share a lock. A second run started
while one is going stops immediately with a message.

## Automatic runs (launchd)

```sh
./scripts/install-launchd.sh      # install / reinstall
./scripts/uninstall-launchd.sh    # remove
```

launchd starts `yojobs --scheduled` every 10 minutes and at login (its timer doesn't fire
while the Mac sleeps, so frequent checks mean a due run starts soon after waking; a check
that finds nothing due exits immediately and is logged at most once an hour).
yojobs only runs (with `--email`) when due per `schedule:` in `config/settings.yaml`:
between `earliest` and `latest`, at most `max_runs_per_day`, at least
`min_gap_hours` apart. Missed runs are not caught up and each day starts fresh.
Each run looks back to the previous run, so a weekend off loses nothing.

Safety:
- a lock prevents overlapping runs (an automatic run skips if another run is going)
- a run where every source fails (e.g. no Wi-Fi yet after wake) or the email fails
  is not counted and is retried on the next tick
- the log is trimmed above 2 MB

### Is it running?

| What you want to know | Command |
|---|---|
| Everything at once: run in progress, today's runs, next run, agent | `./scripts/status.sh` |
| Follow the log | `tail -f ~/Library/Logs/yojobs.log` |
| Is the launchd job loaded, did it exit cleanly? | `launchctl print gui/$(id -u)/local.yojobs \| grep -E "state\|runs\|last exit"` |
| Is a run going right now? | `pgrep -fl yojobs` |
| Would it run now, and why (not)? | `.venv/bin/python -m yojobs --check-schedule` |
| When did successful runs happen? | `cat schedule_state.json` |

`state = not running` is normal between ticks. If the log shows
"Operation not permitted", macOS is blocking background access to the folder (e.g.
`~/Documents`): grant Python access in System Settings → Privacy & Security, or
move the repo elsewhere and reinstall.

## Search profiles (`config/profile.yaml`)

A job is reported if it passes **any** profile. Checks, in order:

| key | meaning |
|---|---|
| `exclude_titles` | drop the job if any of these appear (searched in `exclude_in`, default: `match_in`); a list, or named groups of lists |
| `ad_must_mention` | every entry must appear in the ad (searched in `ad_must_mention_in`); `"a\|b"` = either word |
| `where: onsite_cities` | on-site / hybrid jobs are kept only in these cities (any work mode is fine there) |
| `where: remote_regions` | remote jobs must be open to one of these (e.g. Germany, Europe, Worldwide) or say plain "Remote"; empty = anywhere |
| `title_must_have` | named word lists; the `match_in` text needs one word from **each** group (AND between groups, OR inside) |
| `title_any` | extra OR words; each distinct match adds +1 to the score |
| `min_score` | at least this many distinct matches (groups + `title_any`) |
| `match_in` | fields to match: `title`, `description`, `tags`, `company`, `location` |
| `skip_ad_languages` | drop ads written in these languages, e.g. `[de]` (bilingual ads are kept) |
| `skip_if_requires` | drop ads requiring fluency, e.g. `[German]` ("fluent German", "Deutsch C1"; not "German is a plus") |

Matching is case-insensitive and whole-word; a space also matches a hyphen.
The older key names (`groups`, `all_of`, `none_of`, `any_of`, `all_of_in`, and
`onsite_cities` / `remote_regions` without `where:`) still work.

To never hear from some companies (already applied, not interested), list them under
`blocked_companies:` in `config/blocklist.yaml`. Case, spaces and legal suffixes are
ignored, so `GetYourGuide` also blocks "Get Your Guide GmbH". Blocked jobs are never
emailed and never listed as near misses.

Sources without job descriptions (marked below) can't check `ad_must_mention`: their jobs are
kept and marked "<word> not verified" in the email.

On-site / hybrid jobs get a work-mode hint next to the location, e.g.
`Berlin (hybrid · 2-3 office days/week)`. It comes from the job board when it states
the mode (Greenhouse, Lever, Ashby, StartupMap), otherwise from the ad text in English
or German ("3 days a week in the office", "2 Tage pro Woche im Büro"). When the ad
gives a number of office days, that number decides: under 5 is hybrid, 5 is on-site.

For remote jobs the location means where you may live, so "Remote · Cork, Ireland"
or "Remote, USA only" are dropped unless the region is allowed.

See `config.example/profile.yaml` for complete examples: a platform/infrastructure leadership
profile (active), a remote Python backend developer, data engineering in Munich, and
frontend roles at specific companies.

## Weekly summary, near misses and source health

Real runs (`--email` and scheduled runs) keep a small history in `seen.sqlite`:

- **Weekly summary** (`weekly:` in `config/settings.yaml`): once a week, with the first scheduled
  run on or after `day`, an extra email with runs, jobs checked and emailed, and a
  status table of every source. It's also how you know yojobs is still running.
- **Near misses** (in the weekly email): jobs that passed every rule except the
  required words (`ad_must_mention`), e.g. a platform leadership job whose ad never says
  Kubernetes. Each is listed once; jobs already emailed as matches are left out.
  With CV matching on, up to `near_misses_scored` (15) of them get a CV match score
  and are listed best first.
- **Board discovery** (in the weekly email): companies from your recent matches and near
  misses are checked once for a public job board on the six hiring systems; found boards
  are suggested with the line to add to `config/companies.yaml` (`discover_boards`, 0 = off).
- **Searches** (in the weekly email): matches and near misses per LinkedIn / Indeed /
  StepStone search over the last 7 days, including searches that found nothing, to see
  which searches earn their place.
- **Source health** (`health:`): a source that errors or returns 0 jobs for
  `failed_runs` runs in a row (usually because the site changed) triggers one
  warning email, sent even when there are no new jobs. Runs where every source
  fails (no internet) don't count.
- **Company boards** are checked one by one: a board that fails `failed_runs` runs
  in a row (e.g. 404 because the company moved to another hiring system) triggers
  one warning, and every board that failed during the week is listed in the weekly
  email.

## CV match (optional)

yojobs can rate each new job against your CV with a local AI model through
[Ollama](https://ollama.com), so nothing leaves your Mac. It's off by default.

1. Install Ollama and a model: `ollama pull gpt-oss:20b` (13 GB; ~16 GB RAM needed)
2. Put your CV in `cv/` (git-ignored) as a `.md`, `.txt`, `.docx` or `.pdf` file (any name)
   (PDF needs `.venv/bin/pip install pypdf`). Optionally add `cv/wishes.md`: what you
   want and don't want; the score takes it into account.
3. Set `enabled: true` in `config/matching.yaml`, then check the setup:
   `.venv/bin/python -m yojobs --cv-check`

The model doesn't invent a number: it rates the criteria in `criteria:` (1 to 5 of
`role`, `skills`, `seniority`, `gaps`, `wishes`; default `[role, skills]`) on fixed
scales, and yojobs computes the score (fit criteria averaged, `wishes` multiplies, so a
job that conflicts with your wishes stays low). `cv/wishes.md` is only used when
`wishes` is in the list. This gives the same result run after run. To try other
criteria for one run: `--match <ad> --criteria skills,seniority,gaps,wishes`.

Each new job then gets a line like `CV match 83% · role: good · skills: strong · strong: … · gaps: …`
plus a one-line summary, and the email lists the best matches first. The score never hides a job. Only
jobs about to be emailed are scored (~15–20 s each on an M2), each one once; jobs
without ad text get no score. If Ollama isn't running, the email just has no scores.

### Scoring one job ad: `--match`

```sh
.venv/bin/python -m yojobs --match https://jobs.ashbyhq.com/company/<id>   # a link
.venv/bin/python -m yojobs --match ~/Downloads/job.pdf                     # .txt .md .pdf .docx .html
pbpaste | .venv/bin/python -m yojobs --match -                             # copied text
```

Prints the ad's title, company, place and how much text was found, then the CV match
(score, strengths, gaps, summary). Nothing is saved or emailed, and it works even when
automatic matching is off (it needs the CV and Ollama). Links to Greenhouse, Lever,
Ashby, Personio and Recruitee use their official APIs; other pages are read from their
embedded job data or visible text. If a site blocks it (e.g. StepStone job pages),
save the page from the browser (File → Save As… or Print → Save as PDF) and pass the file.

### Starting and stopping Ollama

Ollama doesn't have to run all the time. From your yojobs folder:

```sh
./scripts/install-ollama-prompt.sh   # after every login: "Start Ollama for the yojobs CV match?"
./scripts/make-ollama-app.sh         # an "Ollama" icon on the Desktop: double-click to start/stop
./scripts/ollama-ctl.sh status       # or start / stop, from the terminal
```

The login question closes by itself after 2 minutes and isn't shown if Ollama is
already running; remove it with `./scripts/uninstall-ollama-prompt.sh`. The Desktop
app calls the scripts in the folder it was created from, so create it from the
folder yojobs runs in (re-run the script if you move the repo). You can drag it to
the Dock. Ollama's own log: `~/Library/Logs/ollama.log`.

## Duplicates

A job is never emailed twice: its URL is remembered forever, and its normalized
company + title for `dedupe_days` (default 60), which catches reposts and the same
job on another portal. Retitled copies count too: same company and titles sharing
more than 65% of their words (brackets ignored). Normalization drops legal suffixes (GmbH, Inc, B.V....),
gender tags like (m/w/d), location tails like "- Remote, Germany", and expands
Sr/Jr/Mgr.

## Sources

| name | type | notes |
|---|---|---|
| remotive | JSON API | max ~4 requests/day; public feed is 24h delayed and small |
| remoteok | JSON API | latest ~100, mostly US-focused; terms: credit Remote OK + link to the job |
| himalayas | JSON API | keyword search (one query per `ad_must_mention` word); rate-limited, ~2 min |
| jobicy | JSON API | latest 100; optional `geo` |
| weworkremotely | RSS | optional category feed `url` |
| workingnomads | JSON | latest ~35 |
| euremotejobs | homepage HTML | feed/API disabled by owner; latest ~60 jobs; job page opened only for matches |
| euroremotejobs | WP Job Manager feed | euroremotejobs.com (not euremotejobs): newest 100 jobs per run |
| jobspresso | WP Job Manager feed | only the newest 10 per run (robots.txt disallows feed URLs with `?`) |
| hackernews | HN Search API | monthly "Who is hiring?" threads (latest 2); first line `Company \| Role \| Location \| REMOTE (EU)` parsed |
| landingjobs | JSON API | EU tech, many on-site/hybrid |
| 4dayweek | RSS | titles only, no descriptions |
| startupmap | JSON | ~16k EU startup jobs in one request; no descriptions |
| arbeitnow | JSON API | jobs in Germany (many Berlin, ~1/3 in German); 300 per page, ~20 s for 30 days |
| berlinstartupjobs | RSS | teaser only; full page fetched for title matches |
| welcometothejungle | sitemaps | job pages are bot-protected, so sitemap URLs only: Berlin jobs, no descriptions |
| companies | Greenhouse / Lever / Ashby / Personio / Recruitee / Teamtailor | company career pages, listed in `config/companies.yaml`; ~2 min for 137 companies |
| remoterocketship | job sitemaps | English sitemaps; jobs open to Germany/Europe/EMEA/worldwide; job page only for new candidates |
| remotecom | search pages | remote.com/jobs: `only: [remotecom]` terms; where they hire, work mode, salary; full ad for candidates |
| stepstone | search pages | `searches.yaml` terms in cities (no remote searches); excerpt + skills only, job pages not opened; ~1 min |
| linkedin | jobdrop | searches in config; descriptions fetched only for title/location matches; ~10 min |
| indeed | jobdrop | one Indeed country per config; descriptions included; fast |

Any source can be limited to its first N runs a day with `runs_per_day` in
`config/sources.yaml` (the example sets LinkedIn to 1, since it throttles heavy use); a
throttled run doesn't count, and `--source <name>` always runs it.

LinkedIn and Indeed remote flags are unreliable, so outside your on-site cities a job
from them only counts as remote if its location/title/description clearly says so
(`yojobs/remote.py`); jobs remote only per description are marked "check".

Not supported: sites that block automated access (e.g. hiring.cafe, Wellfound).

### Adding a company

Find its jobs page, take the id from the address, and add it to the right list in
`config/companies.yaml`:

| jobs page | list in companies.yaml |
|---|---|
| `job-boards.greenhouse.io/<id>` | `greenhouse` |
| `jobs.lever.co/<id>` | `lever` |
| `jobs.ashbyhq.com/<id>` | `ashby` |
| `<id>.jobs.personio.de` | `personio` (for `.jobs.personio.com` write `<id>.com`) |
| `<id>.recruitee.com` | `recruitee` |
| `<id>.teamtailor.com` (or a company's own career site "powered by Teamtailor") | `teamtailor` (id, or the career domain) |

SmartRecruiters and Workable aren't supported: SmartRecruiters' API robots.txt only
allows LinkedIn's bot, and Workable rate-limits after a handful of requests.

### Adding a source

Create `yojobs/sources/<name>.py` with `fetch(cfg, since) -> list[Job]`, register it
in `yojobs/sources/__init__.py`, and add `<name>: on` to `config/sources.yaml`.

## Tests

The same tests run on GitHub (Actions) for every pull request and push to `main`;
the result shows as a check on the pull request.

```sh
.venv/bin/python -m unittest discover tests
```

## Versions

`yojobs --version` prints the version. Every merged pull request is one version,
tagged `vX.Y.Z` on its merge commit and listed in [CHANGELOG.md](CHANGELOG.md):

- PR titles follow `[type][scope] summary` (max 80 characters)
- `[feat]` raises the minor version (0.5.0 → 0.6.0); `[fix]`, `[docs]`, `[chore]`... the patch (0.5.0 → 0.5.1)
- the PR itself bumps `__version__` in `yojobs/__init__.py` and adds its CHANGELOG entry;
  after merging, the merge commit gets the tag

## License

GPL-3.0, see [LICENSE](LICENSE).
