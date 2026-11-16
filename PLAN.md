# yojobs plan

## Decisions
- Local only (macOS, launchd). Python 3.12 (Homebrew) + venv, stdlib HTTP, PyYAML.
- One config file (`config.yaml`): sources + keyword profiles.
- Keywords are OR and additive: score = number of distinct matches, sorted by score.
- Notification: **email** (to self, via SMTP).
- Schedule: 2–3 runs/day (user preference; Remotive allows ≤4). Not set up yet.
- jobdrop (PyPI, v2.10.0, 33 sources incl. LinkedIn/Indeed/hiring.cafe/Wellfound)
  exists; young project (May 2026). Candidate for adding LinkedIn & co later.

## Pieces
- [x] 1. Skeleton, config, filter, terminal output
- [x] 2. Tier 1 sources: remotive, himalayas, jobicy, weworkremotely, workingnomads, landingjobs, 4dayweek
- [x] 3. SQLite dedupe (URL + normalized company/title) → only new jobs
- [x] 4. Email notification (SMTP; password in macOS Keychain, not in config)
- [ ] 5. launchd schedule + log file; warn when a source returns 0 / errors repeatedly
- [ ] 6. Tier 2: LinkedIn/Indeed (jobdrop or JobSpy), hiring.cafe, NoFluffJobs, WTTJ, EuroBrussels...

## Filter decisions
- Kubernetes is required (all_of, searched in title/description/tags).
- Other keywords are OR + additive score, matched in the title.
- Location: Germany, Europe/EU/EMEA, worldwide or plain remote. UK-only/US-only dropped.
- Excluded titles: Account Executive, Product Manager, Sales, Marketing.

## Open questions
- Jobs tied to one other European country (e.g. "Spain") are currently dropped. OK?
- GitHub remote: `gh` isn't installed; create repo manually or `brew install gh`.
