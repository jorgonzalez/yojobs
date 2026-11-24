# Changelog

One version per merged pull request, tagged `vX.Y.Z` on its merge commit.
`[feat]` raises the minor version (0.5.0 → 0.6.0); `[fix]`, `[docs]`, `[chore]` and
other types raise the patch version (0.5.0 → 0.5.1).

## v0.30.0 — #53 [feat][companies] Read company boards on Deel's hiring system (jobs.deel.com)
- New hiring system `deel` in `companies.yaml` (`deel: [<id>]` for `jobs.deel.com/<id>`): one
  page per company holds every job with its ad text, places and work mode (robots.txt allows
  these pages; its `/api/` is off-limits and not used).
- Deel's own page (`deel: [deel]`) lists jobs fed from Ashby with countries but no ad text or
  work mode: the job pages of up to 5 unknown jobs per run whose title would fit (as remote)
  are opened, with 2–4 s pauses; a 403/429 stops them for that run.

## v0.29.2 — #52 [fix][stapply] Keep jobs that say "Remote" only in the location
- The Stapply query also keeps jobs whose location text says "Remote" but whose remote flag
  isn't set (Workday: ~680 such jobs this month were skipped).

## v0.29.1 — #51 [fix][weekly] Re-check stored near misses against today's rules
- The weekly email re-checks stored near misses against today's title rules before CV
  scoring and listing them: jobs a newer exclusion rejects (e.g. SAP, Account Manager,
  saved before those rules) no longer use scoring slots or appear in the email.
- Same company + near-identical title counts as one near miss (as for alerts).
- The same job from another portal (same key) is marked done with the listed one, so it
  no longer comes back the following week.

## v0.29.0 — #50 [feat][sources] Optional Stapply job dataset source (off by default)
- New source `stapply`: Stapply's open daily job dataset, read with DuckDB (optional
  dependency) from Parquet over HTTP; each slice's daily snapshot read once, jobs in Germany
  or remote since the last read, ad text only for fitting titles; multi-city ads keep all
  offices. Off in the example config (`runs_per_day: 1`).
- The weekly Searches table lists each Stapply slice, to judge whether it's worth keeping.

## v0.28.0 — #49 [feat][linkedin] Fewer LinkedIn searches per run, each with its own lookback
- `searches_per_run: N` (LinkedIn, `sources.yaml`): each run does only the next N searches
  in the saved rotation, so the searches are spread over several days.
- Each search looks back to when it last ran completely (+2 h margin, at most 7 days)
  instead of to LinkedIn's last full run; a search interrupted by a 429 isn't marked done.
