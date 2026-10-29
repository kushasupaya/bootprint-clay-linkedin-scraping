# LinkedIn Job-Change Watchlist

A personal tool for recruiters. It watches a short list of people (about five to start) and tells you when one of them changes jobs, so you can reach out while the timing is right.

Every day it compares each person's current company and job title, supplied by [Clay](https://www.clay.com), with what it saved last time. A company change is a **Job change**. A title change at the same company is a **Possible move**. A local web page shows the full history for each person, including why each decision was made.

## Status

| Part | State |
| --- | --- |
| Comparison engine (`engine.py`) | Working, reads a Clay CSV export |
| History page with "Check for updates" button | Working |
| Demo mode with made-up job changes and simulate buttons (`python3 demo.py`) | Working |
| Test mode: 4 invented candidates, real emails to your own inbox (`python3 testmode.py`) | Working, needs `.env` |
| Candidate brief and A/B/C priority tier on the page | Working |
| Outreach email from the page (you review, edit and click Send; Gmail SMTP) | Working, needs an Email column in Clay and `.env` |
| Outreach approval in Slack (react with a green check; `python3 approvals.py --watch`) | Built, untested against real Slack and Gmail; needs the `reactions:read` scope |
| Reading the Google Sheet live | Not built |
| Slack daily summary | Built, untested against real Slack (`python3 digest.py`; needs a Slack app token in `.env`) |
| 10 PM Eastern scheduler | Not built |
| LinkedIn post announcements | Parked. LinkedIn has no email option for these notifications, so job changes come from Clay only. |

The full spec is in [`plan.md`](plan.md), and the flow is in [`diagram.html`](diagram.html). Open the diagram in a browser.

## How it decides

- **Company changed:** Job change. "Acme" and "Acme, Inc." count as the same company.
- **Title changed, same company:** Possible move.
- **Blank, missing, errored, or older than 48 hours:** skipped and logged. It is never treated as a change.
- **First run:** saves a starting point and reports nothing.
- **Reported once:** a change is not repeated on later runs.
- **Cleaning:** a trailing employer in a title ("Surgeon at Acme") and a trailing branch or city in a company ("Acme, Austin") are dropped before comparing.

## Setup

You need Python 3.9 or later. There is nothing to install.

1. Create `watchlist.json` in the project folder (see the example below).
2. Export your Clay table as a CSV to `data/clay_latest.csv`.
3. Run the engine to save a starting point:

   ```
   python3 engine.py
   ```

4. Start the history page and open http://127.0.0.1:8765:

   ```
   python3 server.py
   ```

`watchlist.json` lists who to watch, and is edited by hand:

```json
[
  {"name": "Jane Doe", "company": "Example Co", "linkedin_url": "https://www.linkedin.com/in/jane-doe"}
]
```

The CSV needs a column for each of full name, current company, job title, LinkedIn URL and a "last enriched" timestamp. Common header names such as "Full Name", "Current Org", "Current Title", "LinkedIn" and "Last Enriched" are recognized. People are matched to Clay rows by LinkedIn URL.

## Using it

- **Refresh:** replace `data/clay_latest.csv` with a new export and click **Check for updates** on the page, or run `python3 engine.py`.
- **Try it with made-up data:** `python3 engine.py --root <folder> --clay sample/clay_latest.json`, using a copy of the project so your real files are untouched. The files in `sample/` are fictional.
- **Tests:** `python3 -I -m unittest discover -s tests -v`

## How it fits together

```
Clay export (CSV) ──> engine.py ──> logs/run.log   (one line per decision, with the reason)
                          │
watchlist.json ───────────┤
                          └──────> data/memory.json (last-known title and company)

logs/run.log + data/memory.json ──> server.py ──> web/ (history page)
```

`logs/run.log` is the source of truth. Its format is `time | person | source | decision | what happened | link`. The page groups lines by person, so every line about a person must carry their exact name.

## Privacy

The tool only reads data and shows it on your own laptop. The server listens on `127.0.0.1` only. The one write action, the refresh button, accepts requests only from the page itself and runs one refresh at a time.

`watchlist.json`, `data/` and `logs/` hold real people and are excluded from git. Keep real names and employers out of anything you commit.
