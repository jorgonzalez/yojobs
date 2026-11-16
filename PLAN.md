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
- [x] 6a. LinkedIn via jobdrop (search without descriptions, fetch descriptions only for title/location matches)
- [ ] 6b. hiring.cafe: jobdrop's buildId is stale and its browser fallback failed; needs a decision
- [x] 6c. StartupMap (JSON, no descriptions) and Berlin Startup Jobs (RSS + job page for matches)
- [ ] 6d. EU Remote Jobs (homepage HTML; job feed/API deliberately disabled by owner), ~45 min
- [ ] 6e. Not feasible: EU-Startups (Cloudflare), Upwork (403, freelance). Low value: The Hub (Nordics), JobFluent (Spain)

## Filter decisions
- Kubernetes is required (all_of, searched in title/description/tags).
- Other keywords are OR + additive score, matched in the title.
- Location: Germany, Europe/EU/EMEA, worldwide or plain remote. UK-only/US-only dropped.
- Title must match a role word (Manager, Head of, Director, Team Lead…) AND an area word (Platform, Infrastructure, DevOps, SRE, Cloud…).
- Excluded titles: Account Executive, Product Manager, Sales, Marketing, Project/Program Manager, Procurement.
- Sources without descriptions skip the Kubernetes rule; jobs are marked "Kubernetes not verified".

## Open questions
- Jobs tied to one other European country (e.g. "Spain") are currently dropped. OK?
- GitHub remote: `gh` isn't installed; create repo manually or `brew install gh`.
