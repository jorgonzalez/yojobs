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
cp config.example.yaml config.yaml     # then edit: email, sources, profiles
```

`config.yaml` is git-ignored: your email address and searches never go into the repo.
`config.example.yaml` documents every option and contains example profiles.

### Email (Gmail)

Enable 2-step verification on your Google account, create an App Password at
https://myaccount.google.com/apppasswords, then store it in the macOS Keychain:

```sh
security add-generic-password -U -s yojobs-smtp -a you@gmail.com -w
```

Paste the App Password when asked (spaces are ignored). Use the same address as
`email: username:` in `config.yaml`. The password lives only in the Keychain.

## Run

```sh
.venv/bin/python -m yojobs                      # preview: all enabled sources, nothing saved
.venv/bin/python -m yojobs --source jobicy      # one source (repeatable)
.venv/bin/python -m yojobs --days 7             # override max_age_days
.venv/bin/python -m yojobs --all                # no keyword filter (debug)
.venv/bin/python -m yojobs --email              # email jobs not sent before, then remember them
.venv/bin/python -m yojobs --email --days 30    # catch-up email for the last month
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

launchd starts `yojobs --scheduled` every 30 minutes and once after login/wake.
yojobs only runs (with `--email`) when due per `schedule:` in config.yaml:
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
| Follow the log | `tail -f ~/Library/Logs/yojobs.log` |
| Is the launchd job loaded, did it exit cleanly? | `launchctl print gui/$(id -u)/local.yojobs \| grep -E "state\|runs\|last exit"` |
| Is a run going right now? | `pgrep -fl yojobs` |
| Would it run now, and why (not)? | `.venv/bin/python -m yojobs --check-schedule` |
| When did successful runs happen? | `cat schedule_state.json` |

`state = not running` is normal between ticks. If the log shows
"Operation not permitted", macOS is blocking background access to the folder (e.g.
`~/Documents`): grant Python access in System Settings → Privacy & Security, or
move the repo elsewhere and reinstall.

## Search profiles (config.yaml → profiles)

A job is reported if it passes **any** profile. Checks, in order:

| key | meaning |
|---|---|
| `none_of` | drop the job if any of these appear (searched in `exclude_in`, default: `match_in`) |
| `all_of` | every entry must appear (searched in `all_of_in`); `"a\|b"` = either word |
| `onsite_cities` | on-site / hybrid jobs are kept only in these cities (any work mode is fine there) |
| `remote_regions` | remote jobs must be open to one of these (e.g. Germany, Europe, Worldwide) or say plain "Remote"; empty = anywhere |
| `groups` | named word lists; the `match_in` text needs one word from **each** group (AND between groups, OR inside) |
| `any_of` | extra OR words; each distinct match adds +1 to the score |
| `min_score` | if `any_of` is set, at least this many distinct matches |
| `match_in` | fields to match: `title`, `description`, `tags`, `company`, `location` |

Matching is case-insensitive and whole-word; a space also matches a hyphen.

Sources without job descriptions (marked below) can't check `all_of`: their jobs are
kept and marked "<word> not verified" in the email.

On-site / hybrid jobs get a work-mode hint next to the location, e.g.
`Berlin (hybrid · 2-3 office days/week)`. It comes from the job board when it states
the mode (Greenhouse, Lever, Ashby, StartupMap), otherwise from the ad text in English
or German ("3 days a week in the office", "2 Tage pro Woche im Büro"). When the ad
gives a number of office days, that number decides: under 5 is hybrid, 5 is on-site.

For remote jobs the location means where you may live, so "Remote · Cork, Ireland"
or "Remote, USA only" are dropped unless the region is allowed.

See `config.example.yaml` for complete examples: a platform/infrastructure leadership
profile (active), a remote Python backend developer, data engineering in Munich, and
frontend roles at specific companies.

## Duplicates

A job is never emailed twice: its URL is remembered forever, and its normalized
company + title for `dedupe_days` (default 60), which catches reposts and the same
job on another portal. Normalization drops legal suffixes (GmbH, Inc, B.V....),
gender tags like (m/w/d), location tails like "- Remote, Germany", and expands
Sr/Jr/Mgr.

## Sources

| name | type | notes |
|---|---|---|
| remotive | JSON API | max ~4 requests/day; public feed is 24h delayed and small |
| remoteok | JSON API | latest ~100, mostly US-focused; terms: credit Remote OK + link to the job |
| himalayas | JSON API | keyword search (one query per `all_of` word); rate-limited, ~2 min |
| jobicy | JSON API | latest 100; optional `geo` |
| weworkremotely | RSS | optional category feed `url` |
| workingnomads | JSON | latest ~35 |
| euremotejobs | homepage HTML | feed/API disabled by owner; latest ~60 jobs; job page opened only for matches |
| hackernews | HN Search API | monthly "Who is hiring?" threads (latest 2); first line `Company \| Role \| Location \| REMOTE (EU)` parsed |
| landingjobs | JSON API | EU tech, many on-site/hybrid |
| 4dayweek | RSS | titles only, no descriptions |
| startupmap | JSON | ~16k EU startup jobs in one request; no descriptions |
| berlinstartupjobs | RSS | teaser only; full page fetched for title matches |
| welcometothejungle | sitemaps | job pages are bot-protected, so sitemap URLs only: Berlin jobs, no descriptions |
| companies | Greenhouse / Lever / Ashby APIs | company career pages, `boards:` as `"system:id"`; ~70 s for 66 companies |
| linkedin | jobdrop | searches in config; descriptions fetched only for title/location matches; ~10 min |
| indeed | jobdrop | one Indeed country per config; descriptions included; fast |

LinkedIn and Indeed remote flags are unreliable, so outside your on-site cities a job
from them only counts as remote if its location/title/description clearly says so
(`yojobs/remote.py`); jobs remote only per description are marked "check".

Not supported: sites that block automated access (e.g. hiring.cafe, Wellfound).
yojobs respects robots.txt and does not work around bot protection.

### Adding a company

Find its jobs page and use the id from the URL:

| jobs page | config entry |
|---|---|
| `job-boards.greenhouse.io/<id>` | `"greenhouse:<id>"` |
| `jobs.lever.co/<id>` | `"lever:<id>"` |
| `jobs.ashbyhq.com/<id>` | `"ashby:<id>"` |

### Adding a source

Create `yojobs/sources/<name>.py` with `fetch(cfg, since) -> list[Job]`, register it
in `yojobs/sources/__init__.py`, and add `<name>: {enabled: true}` under `sources:`.

## Tests

```sh
.venv/bin/python -m unittest discover tests
```
