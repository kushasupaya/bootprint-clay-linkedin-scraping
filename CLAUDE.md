# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

Read `handoff.md` first, every session. Decisions and their reasons are in `decisions.md`; per-day logs are in `sessions/`. `README.md` is the public-facing overview; keep its status table in sync when a feature ships.

## What this is

A personal tool for a recruiter: watch ~5 people on LinkedIn and send one daily Slack DM when one changes jobs. The full spec is `plan.md` and the flow is `diagram.html` (Mermaid, open in a browser). Read `plan.md` before building anything new; it defines the decision rules (strict, "Possible move" for anything unclear, blank Clay data is never a change, posts older than 48h ignored, reported posts never repeated).

Built so far: the local history page (with a manual "Check for updates" button) and the Clay comparison engine (`engine.py`, fed by a local file, not live Clay yet). Not built yet: live Clay delivery, Slack digest, 10 PM Eastern scheduler. Build order the user chose: website, then Clay, then Slack.

The Gmail/LinkedIn-email posts path is dropped for now: the user checked and LinkedIn offers no email option for these notifications (job-change notifications are in-app/push only, which code can't read). Do not scrape LinkedIn. Job changes come from Clay only; revisit posts only if Clay can return post text.

## Commands

- Run the history page: `python3 server.py` (set `PORT=` to use another port; restart it after editing Python files), then open http://127.0.0.1:8765 (stdlib only, no install step, no linter).
- Run the engine: `python3 engine.py [--clay FILE] [--root DIR]`. It appends to `logs/run.log` and rewrites `data/memory.json`, so trial it on a copy with `--root` (sample input: `sample/clay_latest.json`).
- Tests: `python3 -I -m unittest discover -s tests -v`; one test: `python3 -I -m unittest tests.test_engine.Evaluate.test_clay_error`.
- Syntax-check the frontend: `node --check web/app.js`.

## Architecture

The engine writes and the page reads through these files; the server calls the engine only for the manual refresh:

- `logs/run.log` is the source of truth for history. One line per event: `time | person | source | decision | what happened | link (optional)`. Time is `YYYY-MM-DD HH:MM:SS`. `person` is `-` for run-level lines. `source` is Post, Profile or Run. `decision` is one of Job change, Possible move, Ignored, No change, Skipped, Error, Info. Every line about a person must carry their exact name, because `server.py` groups events by matching it to the watchlist name.
- `data/memory.json` is the last-known title, company and `last_checked` per person, keyed by slug (lowercase name, hyphens).
- `watchlist.json` lists who is watched (name, company, LinkedIn URL). It is hand-edited by the user. It is deliberately not fed from Clay; Clay supplies current title and company, joined to the watchlist by LinkedIn URL.

`engine.py` is the writer: for each watchlist person it matches the Clay row by normalized LinkedIn URL, then `evaluate()` returns the decision. Company differences ignore case, punctuation and legal suffixes (Acme vs Acme, Inc.); a company change is Job change, a title-only change is Possible move; blank, missing, errored or over-48h-stale rows are Skipped/Error and never a change; the first run only saves a baseline. `slugify` lives in `common.py`, shared by `engine.py` and `server.py`.

`server.py` parses these into one `/api/data` response (people, 14-day activity strip, per-person events, last run). `web/app.js` renders it as a roster plus a per-person timeline. Anything that writes the log must keep the line format above or events silently disappear from the page (malformed lines are skipped).

The page only reads, with one exception: the "Check for updates" button POSTs `/api/refresh`, which runs `engine.run(..., trigger="manual")` once (logged as "Run started (manual refresh)"). That endpoint rejects requests without the page's `X-Requested-With` header or from another host/origin, and only one refresh runs at a time. Every other non-GET returns 405; don't add other write endpoints. The timeline collapses consecutive same-day repeats of No change/Skipped/Error/Ignored into one expandable row; signals are never collapsed.

## Things to know

- `logs/`, `data/` and `watchlist.json` are gitignored (plan requirement) because they hold real people. They now contain the user's five real contacts; the CSV timestamps are random demo values and one person has a fake title change (backup in `data/backup_before_demo/`). Made-up sample data lives in `sample/`.
- Git: branch `main`, remote `origin` = github.com/kushasupaya/bootprint-clay-linkedin-scraping. Never commit real contact names or employers (tests, docs and examples use made-up ones); `git grep` for the names in `watchlist.json` before committing.
- Secrets (`.env`, Slack token, Clay and email credentials) must stay out of git; `.gitignore` already covers `.env`.
