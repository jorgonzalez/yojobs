# Changelog

One version per merged pull request, tagged `vX.Y.Z` on its merge commit.
`[feat]` raises the minor version (0.5.0 → 0.6.0); `[fix]`, `[docs]`, `[chore]` and
other types raise the patch version (0.5.0 → 0.5.1).

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
