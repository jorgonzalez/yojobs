# yojobs plan

## Decisions
- Local only (macOS, launchd). Python 3.12 (Homebrew) + venv, stdlib HTTP, PyYAML.
- One config file (`config.yaml`): sources + keyword profiles.
- Keywords are OR and additive: score = number of distinct matches, sorted by score.
- Notification: **email** (to self, via SMTP).
- Schedule: up to 3 runs/day from 06:30, 5h apart, none after 22:00 (Remotive allows ≤4).
- jobdrop (PyPI, v2.10.0, 33 sources incl. LinkedIn/Indeed/hiring.cafe/Wellfound)
  exists; young project (May 2026). Candidate for adding LinkedIn & co later.

## Pieces
- [x] 1. Skeleton, config, filter, terminal output
- [x] 2. Tier 1 sources: remotive, himalayas, jobicy, weworkremotely, workingnomads, landingjobs, 4dayweek
- [x] 3. SQLite dedupe (URL + normalized company/title) → only new jobs
- [x] 4. Email notification (SMTP; password in macOS Keychain, not in config)
- [x] 5. launchd schedule (06:30-22:00, max 3/day, 5h gap, no catch-up) + lock + retry + log
- [ ] 5b. warn when a source returns 0 / errors repeatedly
- [x] 6a. LinkedIn via jobdrop (search without descriptions, fetch descriptions only for title/location matches)
- [-] 6b. hiring.cafe: NOT automated. robots.txt disallows `?searchState=` (what jobdrop uses), and even its sitemaps sit behind a Cloudflare challenge. Use it manually / via its own alerts. Same expected for Wellfound.
- [x] 6c. StartupMap (JSON, no descriptions) and Berlin Startup Jobs (RSS + job page for matches)
- [x] 6c2. Indeed Germany via jobdrop (Berlin + remote-Germany searches)
- [x] 6c3. Welcome to the Jungle: sitemaps only (robots.txt blocks search; job pages bot-protected → 202/403 after ~60 pages). Berlin jobs only, Kubernetes not verified.
- [x] 6d. EU Remote Jobs: homepage cards (title, company, region, date); job page (JobPosting) only for matches
- [x] Hacker News "Who is hiring?" (HN Search API): few leadership roles; cheap, kept enabled
- [-] Kube Careers: checked, skipped. No feed, API needs login; public pages show only ~13 jobs (5 remote), mostly US ICs; Germany page empty.
- [x] Company career pages: 66 boards (Greenhouse/Lever/Ashby official APIs); add more in config
- [ ] Next candidates: Arbeitnow, RemoteOK
- [ ] 6e. Not feasible: EU-Startups (Cloudflare), Upwork (403, freelance). Low value: The Hub (Nordics), JobFluent (Spain)

## Filter decisions
- Kubernetes is required (all_of, searched in title/description/tags).
- Other keywords are OR + additive score, matched in the title.
- Location: Germany, Europe/EU/EMEA, worldwide or plain remote. UK-only/US-only dropped.
- Title must match a role word (Manager, Head of, Director, Team Lead…) AND an area word (Platform, Infrastructure, DevOps, SRE, Cloud…).
- Excluded titles: Account Executive, Product Manager, Sales, Marketing, Project/Program Manager, Procurement, Head of Product, Growth.
- Sources without descriptions skip the Kubernetes rule; jobs are marked "Kubernetes not verified".

## Open questions
- Jobs tied to one other European country (e.g. "Spain") are currently dropped. OK?
- GitHub remote: `gh` isn't installed; create repo manually or `brew install gh`.
