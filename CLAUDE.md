# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

Read `handoff.md` first, every session. Decisions and their reasons are in `decisions.md`; per-day logs are in `sessions/`. `README.md` is the public-facing overview; keep its status table in sync when a feature ships.

## What this is

A personal tool for a recruiter: watch ~5 people on LinkedIn and send one daily Slack DM when one changes jobs. The full spec is `plan.md` and the flow is `diagram.html` (Mermaid, open in a browser). Read `plan.md` before building anything new; it defines the decision rules (strict, "Possible move" for anything unclear, blank Clay data is never a change, posts older than 48h ignored, reported posts never repeated).

Built so far: the local history page (manual "Check for updates" button), the Clay comparison engine (`engine.py`, fed by a local CSV, not live Clay yet), candidate briefs with A/B/C tiers, human-approved outreach email, and demo and test modes. Not built yet: live Clay delivery, Slack digest (and Slack approval of outreach), 10 PM Eastern scheduler. Build order the user chose: website, then Clay, then Slack.

The Gmail/LinkedIn-email posts path is dropped for now: the user checked and LinkedIn offers no email option for these notifications (job-change notifications are in-app/push only, which code can't read). Do not scrape LinkedIn. Job changes come from Clay only; revisit posts only if Clay can return post text.

## Commands

- Run the history page: `python3 server.py` (set `PORT=` to use another port; restart it after editing Python files), then open http://127.0.0.1:8765 (stdlib only, no install step, no linter).
- Run the engine: `python3 engine.py [--clay FILE] [--root DIR]`. It appends to `logs/run.log` and rewrites `data/memory.json`, so trial it on a copy with `--root` (sample input: `sample/clay_latest.json`).
- Tests: `python3 -I -m unittest discover -s tests -v`; one test: `python3 -I -m unittest tests.test_engine.Evaluate.test_clay_error`.
- Syntax-check the frontend: `node --check web/app.js`.

## Architecture

The engine writes and the page reads through these files; the server calls the engine only for the manual refresh:

- `logs/run.log` is the source of truth for history. One line per event: `time | person | source | decision | what happened | link (optional)`. Time is `YYYY-MM-DD HH:MM:SS`. `person` is `-` for run-level lines. `source` is Post, Profile, Run or Email. `decision` is one of Job change, Possible move, Ignored, No change, Skipped, Error, Info. Every line about a person must carry their exact name, because `server.py` groups events by matching it to the watchlist name.
- `data/memory.json` is the last-known title, company, `email` (from Clay), `data_as_of` and `last_checked` per person, keyed by slug (lowercase name, hyphens).
- `watchlist.json` lists who is watched (name, company, LinkedIn URL). It is hand-edited by the user. It is deliberately not fed from Clay; Clay supplies current title and company, joined to the watchlist by LinkedIn URL.

`engine.py` is the writer: for each watchlist person it matches the Clay row by normalized LinkedIn URL, then `evaluate()` returns the decision. Company differences ignore case, punctuation and legal suffixes (Acme vs Acme, Inc.); a company change is Job change, a title-only change is Possible move; blank, missing, errored or over-48h-stale rows are Skipped/Error and never a change; the first run only saves a baseline. `slugify` lives in `common.py`, shared by `engine.py` and `server.py`.

`server.py` parses these into one `/api/data` response (people, 14-day activity strip, per-person events, last run). `web/app.js` renders it as a roster plus a per-person timeline. Anything that writes the log must keep the line format above or events silently disappear from the page (malformed lines are skipped).

The page only reads, with exceptions (refresh, outreach send, and demo-mode endpoints). The refresh exception: the "Check for updates" button POSTs `/api/refresh`, which runs `engine.run(..., trigger="manual")` once (logged as "Run started (manual refresh)"). That endpoint rejects requests without the page's `X-Requested-With` header or from another host/origin, and only one refresh runs at a time. The second write is the outreach email (below). Every other non-GET returns 405; don't add other write endpoints. The timeline collapses consecutive same-day repeats of No change/Skipped/Error/Ignored into one expandable row; signals are never collapsed.

## Demo mode

`python3 demo.py` rebuilds `demo/` (gitignored) with invented job changes on the real watchlist names and serves it on port 8766 (`WATCHLIST_ROOT=demo`, `WATCHLIST_DEMO=1`). Re-run it before presenting so ages and tiers are fresh. In demo mode the page shows a banner, Send only logs "(demo, not actually sent)" and never calls SMTP, and "Check for updates" finds two new Job changes live. It adds seven invented candidates (example.org addresses) to the real names. A "Demo controls" panel (shown only in demo mode) can simulate a job change or title change for anyone (`POST /api/demo/simulate`, which also updates the demo Clay CSV so the next refresh doesn't flip it back) or reset (`POST /api/demo/reset`); both endpoints return 405 outside demo mode. Real `data/` and `logs/` are never touched. Never remove the SMTP skip in demo mode: the demo uses real contacts' addresses.

## Test mode

`python3 testmode.py` builds `testmode/` (gitignored) with 4 invented candidates (A, A, B, C) on port 8767 (`WATCHLIST_ROOT=testmode`, `WATCHLIST_TEST=1`). Unlike demo mode, Send is real, but every address is `TEST_EMAIL` (or `GMAIL_ADDRESS` from `.env`) with a `+name` tag, so mail only reaches the user's own inbox. It copies `.env` into `testmode/` (credentials stay git-ignored). Use it to prove Gmail sending works end to end. No demo endpoints exist in this mode.

## Brief and tiers

`brief.py` builds a one-paragraph brief and a priority tier for anyone whose latest event is a Job change or Possible move; `server.py` adds it to `/api/data` as `brief` and sorts the roster Tier A first (people not yet emailed before those already emailed). A: Job change within 7 days; B: older Job change, or Possible move within 7 days; C: older Possible move. Age counts from the log time of the signal. `"tier": "A"|"B"|"C"` on a person in `watchlist.json` overrides the rule. The brief parses the engine's wording ("Company changed from X to Y", "Title changed from X to Y"), so change that wording and `brief.py` together.

## Outreach email (human in the loop)

When a person has a Job change or Possible move, the page shows an "Email this person" panel. `outreach.py` fills a template draft; the user edits it and clicks Send, which POSTs `/api/outreach/send` (same page-only guard as refresh, one send at a time). The recipient is read from `data/memory.json` (`email`, filled from Clay's Email column; a blank value never erases a saved one), never from the request. Sending uses Gmail SMTP with `GMAIL_ADDRESS`, `GMAIL_APP_PASSWORD`, `SENDER_NAME` in `.env` (see `.env.example`). A send is logged as `Email | Info | Sent "subject" to addr` (failures as `Email | Error`); one email per signal, detected from that log line. Nothing is ever sent automatically. The Slack version of this approval is not built; reuse `outreach.py` for it.

## Things to know

- `logs/`, `data/`, `watchlist.json`, `demo/` and `testmode/` are gitignored because they hold real people. They contain the user's ten real contacts; `data/clay_latest.csv` is the user's `clay_new.csv` (has Email, no "Last Enriched" column, so the 48h stale check is off). Backups of earlier states: `data/backup_before_demo/`, `data/backup_before_clay_new/`. Made-up sample data lives in `sample/`.
- Never put fake or demo signals in the real `logs/run.log` or `data/memory.json`: the page would offer to email a real person about a move that didn't happen. Use `demo.py` or `testmode.py`.
- In `web/app.js`, never pass a possibly-null value to DOM `append()`; it prints the text "null" (this caused "nullnull" on the page). Filter first. Render the page against a server with jsdom to catch such bugs; there is no browser in the sandbox.
- Only the user's own address may receive test mail; keep `testmode.py` aliases on `TEST_EMAIL`/`GMAIL_ADDRESS`.
- Git: branch `main`, remote `origin` = github.com/kushasupaya/bootprint-clay-linkedin-scraping. Never commit real contact names or employers (tests, docs and examples use made-up ones); `git grep` for the names in `watchlist.json` before committing.
- Secrets (`.env`, Slack token, Clay and email credentials) must stay out of git; `.gitignore` already covers `.env`.
