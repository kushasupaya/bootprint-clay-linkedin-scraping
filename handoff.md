Last updated: 2026-10-26

## Where we are
Version 1 works locally without Slack. `python3 server.py` shows the history page at http://127.0.0.1:8765 for five real people (light, vivid design; repeated routine checks collapse into one row per day). The "Check for updates" button runs the engine on demand. `python3 engine.py` reads `data/clay_latest.csv`, compares each person with `data/memory.json`, appends to `logs/run.log` and prints a summary. 23 tests pass (`python3 -I -m unittest discover -s tests`).

The data is demo-flavored: the CSV timestamps are random, the stale person is deliberately stale, and one person has a fake title change (a Possible move). Backup of the pre-demo state: `data/backup_before_demo/`. Git is set up: `main` is pushed to github.com/kushasupaya/bootprint-clay-linkedin-scraping (first commit d400481).

## What we did
- Dropped the LinkedIn posts path (no email option from LinkedIn); Clay is the only signal.
- Built the comparison engine, CSV input, Clay timestamps, title/org cleaning and tests.
- Loaded the user's five real contacts; archived made-up samples in `sample/`.
- Redesigned the page, collapsed repeated checks, added the guarded refresh button.
- Updated `CLAUDE.md`, `decisions.md`, `.gitignore`.

## What's next
1. Replace the demo CSV (random timestamps, fake title change) with a real export from the Clay-filled sheet, or restore from `data/backup_before_demo/`, and re-run the engine.
2. Read the Google Sheet directly (read-only service account, key file kept out of git). The refresh button should fetch the sheet first, then run the engine.
3. Slack daily digest: build it from the whole day's Job change/Possible move log lines, not just the last run, because a manual refresh updates memory and would hide the change at 10 PM. Job changes first, possible moves in their own section, "Couldn't check X's profile today" notes, "nothing today" on quiet days, retry once on failure and log it. Needs a bot token and member ID in `.env`.
4. Scheduler at 10 PM Eastern with catch-up when the laptop reopens, labeled "late summary".
5. "No data at all" warning when every row is stale or missing, so a broken Clay refresh isn't a quiet day.
6. Tune the title/org cleaning from a few days of real logs if false Possible moves appear.
7. Keep committing at each milestone. Confirm the GitHub repo is private (I couldn't check; `gh` isn't installed). `.gitignore` excludes `.env`, `logs/`, `data/`, `watchlist.json`; real names are scrubbed from tracked files.

## Open items and blockers
- Confirm Clay re-enriches on a daily schedule, the credit cost per refresh, and whether it adds a row per refresh or updates the existing one (the engine handles both).
- Slack: needs a personal free workspace, bot token (`chat:write`, `im:write`) and member ID.
- The new page features were not checked visually by the assistant; the user should confirm the collapsed rows and refresh button look right.
- Posts path stays parked unless Clay can return post text.
