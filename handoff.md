Last updated: 2026-10-28

## Where we are
Version 1 runs locally. `python3 server.py` serves the history page at http://127.0.0.1:8765 for the user's ten real contacts (from `data/clay_latest.csv`; no signals yet). Built:
- Clay comparison engine, history page with "Check for updates", A/B/C briefs, outreach email from the page (Gmail SMTP, `outreach.py`). **No real email has ever been sent: `.env` has Slack keys but the three Gmail keys are empty.**
- Slack daily digest (`python3 digest.py`), 48-hour rule, verified with a real test DM. Nothing runs it automatically.
- **New: Slack approval of outreach** (`approvals.py`). After the digest, one draft-email DM per signal with a valid email; the user's green-check reaction sends that exact draft through Gmail. Run `python3 approvals.py --watch` for it to notice. Needs `reactions:read` on the Slack app (added and app reinstalled; token not yet compared with `.env`). Unit-tested only, never run against live Slack.
- Demo mode (`python3 demo.py`, port 8766, currently running, freshly rebuilt): the "Slack alert" send also posts up to two "[Demo] Draft email" DMs; a green check only logs a pretend send within ~10 seconds. Test mode (`python3 testmode.py`, port 8767) for real Gmail to the user's own inbox.
- Slide deck for the 3-minute talk + 2-minute demo (7 slides, up to date with Slack approval): https://claude.ai/artifact/FuVJSPZn9oxhPFBVRHxGvR
81 tests pass. Pages verified with jsdom and curl only.

Git: branch `handoff-2026-10-27`, `main` untouched.

## What we did
- Built the pitch deck and kept it in step with the app.
- Built Slack ✅ approval of outreach, plus its demo version and 17 tests.
- Explained why "Email sent" appeared earlier (demo Send is simulated).

## What's next
1. Rehearse the demo path once for real: `python3 demo.py`, click Slack alert, put ✅ on a draft, see the thread reply. Re-run `python3 demo.py` right before presenting (live finds work once per build).
2. Check `SLACK_BOT_TOKEN` in `.env` matches Slack's OAuth page; if `logs/run.log` shows `missing_scope`, add `im:history` and reinstall.
3. Add Gmail settings to `.env` (see `.env.example`), set `TEST_EMAIL`, run `python3 testmode.py`, and test the full flow (`digest.py --root <abs>/testmode --no-engine`, ✅, `approvals.py --root <abs>/testmode`).
4. Make the page say "Demo only, nothing was sent" in demo mode instead of "Email sent".
5. Build the 10 PM Eastern scheduler: `digest.py` daily (`--late` on catch-up) plus keep `approvals.py --watch` alive; add the "no data at all" warning.
6. Fix the Clay export: re-add "Last Enriched", fill the one blank email, confirm the LinkedIn URL whose slug doesn't match, check emails using another company's domain.
7. Open a pull request from `handoff-2026-10-27` into `main`; decide on deleting `handoff-2026-10-26`.
8. Later: read the Google Sheet directly; tune tiers from real logs.

## Open items and blockers
- Slack approval and its demo are untested live. Gmail is unconfigured.
- User must confirm the GitHub repo is private. README claims Python 3.9+ but only 3.11 was run.
- Test messages from earlier sessions sit in the user's Slack DM and can be deleted; testing approval will add more.
- Confirm Clay re-enriches daily, its credit cost, and whether it adds or updates rows.
- Never commit real contact names (`git grep` the names in `watchlist.json` first). Stray `.Rhistory` is untracked and not ours.
