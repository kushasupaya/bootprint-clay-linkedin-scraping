# Decisions

## 2026-10-26

- **Build one feature at a time: history website first, then Clay, then Slack.** The user chose this order. Not chosen: starting with the Clay or posts path, because the page and log format are the foundation both reuse.
- **Log line format is the contract between pipeline and page:** `time | person | source | decision | what happened | link`. Chosen because it is human-readable (plan requirement) and lets the page group by person. Not chosen: JSON logs, which a non-technical user can't read.
- **Page stack: Python standard-library server plus plain HTML/CSS/JS, no build step.** Chosen for zero install and a read-only surface (405 on writes). Not chosen: a framework, which adds dependencies for a five-person page.
- **Visual direction: cool slate palette, Schibsted Grotesk, roster plus per-person timeline, 14-day activity strip.** Avoids the cream/terracotta and dark/neon defaults. User approved.
- **Watchlist stays hand-edited, not fed from Clay; joined to Clay by LinkedIn URL.** This keeps the roster intact if Clay is down or returns blank data and stops stray Clay rows from creating alerts. Not chosen: Clay as the roster (simpler, but loses those safeguards) or an add-person form (would break read-only).
- **Clay delivery: leaning to a Google Sheet that the laptop reads, else a small always-on mailbox the laptop pulls from. Not final.** Clay cannot reach a sleeping laptop, so a direct webhook or tunnel is rejected. Open until the user confirms their Clay setup.

## 2026-10-26 (later)

- **Posts path (Gmail bell emails, post labeling) is parked; version 1 detects job changes through Clay only.** The user checked and LinkedIn has no email option for these notifications (job-change notifications are in-app and push only). Not chosen: reading phone pushes or scraping LinkedIn, because code can't read pushes reliably and scraping risks the user's account and breaks LinkedIn's terms. Revisit only if Clay can return post text. This supersedes the posts-path plan in `plan.md` (note added there).
- **Clay data reaches the engine through the Google Sheet Clay fills; the laptop will read the sheet directly later.** For now the user downloads a CSV to `data/clay_latest.csv`. Preferred live access is a read-only Google service account; "publish to web" is a stopgap only, because the link exposes candidate names to anyone who has it.
- **The Clay timestamp column ("Last Enriched") is first-class.** Per person the newest row wins, rows older than 48 hours are Skipped (so a stalled Clay refresh never looks like "no change"), and the timestamp is shown in every log line, in memory (`data_as_of`) and on the page. Not chosen: ignoring timestamps, which hides stale data.
- **Title and org are cleaned inside the engine, not in the CSV.** Titles lose a trailing "at Employer"; orgs lose a trailing "(branch)" and ", City" or ", ST". Both incoming and saved values are cleaned before comparing, so old memory causes no false alarms and heals to the clean value. Legal suffixes and "&" names are kept. Not chosen: editing the CSV (Clay overwrites it every refresh). Tradeoff: a move between branches of one company is not reported.
- **Real data replaced the sample data.** The made-up watchlist, memory and log were archived in `sample/`; `watchlist.json` now holds the five people from the user's sheet and the baseline run is saved. `sample/clay_latest.json` is test input only.
- **The CSV timestamps are currently random (demo only).** The original export is kept at `data/clay_latest.original.csv`. Replace with a real export before trusting any result.

## 2026-10-26 (design pass and refresh button)

- **Light-only vivid design; dark mode removed.** The user found dark mode too much. Electric-blue header band and accents, colored initials avatars; the violet Possible move and red Skipped/stale colors were kept at the user's request.
- **Repeated routine checks collapse into one row per day.** Consecutive No change, Skipped, Error or Ignored entries become "No change (4 checks)" with a toggle to expand; signals are never collapsed. Chosen over hiding routine checks or deleting log lines, so the full log stays intact (plan: log every decision). This is done on the page only.
- **The page is no longer purely read-only: a "Check for updates" button runs the engine on demand** (Clay sometimes updates before the 10 PM run). This supersedes the earlier read-only-page decision. Guardrails: one endpoint (`POST /api/refresh`), localhost only, rejects wrong host/origin or a missing custom header so another website can't trigger it, one run at a time, runs are labeled "manual refresh" in the log. Not chosen: a separate CLI-only refresh, which the user didn't want. For now the button re-reads `data/clay_latest.csv`; it will fetch the Google Sheet once that is connected.
- **Moved `slugify` to `common.py`** so `server.py` can import `engine.py` without a circular import.

## 2026-10-26 (git)

- **Real contact names and employers are kept out of git, including docs and tests.** Docs refer to "one person" and tests use made-up companies; `watchlist.json`, `data/` and `logs/` are gitignored, while `sample/` (made-up) is committed. Chosen because the repo may be visible to others and the plan says candidate data stays local. Not chosen: relying on `.gitignore` alone, since names had leaked into the handoff docs and tests.
