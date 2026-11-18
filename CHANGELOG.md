# Changelog

One version per merged pull request, tagged `vX.Y.Z` on its merge commit.
`[feat]` raises the minor version (0.5.0 → 0.6.0); `[fix]`, `[docs]`, `[chore]` and
other types raise the patch version (0.5.0 → 0.5.1).

## v0.17.0 — #29 [feat][companies] Add Teamtailor career sites as a hiring system
- `teamtailor:` in companies.yaml: a company's Teamtailor career site feed
  (`https://<id>.teamtailor.com/jobs.rss`, or the company's own career domain), which
  robots.txt allows. Title, full ad text, date, locations (city, country), department,
  and the work mode from `remoteStatus` (fully/remote, hybrid, none).

## v0.16.0 — #28 [feat][weekly] Show matches and near misses per search in the weekly email
- LinkedIn, Indeed and StepStone jobs remember which search found them ("SRE Manager ·
  Berlin"); stored with emailed jobs and near misses (new `found_by` columns, added
  automatically to existing databases).
- The weekly email (and `--weekly`) has a "Searches" table: matches emailed / near
  misses per configured search over the last 7 days, including searches that found
  nothing, to decide which searches to drop.

## v0.15.1 — #27 [perf][linkedin] Fewer LinkedIn requests: skip known jobs, shorter lookback
- Job pages are only opened for candidates not already emailed or already near misses
  (the same jobs used to be reopened every run).
- LinkedIn looks back only since its last full (unthrottled) run plus 2 hours, when
  that's shorter than the general window: with one run a day ~27 h instead of 73 h,
  so fewer result pages. After missed days it looks back further, up to the window.

## v0.15.0 — #26 [feat][sources] Limit a source to N runs a day (LinkedIn once a day)
- New per-source setting `runs_per_day`: after that many runs today the source is
  skipped (shown as "skip", not as a problem). A run in which the source was throttled
  doesn't count, so a later run retries. `--source <name>` always runs it.
- The example config sets `linkedin: runs_per_day: 1`: LinkedIn throttled 28 searches x
  3 runs a day (429 from the first search all afternoon on 2026-11-18).

## v0.14.1 — #25 [chore][scripts] Add status.sh to see whether a run is in progress
- `./scripts/status.sh`: whether a run is in progress (automatic or manual, how long,
  latest log lines), today's automatic runs, when the next is due, and the launchd
  agent's state and interval.

## v0.14.0 — #24 [feat][weekly] CV-score the weekly near misses and list the best first
- Near misses now keep their ad text (new `description` column; added automatically
  to existing databases; older near misses stay unscored).
- With CV matching on, the weekly email scores up to `weekly.near_misses_scored` (15)
  pending near misses with your CV and criteria, lists them best first and shows the
  "CV match NN% · role: …" line. Scores are cached, so previews don't redo them.

## v0.13.6 — #23 [chore][ci] Run the tests on GitHub for every pull request
- GitHub Actions workflow (`.github/workflows/tests.yml`): installs the requirements on
  Ubuntu with Python 3.12 and runs the unit tests on every pull request and push to
  main; the result shows as a ✅/❌ check on the pull request.

## v0.13.5 — #22 [fix][schedule] Check every 10 minutes so runs start soon after the Mac wakes
- launchd's interval timer doesn't fire while the Mac sleeps, so with 30-minute checks
  a due run could wait up to 30 minutes after waking (13:15 check slept through,
  run only at 13:28 by hand). The agent now checks every 10 minutes; reinstall it with
  `./scripts/install-launchd.sh` to apply.
- "Scheduled run not due" is logged at most once an hour, so the log doesn't grow.

## v0.13.4 — #21 [fix][cli] Let --cv-check continue with the run it's combined with
- `--cv-check` on its own still only shows the CV match setup. Combined with run
  options (`--days`, `--email`, `--source`, `--match`, `-v`…) it now shows the setup
  and then runs; before, `--cv-check --days 90 -v --email` silently did nothing else.

## v0.13.3 — #20 [fix][dedupe] Treat the same job retitled on another portal as a duplicate
- Duplicates were only caught by an identical normalized company + title, so the same
  job was emailed twice when portals titled it differently (Miaplaza on Himalayas and
  Arbeitnow; Trawa on Welcome to the Jungle and StartupMap).
- Now also: same company and titles sharing more than 65% of their words (brackets such
  as "(GCP/Kubernetes)" ignored), within dedupe_days, across runs and within a run.
  "Engineering Manager Banking Platform" vs "… AI Platform" stay two jobs.

## v0.13.2 — #19 [fix][linkedin] Use the job page's location and the ad's remote region
- Some LinkedIn search cards have no location; for a remote job an empty location
  counted as "no restriction", so remote jobs in Cracow, Portugal and Barcelona were
  emailed. The location now comes from the job page (fetched anyway for the
  description) when the card has none.
- The remote region named in the ad ("fully remote and global", "remote within the EU")
  is added to the location for the remote_regions rule, with the note "remote region
  from the ad, check": global/EU remote roles pass, "remote, based in Barcelona" doesn't.

## v0.13.1 — #18 [fix][linkedin] Stop on throttling instead of waiting minutes per search
- jobdrop retried LinkedIn's 429 ("too many requests") 3 times honouring Retry-After:
  four searches in one run stalled ~15.5 minutes each (LinkedIn took 78 min).
- LinkedIn requests now never retry 429s or wait for Retry-After (5xx: 2 short retries).
- A 429 stops the run's remaining LinkedIn searches/descriptions, reported to the
  health checks ("throttled"); the search order rotates each run, so the next run
  starts with the skipped ones.

## v0.13.0 — #17 [feat][matching] Add --criteria for one run; allow all five criteria
- `--criteria role,skills,gaps,wishes` overrides `criteria:` from matching.yaml for one
  run (with `--match` or a normal run).
- Up to 5 criteria (was 4), so all of role, skills, seniority, gaps, wishes can be
  rated together (role already covers skills + seniority, so they then count twice).

## v0.12.0 — #16 [feat][matching] Score from rated criteria instead of a free 0-100 number
- The model rates 1 to 4 criteria (`criteria:` in matching.yaml; default
  `[role, skills]`) on fixed scales, and yojobs computes the score: fit criteria
  averaged, `wishes` multiplies. Available: role, skills, seniority, gaps, wishes.
- The same job scored 55, 80, 90, 92 and 78 with the old free number; with ratings,
  four jobs gave identical results in 3 runs each, and two bad fits scored 4%.
- Prompt: check the CV for other wordings before calling something missing (e.g.
  FinOps); what the wishes ask for (remote, async) counts in favour, and only a clear
  contradiction is a conflict.
- Email and `--match` show the ratings, e.g. "CV match 83% · role: good · skills: strong".
  Cached scores are recomputed (prompt version 3).

## v0.11.0 — #15 [feat][matching] Score any job ad against your CV with --match
- `--match <link | file | ->` scores one ad with the local model and prints title,
  company, place, how much text was found, the score, strengths, gaps and summary.
  Nothing is saved or emailed; works even when automatic matching is off.
- Links: Greenhouse, Lever, Ashby, Personio and Recruitee through their official
  APIs; other pages through their embedded JobPosting data, else the visible text.
  Blocked pages (403/429, bot checks, timeouts) aren't worked around: yojobs says to
  save the page from the browser and use the file.
- Files: .txt, .md, .pdf, .docx, .html (a page saved from the browser); `-` reads
  pasted text, e.g. `pbpaste | python -m yojobs --match -`.

## v0.10.1 — #14 [fix][stepstone] Judge the ad language by the ad's own text, not the summary
- StepStone's excerpt is its own German summary, even for English ads, so with
  `skip_ad_languages: [de]` every StepStone job was dropped (0 of 187 matched; e.g.
  kleinanzeigen.de's "Engineering Manager SRE & DevOps" was lost).
- The ad text is now benefits section (the ad's own words, in its own language) +
  excerpt + skills: English ads are kept, German ones still skipped.

## v0.10.0 — #13 [feat][sources] Add StepStone (search pages, Berlin, excerpt only)
- New source `stepstone`: one search page per term in `searches.yaml`, in city places
  only (robots.txt disallows its API and "home office" section, so no remote
  searches); ~25 results per page from the JSON embedded in the page.
- Job pages aren't opened (they timed out when tried): `ad_must_mention` is checked
  on the ~500-character excerpt plus skills; misses go to the weekly near misses.
  Matches are marked "excerpt only".
- A failed search is skipped and reported to the health checks; all failing is an error.
- A trial over 12 terms in Berlin found 3 matches, 2 of them on no other source.

## v0.9.2 — #12 [fix][http] Cap each download at 2 minutes in total
- The 30 s timeout applied to each read, so a connection trickling data could hang a
  download much longer: one company board (Notion) stalled a run for ~10 minutes.
  Each download now also has a 120 s total limit; a board that hits it is skipped
  and reported like any failed board.

## v0.9.1 — #11 [fix][matching] Give Ollama enough context for a full CV
- Requests now set `num_ctx` (`context_tokens`, default 16384). Ollama's default room
  (~2048 tokens) silently cut a real CV + ad (~4,600 tokens), and the model returned
  an empty answer, so the job was emailed without a score.
- An empty model answer is now reported as such, with a hint, instead of a JSON error.

## v0.9.0 — #10 [feat][matching] Login question and Desktop icon to start/stop Ollama
- `scripts/install-ollama-prompt.sh`: after every login, asks "Start Ollama for the
  yojobs CV match?" (closes by itself after 2 minutes; skipped if Ollama is running).
  Remove with `scripts/uninstall-ollama-prompt.sh`.
- `scripts/make-ollama-app.sh`: creates an "Ollama" app on the Desktop that shows
  whether Ollama is running and starts or stops it with a double-click.
- `scripts/ollama-ctl.sh status|start|stop`, shared by both; logs to
  `~/Library/Logs/ollama.log`.

## v0.8.0 — #9 [feat][matching] Optional CV match score from a local Ollama model
- Off by default (`config/matching.yaml`). When enabled, each new job is compared with
  your CV (`cv/`, git-ignored) and optional `cv/wishes.md` by a local model through
  Ollama; nothing leaves the Mac.
- The email shows "CV match 82% · strengths · gaps" and a one-line summary, best
  matches first. Score only: no job is hidden.
- Each job is scored once (cached per CV, wishes and model). If Ollama isn't running
  or the CV is missing, the email just has no scores.
- `--cv-check` shows the setup (CV file, wishes, Ollama, model).

## v0.7.0 — #8 [feat][config] Split the config into a config/ folder of small files
- `config/`: settings, profile, blocklist, sources, searches and companies in separate
  files; the same key in two files is an error.
- Shorter formats: searches as terms × places (shared by LinkedIn and Indeed), company
  boards grouped by hiring system, sources as `on` / `off`, excluded titles in named groups.
- Plain-English profile keys (`title_must_have`, `ad_must_mention`, `exclude_titles`,
  `title_any`, `where:`); the old names still work.
- A single `config.yaml` still works when there's no `config/`; `--split-config`
  converts one and checks the result loads to the same configuration.
- `config.example/` replaces `config.example.yaml`.

## v0.6.0 — #7 [feat][version] Add version number, --version and changelog
- `yojobs --version` prints the version; the HTTP User-Agent includes it.
- This changelog, and version tags for every merged pull request.

## v0.5.0 — #6 [feat][sources] Add euroremotejobs.com and Jobspresso via job feeds
- New sources from WP Job Manager feeds: euroremotejobs.com (newest 100 per run) and
  Jobspresso (newest 10 per run; its robots.txt disallows feed URLs with `?`).
- "Country, Europe" locations lose the generic "Europe", so UK-only jobs don't pass.

## v0.4.1 — #5 [docs][readme] Remove the robots.txt statement

## v0.4.0 — #4 [feat][filter] Add blocked_companies to never email jobs from listed companies
- `blocked_companies:` list; case, spaces and legal suffixes are ignored.

## v0.3.0 — #3 [feat][health] Warn about failing company boards; list them weekly
- A company board failing 3 runs in a row triggers one warning email; failing boards
  are listed in the weekly summary.

## v0.2.1 — #1 [fix][wttj] Parse city in title_city URLs; never treat jobs as remote
- Most Welcome to the Jungle URLs have no job id; their city was lost and an empty
  location counted as remote (a San Francisco job got through).
- Corporate-IT titles excluded in the example profile.

## v0.2.0 — #2 [feat][sources] Add Arbeitnow (Germany/Berlin jobs, public API)

## v0.1.0 — everything before pull requests
- Sources: Remotive, Remote OK, Himalayas, Jobicy, We Work Remotely, Working Nomads,
  EU Remote Jobs, Hacker News, Landing.jobs, 4dayweek, StartupMap, Berlin Startup Jobs,
  Welcome to the Jungle, LinkedIn, Indeed, company career pages (Greenhouse, Lever,
  Ashby, Personio, Recruitee).
- Profiles with title groups, required and excluded words, on-site cities, remote
  regions, language filters; duplicate detection across portals.
- Gmail alerts (password in the macOS Keychain), launchd scheduling with safety rules,
  quiet/verbose progress, weekly summary with near misses, source health warnings,
  work-mode hints for on-site/hybrid jobs.
