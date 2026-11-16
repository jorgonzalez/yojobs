# yojobs

Local job-alert script: queries several job portals, filters by keywords, and
(soon) emails new matches a few times a day. Runs entirely on this machine.

## Setup

```sh
/opt/homebrew/bin/python3.12 -m venv .venv   # Python 3.10+ (brew install python@3.12)
.venv/bin/pip install -r requirements.txt
cp config.example.yaml config.yaml   # then edit keywords/sources
```

## Run

```sh
.venv/bin/python -m yojobs                      # all enabled sources
.venv/bin/python -m yojobs --source jobicy      # one source
.venv/bin/python -m yojobs --days 1             # override max_age_days
.venv/bin/python -m yojobs --all                # no keyword filter (debug)
```

Preview mode (above) prints matches and marks unseen ones with `*`; it saves nothing.

```sh
.venv/bin/python -m yojobs --email     # email only jobs not sent before, then remember them
```

Email setup (Gmail): enable 2-step verification, create an App Password at
https://myaccount.google.com/apppasswords, then store it in the macOS Keychain:

```sh
security add-generic-password -s yojobs-smtp -a you@gmail.com -w
```

Your address lives only in `config.yaml` (git-ignored); the password only in the Keychain.

The first run (empty `seen.sqlite`) looks back `first_run_days` (30) instead of
`max_age_days` (3). Progress is printed to stderr while sources run; results go to stdout.

## Where you can work (profile)

- `onsite_cities: [Berlin]`: on-site / hybrid jobs only there.
- `remote_regions`: remote jobs must be open to one of these (Germany, Europe, worldwide…).
  For LinkedIn remote jobs the location means where you may live, so
  "Remote · Cork, Ireland" (remote within Ireland) is dropped.

Output is sorted by score (number of distinct `any_of` keywords matched), then date.

## Duplicates

A job is never emailed twice: its URL is remembered forever, and its normalized
company + title for `dedupe_days` (default 60), which catches reposts and the same
job on another portal. Normalization drops legal suffixes (GmbH, Inc, B.V....),
gender tags like (m/w/d), location tails like "- Remote, Germany", and expands
Sr/Jr/Mgr.

## Tests

```sh
.venv/bin/python -m unittest discover tests
```

## Keywords (config.yaml → profiles)

| key | meaning |
|---|---|
| `any_of` | OR keywords; each match adds +1 to the score |
| `all_of` | AND keywords; all must match |
| `none_of` | exclude if any matches |
| `match_in` | fields to search: `title`, `description`, `tags`, `company` |
| `min_score` | minimum distinct `any_of` matches |
| `location_any` / `location_none` | keywords checked against the job location |

Matching is case-insensitive, whole-word; a space also matches a hyphen.

## Sources

| name | type | notes |
|---|---|---|
| remotive | JSON API | max ~4 requests/day; public feed is 24h delayed and small |
| himalayas | JSON API | uses keyword search (one query per keyword); rate-limited, ~2 min |
| jobicy | JSON API | latest 100 |
| weworkremotely | RSS | |
| workingnomads | JSON | latest ~35 |
| landingjobs | JSON API | EU tech, many on-site/hybrid |
| 4dayweek | RSS | titles only, no description → "not verified" |
| linkedin | jobdrop | searches in config; descriptions fetched only for title/location matches; ~10 min |
| startupmap | JSON | all ~16k EU startup jobs in one request; no descriptions → "Kubernetes not verified" |
| berlinstartupjobs | RSS | teaser only; full page fetched for title matches |
| indeed | jobdrop | Indeed Germany; descriptions included; fast |

LinkedIn and Indeed remote flags are unreliable, so outside Berlin a job from them
only counts as remote if its location/title/description clearly says so
(`yojobs/remote.py`); jobs remote only per description are marked "check".

Add a source: create `yojobs/sources/<name>.py` with `fetch(cfg, since) -> list[Job]`
and register it in `yojobs/sources/__init__.py`.
