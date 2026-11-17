# Changelog

One version per merged pull request, tagged `vX.Y.Z` on its merge commit.
`[feat]` raises the minor version (0.5.0 → 0.6.0); `[fix]`, `[docs]`, `[chore]` and
other types raise the patch version (0.5.0 → 0.5.1).

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
