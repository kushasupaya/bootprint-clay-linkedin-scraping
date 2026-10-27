Last updated: 2026-10-27

## Where we are
Version 1 runs locally without Slack. `python3 server.py` serves the real history page at http://127.0.0.1:8765 for the user's ten real contacts (loaded from their `clay_new.csv`, now `data/clay_latest.csv`; no signals yet, 9 of 10 have an email). On top of the history page and engine there are now:
- Candidate brief and A/B/C tier (`brief.py`); roster sorted Tier A first.
- Human-approved outreach email (`outreach.py`, "Email this person" panel): editable template, confirm dialog, one email per signal, Gmail SMTP. **Never sent a real email yet: no `.env` exists.**
- `python3 demo.py` (port 8766): 17 people (10 real names with invented moves, 7 invented), simulated sending, Demo controls to simulate a job/title change or reset, two live finds on "Check for updates".
- `python3 testmode.py` (port 8767): 4 invented candidates (A, A, B, C) with real Gmail sending, but only to the user's own inbox via `+name` aliases. Needs `.env`.
41 tests pass (`python3 -I -m unittest discover -s tests`). Pages were verified with jsdom and curl, not a real browser.

## What we did
- Outreach email with approval gate; briefs and tiers; new Clay CSV loaded; demo and test modes; fixed the "nullnull" bug (null passed to DOM append); made the activity strip subtle.
- Cleaned real data: restored one person's real title, removed a leftover fake signal from the real log (backups in `data/backup_before_clay_new/`).
- Updated CLAUDE.md, plan.md, decisions.md, README status table, session log `sessions/2026-10-27.md`.

## What's next
1. Create `.env` (copy `.env.example`: Gmail address, app password, sender name), run `python3 testmode.py`, send an email to yourself for Avery Stone and confirm it arrives, the panel shows "Email sent", and she drops below Jordan in the list.
2. Look at all three pages in a real browser (real 8765, demo 8766, test 8767), especially the brief card, email panel, Demo controls and the subtle strip.
3. Fix the Clay export: re-add a "Last Enriched" column (the 48h stale check is off without it), fill the one blank email, confirm one person's LinkedIn URL (its slug doesn't match their name), and check why several emails use another company's domain than the listed org.
4. Read the Google Sheet directly (read-only service account, key outside git); the refresh button fetches the sheet first, then runs the engine.
5. Slack daily digest built from the whole day's log lines (Job changes first, Possible moves separate, "Couldn't check X" notes, "nothing today", retry once), plus an approval button for outreach reusing `outreach.py`. Needs a personal Slack workspace, bot token (`chat:write`, `im:write`) and member ID in `.env`.
6. Scheduler at 10 PM Eastern with catch-up ("late summary"); "no data at all" warning when every row is stale or missing.
7. Tune title/org cleaning and the tier rule from real logs (tiers are recency-only; ask whether to weigh seniority or specialty).

## Open items and blockers
- User must confirm the GitHub repo is private (`gh` isn't installed here). README claims Python 3.9+ but only 3.11 was run.
- Confirm Clay re-enriches daily, credit cost per refresh, and whether it adds a row or updates one (the engine handles both).
- Before presenting, re-run `python3 demo.py` so ages and tiers are fresh (the live-find trick works once per build).
- The branch is `handoff-2026-10-26`; merge into `main` when ready. Never commit real contact names (`git grep` the names in `watchlist.json` first); `demo/`, `testmode/`, `.env`, `data/`, `logs/` are gitignored.
