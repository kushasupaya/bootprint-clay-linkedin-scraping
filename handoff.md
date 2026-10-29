Last updated: 2026-10-28

## Where we are
Version 1 runs locally. `python3 server.py` serves the real history page at http://127.0.0.1:8765 for the user's ten real contacts (from `data/clay_latest.csv`; no signals yet, 9 of 10 have an email). Built:
- Clay comparison engine, history page with a manual "Check for updates", A/B/C candidate briefs, human-approved outreach email (Gmail SMTP, `outreach.py`). **No real email has been sent yet: `.env` has Slack keys but no Gmail settings.**
- **Slack daily digest** (`python3 digest.py`): runs the engine, then DMs Job changes, Possible moves and "Couldn't check X" notes logged since the last sent digest **and within the last 48 hours**. Older changes are left out of Slack (logged), but stay on the page with their tiers. One retry on failure. **Verified for real**: a test message reached the user's Slack. Nothing runs it automatically yet.
- Demo mode (`python3 demo.py`, port 8766): 13 people, 3 Tier A, invented moves from one `SCENARIOS` table, two live finds on "Check for updates", Demo controls, and a "Slack alert" button that previews the digest as a Slack-style card and can really DM it (marked "[Demo]") to the user's own Slack. Restart `demo.py` after editing `demo.py` or `server.py`.
- Test mode (`python3 testmode.py`, port 8767): 4 invented candidates, real Gmail to the user's own inbox. Needs Gmail settings in `.env`.
- Page: dark mode (bulb toggle, grayish palette) and a people list that collapses to an avatar rail (desktop).
64 tests pass. Pages were verified with jsdom and curl, never in a real browser.

Git: branch `handoff-2026-10-27`, pushed, five feature commits plus this handoff commit. `main` is untouched. The older `handoff-2026-10-26` still has one superseded squashed commit.

## What we did
- Built and tested the Slack digest, fixed the macOS Python certificate error, and sent real test messages to the user's Slack.
- Added the 48-hour rule for Slack (page and tiers unchanged).
- Reworked the demo (smaller roster, new invented moves, cleaner `demo.py`), added dark mode, the collapsible list and the demo Slack alert.
- Committed in focused commits and pushed.

## What's next
1. Look at the page in a real browser: real 8765, demo 8766 (try dark mode, the list rail, the Slack alert card), test 8767. Re-run `python3 demo.py` right before presenting so ages and tiers are fresh (live finds work once per build).
2. Build the 10 PM Eastern scheduler: run `digest.py` daily (pass `--late` when the laptop was closed at 10 PM and it runs on reopen), plus the "no data at all" warning when every row is stale or missing.
3. Add Gmail settings to `.env` (see `.env.example`), run `python3 testmode.py`, send an email to yourself and confirm the panel shows "Email sent" and tiers reorder.
4. Fix the Clay export: re-add a "Last Enriched" column (the 48h stale check is off without it, and Slack's 48h age falls back to the log time), fill the one blank email, confirm the one LinkedIn URL whose slug doesn't match the person's name, and check why several emails use another company's domain.
5. Open a pull request from `handoff-2026-10-27` into `main` and merge; decide whether to delete `handoff-2026-10-26`.
6. Read the Google Sheet directly (read-only service account, key outside git); the refresh button fetches the sheet first, then runs the engine.
7. Later: Slack approve-outreach button reusing `outreach.py` (needs a public interactivity URL); tune the tier rule and title/org cleaning from real logs (tiers are recency-only; ask whether to weigh seniority or specialty).

## Open items and blockers
- User must confirm the GitHub repo is private (`gh` isn't installed here). README claims Python 3.9+ but only 3.11 was run.
- Two test messages ("Nothing today" and a "[Demo]" digest) are in the user's Slack DM and can be deleted. A real `python3 digest.py` will DM for real now that `.env` has the Slack keys.
- Confirm Clay re-enriches daily, credit cost per refresh, and whether it adds a row or updates one (the engine handles both).
- Never commit real contact names (`git grep` the names in `watchlist.json` first); `demo/`, `testmode/`, `.env`, `data/`, `logs/` are gitignored. Stray `.Rhistory` and `.gitignore.swp` in the repo root are untracked and not ours.
