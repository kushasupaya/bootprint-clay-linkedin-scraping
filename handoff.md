Last updated: 2026-10-28

## Where we are
Version 1 runs locally without Slack. `python3 server.py` serves the real history page at http://127.0.0.1:8765 for the user's ten real contacts (loaded from their `clay_new.csv`, now `data/clay_latest.csv`; no signals yet, 9 of 10 have an email). Built on top of the engine and history page:
- Candidate brief and A/B/C tier (`brief.py`); roster sorted Tier A first.
- Human-approved outreach email (`outreach.py`, "Email this person" panel): editable template, confirm dialog, one email per signal, Gmail SMTP. **No real email has been sent yet: no `.env` exists.**
- `python3 demo.py` (port 8766): 17 people (10 real names with invented moves, 7 invented), simulated sending, Demo controls (simulate job/title change, reset), two live finds on "Check for updates".
- `python3 testmode.py` (port 8767): 4 invented candidates (A, A, B, C), real Gmail sending, but only to the user's own inbox via `+name` aliases. Needs `.env`.
- Slack daily digest (2026-10-28): `python3 digest.py` runs the engine, then DMs Job changes, Possible moves and "Couldn't check X" notes since the last sent digest (`slack.py` formats and sends; one retry). Verified with unit tests (fake Slack) and `--dry-run` on sample data; **never sent to real Slack**: needs `SLACK_BOT_TOKEN` and `SLACK_USER_ID` in `.env`. Not committed yet.
- Demo upgrades (2026-10-28, uncommitted): trimmed roster (13 people, 3 Tier A) with new invented moves, `demo.py` rewritten around one `SCENARIOS` table, dark mode (bulb icon toggle, grayish palette), collapsible people list (avatar rail), a 48-hour rule for Slack (changes logged more than 48 hours ago are not sent but stay on the page with their tiers), and a demo-only "Slack alert" button that previews and really sends the `[Demo]` digest to the user's own DM.
59 tests pass. Pages were verified with jsdom and curl, not in a real browser.

Git: work is committed as six focused commits on branch `handoff-2026-10-27` (pushed). `main` is untouched. The older `handoff-2026-10-26` branch still has one superseded squashed commit.

## What we did
- Last session block: outreach email with approval gate, briefs and tiers, new Clay CSV, demo and test modes, "nullnull" fix, subtler activity strip.
- This block: rewrote the single commit into six commits with proper messages and pushed to a new branch (force-push was blocked, so no history was overwritten). Docs, session log and decisions updated.

## What's next
1. Create `.env` (copy `.env.example`: Gmail address, app password, sender name), run `python3 testmode.py`, send an email to yourself for the first candidate and confirm it arrives, the panel shows "Email sent", and that candidate drops below the second Tier A in the list.
2. Look at all three pages in a real browser (real 8765, demo 8766, test 8767), especially the brief card, email panel, Demo controls and the subtle strip.
3. Fix the Clay export: re-add a "Last Enriched" column (the 48h stale check is off without it), fill the one blank email, confirm the one LinkedIn URL whose slug doesn't match the person's name, and check why several emails use another company's domain than the listed org.
4. Open a pull request from `handoff-2026-10-27` into `main` and merge; decide whether to delete `handoff-2026-10-26` (or approve a force-push to replace it).
5. Read the Google Sheet directly (read-only service account, key outside git); the refresh button fetches the sheet first, then runs the engine.
6. Try the Slack digest for real: create a Slack app in a personal workspace (bot scope `chat:write`), put the token and your member ID in `.env`, run `python3 digest.py`. Then, later, an approve-outreach button reusing `outreach.py` (needs a public interactivity URL).
7. Scheduler at 10 PM Eastern with catch-up ("late summary"); "no data at all" warning when every row is stale or missing.
8. Tune title/org cleaning and the tier rule from real logs (tiers are recency-only; ask whether to weigh seniority or specialty).

## Open items and blockers
- User must confirm the GitHub repo is private (`gh` isn't installed here). README claims Python 3.9+ but only 3.11 was run.
- Confirm Clay re-enriches daily, credit cost per refresh, and whether it adds a row or updates one (the engine handles both).
- Before presenting, re-run `python3 demo.py` so ages and tiers are fresh (the live-find trick works once per build).
- Never commit real contact names (`git grep` the names in `watchlist.json` first); `demo/`, `testmode/`, `.env`, `data/`, `logs/` are gitignored. Stray `.Rhistory` and `.gitignore.swp` in the repo root are untracked and not ours.