- The run keeps jobs from that longer lookback (a source can widen the run's date window).
- The log shows each search's lookback (hours) and how many jobs it returned.

## v0.27.0 — #48 [feat][linkedin] A throttled run counts as the day's LinkedIn run
- `runs_per_day` now counts throttled runs too: after LinkedIn answers 429, it isn't asked
  again the same day (before, every later run tried again and was blocked at once).
- The next day's run still starts with the interrupted search and looks back to the last
  full run, so nothing in between is skipped.

## v0.26.2 — #47 [fix][search] Keep the order of search terms from the profile
- Sources with their own search (Himalayas) searched the `ad_must_mention` words in
  alphabetical order (AKS, EKS, GKE, K8s, Kubernetes, OpenShift). They now run in the order
  written in `profile.yaml`, so the preferred terms come first and still run if the site
  starts throttling later in the run.

## v0.26.1 — #46 [fix][discovery] Ignore unused Pinpoint accounts with sample jobs
- Unused Pinpoint accounts answer with the same sample jobs ("Head of DEI – Belfast",
  "Head of DEI – US", "Marketing Manager", …); `beam` and `hellobetter` looked like those
  companies' boards. Board discovery no longer suggests a Pinpoint board whose jobs are
  only these samples.

## v0.26.0 — #45 [feat][companies] Read Pinpoint job boards
- New hiring system for `companies.yaml`: `pinpoint: [<id> or career domain]`, read from
  Pinpoint's public `postings.json` (title, location, work mode, full ad text). E.g.
  adm-Indicia's "Infrastructure Lead – Europe" (fully remote) on careers.admgroup.com.
- The feed has no posting date or company name: new jobs are told apart by the seen list,
  and the company name comes from the domain ("Admgroup").
- Board discovery also tries `<id>.pinpointhq.com`.

## v0.25.1 — #44 [docs][config] Explain that short title words cover longer ones
- `config.example/profile.yaml`: words match anywhere in the title, so "Manager" already
  covers "Engineering Manager" and "Lead" covers "Team Lead" / "Tech Lead"; listing both
  finds no extra jobs. Whole words only ("Lead" ≠ "Leader", "Leiter" ≠ "Teamleiter"), and
  searches.yaml terms are different (each is its own search).
- The example's role list drops "Engineering Manager" (covered by "Manager").

## v0.25.0 — #43 [feat][enrich] Open the ad for jobs from title-only sources
- Welcome to the Jungle, StartupMap and 4dayweek list jobs without the ad text, and 4dayweek
  without a location: its empty location counted as "remote, no restriction", so Sainsbury's
  "Engineering Manager – PaaS Cloud" (hybrid, London) was emailed. For jobs whose title fits
  (and that aren't known yet), yojobs now opens the ad once (`yojobs/enrich.py`) and fills
  in what's missing: Greenhouse / Lever / Ashby links through their APIs, 4dayweek pages
  from their embedded job data (location, work mode, text), other pages from their
  schema.org JobPosting (Welcome to the Jungle, company sites).
- So the Kubernetes check, the work-mode hint and the CV match see the real ad. A source's
  own location / work mode is kept; only empty fields are filled.
- At most 10 ads per run, 2–4 s apart; a site answering 403/429 isn't asked again that run;
  a failed lookup leaves the job as before ("not verified").
## v0.24.1 — #42 [fix][dedupe] Ignore "in <place>" at the end of job titles
- Knime's "Team Lead - Site Reliability Engineering (m/f/d) in Berlin or Konstanz" (LinkedIn,
  17 Nov) came again from Welcome to the Jungle as "Team Lead Site Reliability Engineering":
  the trailing "in Berlin or Konstanz" made the titles too different (5 of 9 words). A
  trailing "in …" clause is now dropped when the word after "in" is a place (Berlin, Germany,
  Remote, …); "Engineer in Cloud Security" stays as it is.

## v0.24.0 — #41 [feat][linkedin] Continue searches where the last run stopped
- LinkedIn's search order used to rotate with the clock (one step every 4 hours), so after a
  429 the next run didn't really start with the skipped searches. Now the next start is saved
  (meta table `linkedin_next_search`): after a 429 the next run starts with the search LinkedIn
  interrupted (it may be incomplete), so every search is reached even if each run only gets
  through a few. After a complete run the start moves on by one.
- If the saved search is no longer in `searches.yaml`, the configured order is used.

## v0.23.1 — #40 [fix][filter] Treat "remote" ads that require office days as hybrid
- Yubo's "SRE Platform Manager" (Paris) arrived as remote: LinkedIn and euremotejobs label it
  remote, but the ad says "our hybrid model calls for only two office days a month" in the
  Paris office. A remote-labelled job whose ad asks for regular office presence (weekly or
  monthly office days, or a stated hybrid policy) now counts as hybrid, so its office must be
  in one of `onsite_cities` (Berlin). Sentences that make the office optional or are about
  offsites/retreats don't count.
- The email's work-mode hint understands monthly office days ("hybrid · 2 office days/month").

## v0.23.0 — #38 [feat][logs] Delete log lines older than N days (logs: keep_days)
- New `logs:` in `config/settings.yaml`: `keep_days` deletes lines older than that many days,
  `max_mb` caps each file's size (newest half kept), `files` defaults to yojobs' and
  Ollama's logs. Without settings, the old behaviour stays (yojobs.log capped at 2 MB);
  ollama.log now gets the same 2 MB cap.
- Scheduled runs write the date on every log line (`2026-11-19 07:07:18`), so lines can be
  dated; Ollama's own timestamps are understood too.
- Files are rewritten in place: launchd and `ollama serve` keep appending to them.

## v0.22.1 — #37 [fix][discovery] Survive huge or odd job-board answers
- Board discovery crashed on a company with a very large Ashby board: the answer is cut off
  at 3 MB and isn't valid JSON. A cut-off answer that starts with a job list now counts as a
  board (Ashby, Lever, Recruitee — the name is read from the first offer), and an error from
  one system no longer stops the others.
- The weekly summary is sent even if board discovery fails (noted in the log).

## v0.22.0 — #36 [feat][companies] Read company boards on Lever's EU servers
- Companies hosted on Lever's EU servers (jobs.eu.lever.co/<id>, e.g. Quantinuum) weren't
  found: yojobs only asked api.lever.co. Write them as `lever: [eu:<id>]` in
  config/companies.yaml; they're read from api.eu.lever.co.
- The weekly board discovery also tries Lever EU and suggests `lever: eu:<id>`.

## v0.21.1 — #35 [fix][linkedin] Spread LinkedIn requests out to avoid throttling
- LinkedIn answered 'too many requests' (429) on 18 and 19 Nov after 1 and 14 searches:
  the 20 searches went out in ~4 minutes (4–8 s apart, 2–5 s between job pages).
  Now 20–40 s between searches and 8–15 s between job pages, configurable per site
  as `search_pause` / `page_pause` in `config/sources.yaml`. LinkedIn takes ~15–20 min
  in a scheduled run.

## v0.21.0 — #34 [feat][log] List each match's outcome and a summary after a run
- "emailed 0 new of 2 matches" didn't say why. After an `--email` run the log now lists
  every match as `new` (emailed now), `sent` (already sent on <date>, and as which title or
  from which source if different) or `duplicate` (same job as an earlier match in this run),
  then a summary: "2 matches: 0 new, 1 already sent before, 1 duplicate in this run".
  Preview runs print the summary line too.
- README: dedupe note updated for the bracket rule of v0.20.1.

## v0.20.1 — #33 [fix][dedupe] Read bracketed title parts when only one title has them
- "Head of Platform (Infrastructure & DevOps)" (StartupMap) and "Head of Platform –
  Infrastructure, DevOps" (Remote Rocketship) weren't recognised as the same Mimica job:
  the bracketed part was always ignored. Titles are now compared with and without the
  brackets when only one has them (closer result counts), and with them when both do,
  so "EM (Platform)" vs "EM (Data)" are no longer merged either.

## v0.20.0 — #32 [feat][sources] Add Remote Rocketship from its job sitemaps
- New source `remoterocketship`: its English job sitemaps (worldwide + rest of world,
  3 requests, ~50,000 URLs); keeps jobs updated within the window whose URL says they're
  open to Germany, Berlin, Europe, EMEA or worldwide; titles filtered before anything else;
  job pages (schema.org JobPosting: full ad, exact countries, date, company) only for new
  candidates. The German section (machine-translated titles/pages) isn't used.
- First preview (30 days): 5,362 jobs in scope, 10 candidates, 3 matches (nTopology
  EM Distributed Computing Platform, Consensys DevOps Manager, Mimica Head of Platform).

## v0.19.0 — #31 [feat][sources] Add the Remote.com job board
- New source `remotecom`: one search page per term of the `only: [remotecom]` group in
  searches.yaml (`/jobs/all?query=…`, allowed by robots.txt); job data from the page:
  title, company, where they hire (worldwide or regions/countries), work mode, date,
  salary. Job pages (schema.org JobPosting, full ad) only for jobs that pass the title
  and place rules and aren't known yet. Counts in the weekly "Searches" table.
- The example's main search group is now limited to LinkedIn, Indeed and StepStone.

## v0.18.0 — #30 [feat][weekly] Suggest job boards of companies that hire for your profile
- Weekly: companies from the last 30 days' matches and near misses that aren't in
  companies.yaml are checked once (up to `weekly.discover_boards`, default 15 per week)
  for a public board on Greenhouse, Ashby, Lever, Personio, Recruitee or Teamtailor,
  trying a few spellings of the name. A board counts only if its reported name matches
  (whole words, same first word), or, where the system reports none, the id is the full
  name. Suggestions show the line for companies.yaml until it's added.

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
