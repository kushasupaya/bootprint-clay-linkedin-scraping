Last updated: 2026-10-28

## Where we are
Version 1 runs locally. `python3 server.py` serves the history page at http://127.0.0.1:8765 for the user's ten real contacts (from `data/clay_latest.csv`; no signals yet). Built:
- Clay comparison engine, history page with "Check for updates", A/B/C briefs, outreach email from the page (Gmail SMTP). **No real email has ever been sent: the three Gmail keys in `.env` are empty.**
- Slack daily digest (`python3 digest.py`, 48-hour rule), verified with a real test DM. Slack approval of outreach (`approvals.py`): after the digest, one draft-email DM per signal; the user's green-check reaction sends that exact draft. Run `python3 approvals.py --watch`. Needs `reactions:read` (added, app reinstalled). Unit-tested only, never run against live Slack.
- Demo mode (`python3 demo.py`, port 8766): the "Slack alert" send also posts up to two "[Demo] Draft email" DMs; a green check only logs a pretend send. **`python3 demo.py --invented`** (currently running) uses an all-invented roster, for screenshots, slides and projecting. Test mode (`python3 testmode.py`, port 8767) sends real Gmail to the user's own inbox; needs `TEST_EMAIL` in `.env`.
- Pitch deck (3 min talk + 2 min demo), 9 slides, Claude artifact: https://claude.ai/artifact/FuVJSPZn9oxhPFBVRHxGvR . Slides: cover, why, who, success, how it works (Clay/Slack logos, icons), history-page screenshot, Slack screenshots, status, demo. The user edits it in the page as well.
81 tests pass. Nothing has been checked in a real browser except by the user.

Git: branch `handoff-2026-10-27`, `main` untouched.

## What we did
- Built the deck, then added screenshots (history page, Slack digest and draft) and redesigned "How it works" with logos and icons.
- Added `--invented` to the demo after the first screenshot exposed real contact data.
- Explained why "Email sent" appeared on the demo (simulated).

## What's next
1. Look at the whole deck in the browser: check slides 5, 6, 7 (image fit, equal card heights, logos) and fix anything off. Decide on one background everywhere or keep dark/light alternating.
2. Trim timing: the talk runs about 3:20; cut notes on "Who is this for" and "Where it stands", or merge slides 6 and 7.
3. Rehearse the demo: `python3 demo.py --invented`, click Slack alert, put a green check on a draft, see the thread reply within ~10 seconds. Re-run `demo.py --invented` right before presenting (live finds and approval offers work once per build).
4. Check `SLACK_BOT_TOKEN` in `.env`; if `logs/run.log` shows `missing_scope`, add `im:history` and reinstall.
5. Add Gmail settings and `TEST_EMAIL` to `.env`, run `python3 testmode.py` and test real sending (`digest.py --root <abs>/testmode --no-engine`, green check, `approvals.py --root <abs>/testmode`).
6. Make the page say "Demo only, nothing was sent" in demo mode instead of "Email sent".
7. Build the 10 PM Eastern scheduler (`digest.py` daily, `--late` on catch-up, keep `approvals.py --watch` alive) and the "no data at all" warning.
8. Fix the Clay export (re-add "Last Enriched", fill the blank email, confirm the odd LinkedIn URL, check other-company email domains). Open a pull request from `handoff-2026-10-27` into `main`.

## Open items and blockers
- Slack approval and its demo are untested live. Gmail is unconfigured.
- The user's first screenshot (real names, a real work address) exists in their files and this chat; keep it out of the deck.
- Earlier test messages and any new demo DMs sit in the user's Slack and can be deleted.
- Confirm the GitHub repo is private. README claims Python 3.9+ but only 3.11 was run. Confirm Clay's refresh cadence and credit cost.
- Never commit real contact names (`git grep` the names in `watchlist.json` first). Stray `.Rhistory` is untracked and not ours.
