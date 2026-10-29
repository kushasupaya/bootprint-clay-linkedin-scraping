# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

Read `handoff.md` first, every session. Decisions and their reasons are in `decisions.md`; per-day logs are in `sessions/`. `README.md` is the public-facing overview; keep its status table in sync when a feature ships.

## What this is

A personal tool for a recruiter: watch ~5 people on LinkedIn and send one daily Slack DM when one changes jobs. The full spec is `plan.md` and the flow is `diagram.html` (Mermaid, open in a browser). Read `plan.md` before building anything new; it defines the decision rules (strict, "Possible move" for anything unclear, blank Clay data is never a change, posts older than 48h ignored, reported posts never repeated).

Built so far: the local history page (manual "Check for updates" button), the Clay comparison engine (`engine.py`, fed by a local CSV, not live Clay yet), candidate briefs with A/B/C tiers, human-approved outreach email, demo and test modes, and the Slack daily digest (`digest.py`, `slack.py`). Slack approval of outreach by green-check reaction (`approvals.py`). Not built yet: live Clay delivery, 10 PM Eastern scheduler. Build order the user chose: website, then Clay, then Slack.

The Gmail/LinkedIn-email posts path is dropped for now: the user checked and LinkedIn offers no email option for these notifications (job-change notifications are in-app/push only, which code can't read). Do not scrape LinkedIn. Job changes come from Clay only; revisit posts only if Clay can return post text.

## Commands

- Run the history page: `python3 server.py` (set `PORT=` to use another port; restart it after editing Python files), then open http://127.0.0.1:8765 (stdlib only, no install step, no linter).
- Run the engine: `python3 engine.py [--clay FILE] [--root DIR]`. It appends to `logs/run.log` and rewrites `data/memory.json`, so trial it on a copy with `--root` (sample input: `sample/clay_latest.json`).
- Tests: `python3 -I -m unittest discover -s tests -v`; one test: `python3 -I -m unittest tests.test_engine.Evaluate.test_clay_error`.
- Send the Slack digest: `python3 digest.py [--root DIR] [--no-engine] [--dry-run] [--late]` (runs the engine first, then DMs what changed since the last sent digest; `--dry-run` prints instead of sending, so trial it with `--root` on a copy).
- Syntax-check the frontend: `node --check web/app.js`.

## Architecture

The engine writes and the page reads through these files; the server calls the engine only for the manual refresh:

- `logs/run.log` is the source of truth for history. One line per event: `time | person | source | decision | what happened | link (optional)`. Time is `YYYY-MM-DD HH:MM:SS`. `person` is `-` for run-level lines. `source` is Post, Profile, Run, Email or Slack. `decision` is one of Job change, Possible move, Ignored, No change, Skipped, Error, Info. Every line about a person must carry their exact name, because `server.py` groups events by matching it to the watchlist name.
- `data/memory.json` is the last-known title, company, `email` (from Clay), `data_as_of` and `last_checked` per person, keyed by slug (lowercase name, hyphens).
- `watchlist.json` lists who is watched (name, company, LinkedIn URL). It is hand-edited by the user. It is deliberately not fed from Clay; Clay supplies current title and company, joined to the watchlist by LinkedIn URL.

`engine.py` is the writer: for each watchlist person it matches the Clay row by normalized LinkedIn URL, then `evaluate()` returns the decision. Company differences ignore case, punctuation and legal suffixes (Acme vs Acme, Inc.); a company change is Job change, a title-only change is Possible move; blank, missing, errored or over-48h-stale rows are Skipped/Error and never a change; the first run only saves a baseline. `slugify` lives in `common.py`, shared by `engine.py` and `server.py`.

`server.py` parses these into one `/api/data` response (people, 14-day activity strip, per-person events, last run). `web/app.js` renders it as a roster plus a per-person timeline. Anything that writes the log must keep the line format above or events silently disappear from the page (malformed lines are skipped).

The page only reads, with exceptions (refresh, outreach send, and demo-mode endpoints). The refresh exception: the "Check for updates" button POSTs `/api/refresh`, which runs `engine.run(..., trigger="manual")` once (logged as "Run started (manual refresh)"). That endpoint rejects requests without the page's `X-Requested-With` header or from another host/origin, and only one refresh runs at a time. The second write is the outreach email (below). Every other non-GET returns 405; don't add other write endpoints. The timeline collapses consecutive same-day repeats of No change/Skipped/Error/Ignored into one expandable row; signals are never collapsed.

## Demo mode

`python3 demo.py` rebuilds `demo/` (gitignored) with invented job changes on the real watchlist names and serves it on port 8766 (`WATCHLIST_ROOT=demo`, `WATCHLIST_DEMO=1`). Re-run it before presenting so ages and tiers are fresh. In demo mode the page shows a banner, Send only logs "(demo, not actually sent)" and never calls SMTP, and "Check for updates" finds two new Job changes live. It adds three invented candidates (example.org addresses) to the real names; scenarios live in one `SCENARIOS` table in `demo.py`. A "Demo controls" panel (shown only in demo mode) can simulate a job change or title change for anyone (`POST /api/demo/simulate`, which also updates the demo Clay CSV so the next refresh doesn't flip it back) or reset (`POST /api/demo/reset`); both endpoints return 405 outside demo mode. The "Slack alert" button previews the digest (`GET /api/demo/slack`, built by `digest.compose` from the demo log) as a Slack-style card and can really DM it (`POST /api/demo/slack`) to the user's own Slack: `demo.py` copies only `SLACK_BOT_TOKEN` and `SLACK_USER_ID` from the real `.env` into `demo/.env`, the recipient is never taken from the request, and messages are marked "[Demo]" so the user can delete them. The user approved this real send to their own DM. Both routes exist only in demo mode. Real `data/` and `logs/` are never touched. Never remove the SMTP skip in demo mode: the demo uses real contacts' addresses.

## Test mode

`python3 testmode.py` builds `testmode/` (gitignored) with 4 invented candidates (A, A, B, C) on port 8767 (`WATCHLIST_ROOT=testmode`, `WATCHLIST_TEST=1`). Unlike demo mode, Send is real, but every address is `TEST_EMAIL` (or `GMAIL_ADDRESS` from `.env`) with a `+name` tag, so mail only reaches the user's own inbox. It copies `.env` into `testmode/` (credentials stay git-ignored). Use it to prove Gmail sending works end to end. No demo endpoints exist in this mode.

## Brief and tiers

`brief.py` builds a one-paragraph brief and a priority tier for anyone whose latest event is a Job change or Possible move; `server.py` adds it to `/api/data` as `brief` and sorts the roster Tier A first (people not yet emailed before those already emailed). A: Job change within 7 days; B: older Job change, or Possible move within 7 days; C: older Possible move. Age counts from the log time of the signal. `"tier": "A"|"B"|"C"` on a person in `watchlist.json` overrides the rule. The brief parses the engine's wording ("Company changed from X to Y", "Title changed from X to Y"), so change that wording and `brief.py` together.

## Outreach email (human in the loop)

When a person has a Job change or Possible move, the page shows an "Email this person" panel. `outreach.py` fills a template draft; the user edits it and clicks Send, which POSTs `/api/outreach/send` (same page-only guard as refresh, one send at a time). The recipient is read from `data/memory.json` (`email`, filled from Clay's Email column; a blank value never erases a saved one), never from the request. Sending uses Gmail SMTP with `GMAIL_ADDRESS`, `GMAIL_APP_PASSWORD`, `SENDER_NAME` in `.env` (see `.env.example`). A send is logged as `Email | Info | Sent "subject" to addr` (failures as `Email | Error`); one email per signal, detected from that log line. Nothing is ever sent automatically. The Slack version is `approvals.py` (below).

## Slack digest

`digest.py` runs the engine, then `collect()` reads `logs/run.log` for every Job change / Possible move logged after the last `Slack | Info | Sent daily digest` line **and within the last 48 hours** (`digest.MAX_AGE`, the same rule as the engine's stale-Clay check; older ones are left out of Slack, logged as `Slack | Info | Left N change(s) out of the digest ...`, and stay on the page with their usual tier, since tiers are recency-based on their own 7-day rule and the page is what the recruiter watches), plus "Couldn't check X" notes for people whose newest Profile line in that window is Skipped/Error. `slack.py` formats it (Job changes first, Possible moves in a separate section, a "nothing today" message otherwise, "Late summary." with `--late`) and posts with `chat.postMessage` to `SLACK_USER_ID` using `SLACK_BOT_TOKEN` (both in `.env`, stdlib `urllib`). A failed send is retried once, then logged as `Slack | Error`; because only a sent line moves the window, the next run re-includes those signals. The digest itself is an alert; the log and the page stay the record, and the draft-email DMs below are the only Slack action. 
## Slack approval of outreach

After the digest is sent, `digest.py` calls `approvals.offer()`: one extra DM per digest signal whose person has a valid email in `data/memory.json`, showing the exact To, Subject and body from `outreach.build_draft`. Offers are stored in `data/approvals.json`. `python3 approvals.py [--watch]` polls `reactions.get` and, when `SLACK_USER_ID` has put a green check on an offer, sends that exact text via `outreach.send_email` and logs `Email | Info | Sent "subject" to addr (approved in Slack)` (so the page shows it as emailed). Real buttons need a public interactivity URL or Socket Mode (a websocket dependency), so reactions are used instead: polling, no inbound traffic, stdlib only. Guards: only the user's reaction counts; the address must still equal the one shown; a prior `Email | Sent` for that signal blocks it; offers expire after 48 hours; a draft with the `[Your name]` placeholder or over 2500 characters is never offered. Editing stays on the page. Needs the `reactions:read` bot scope (plus `im:history` if Slack returns `missing_scope`); nothing runs `approvals.py` automatically yet. In demo mode the "Slack alert" send also posts up to two "[Demo] Draft email" DMs (`approvals.offer(demo=True)`, stored with `demo: true`); `demo.py` runs a background thread that calls `approvals.process(demo=True)` every 10 seconds, and a green check there only logs `... (demo, not actually sent)` and replies in the thread. SMTP is never called for a demo offer, even without the flag (the stored mark alone is enough); keep it that way.

## Things to know

- `logs/`, `data/`, `watchlist.json`, `demo/` and `testmode/` are gitignored because they hold real people. They contain the user's ten real contacts; `data/clay_latest.csv` is the user's `clay_new.csv` (has Email, no "Last Enriched" column, so the 48h stale check is off). Backups of earlier states: `data/backup_before_demo/`, `data/backup_before_clay_new/`. Made-up sample data lives in `sample/`.
- To try Slack approval for real, use `python3 testmode.py` (Ctrl-C once ready), then `digest.py --root <abs path>/testmode --no-engine`, react with a green check, then `approvals.py --root <abs path>/testmode`; the real watchlist has no signals.
- Never put fake or demo signals in the real `logs/run.log` or `data/memory.json`: the page would offer to email a real person about a move that didn't happen. Use `demo.py` or `testmode.py`.
- Dark mode: `<html data-theme="light|dark">` is set by a small script in `web/index.html` (saved choice in `localStorage`, else the system setting) and flipped by the header toggle (`setupTheme` in `web/app.js`). `web/styles.css` keeps every color in `:root` variables with a `:root[data-theme="dark"]` override, so use a variable for any new color, never a hex. `--job`/`--maybe` are text colors; use `--job-fill`/`--maybe-fill` under white text.
- The people list collapses to an avatar rail on desktop (`#list-toggle`, `setupListToggle` in `web/app.js`; `data-list="collapsed"` on `#layout`, saved in `localStorage` as `list`). The rail hides the name text visually but keeps it for screen readers, so keep the `title`/text on `.person` buttons. Phones ignore it (they already switch between list and person).
- In `web/app.js`, never pass a possibly-null value to DOM `append()`; it prints the text "null" (this caused "nullnull" on the page). Filter first. Render the page against a server with jsdom to catch such bugs; there is no browser in the sandbox.
- Only the user's own address may receive test mail; keep `testmode.py` aliases on `TEST_EMAIL`/`GMAIL_ADDRESS`.
- Git: default branch `main`; work is on `handoff-2026-10-27` (the older `handoff-2026-10-26` holds one superseded squashed commit). Remote `origin` = github.com/kushasupaya/bootprint-clay-linkedin-scraping. Commit in small focused commits with a subject plus a "why" body; never force-push without the user's say-so (the auto-mode classifier blocks it). Never commit real contact names or employers (tests, docs and examples use made-up ones); `git grep` for the names in `watchlist.json` before committing.
- If Python's `urllib` fails with `CERTIFICATE_VERIFY_FAILED` (Slack, any HTTPS), run `/Applications/Python 3.11/Install Certificates.command`; it is a macOS python.org install issue, not a code bug.
- After editing `demo.py` or `server.py`, restart the running demo server (port 8766): it keeps the old modules in memory, so Reset would rebuild the old demo. Use absolute paths in shell commands; `cd demo` leaves later commands in the wrong folder.
- Secrets (`.env`, Slack token, Clay and email credentials) must stay out of git; `.gitignore` already covers `.env`.
