"""Run the check, then send one Slack direct message with whatever changed since the last digest.

Reads:  logs/run.log, data/memory.json, watchlist.json, .env (SLACK_BOT_TOKEN, SLACK_USER_ID)
Writes: logs/run.log (a "Slack" line per send; the engine's lines when it runs)
Run:    python3 digest.py [--root DIR] [--clay FILE] [--no-engine] [--dry-run] [--late]

The digest covers every Job change / Possible move logged after the last digest that was actually
sent, so a failed send is picked up next time and nothing is reported twice.
"""
import argparse
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

import engine
import outreach
import slack
from common import slugify

ROOT = Path(__file__).parent
FIRST_DIGEST_DAYS = 7  # when no digest has ever been sent, look back this far
SENT_PREFIX = "Sent daily digest"


def parse_log(path):
    """Same line format as server.parse_log: time | person | source | decision | detail | link."""
    events = []
    try:
        lines = Path(path).read_text().splitlines()
    except OSError:
        return events
    for line in lines:
        parts = [p.strip() for p in line.split(" | ")]
        if len(parts) < 5:
            continue
        try:
            datetime.strptime(parts[0], "%Y-%m-%d %H:%M:%S")
        except ValueError:
            continue
        events.append({"time": parts[0], "person": parts[1], "source": parts[2], "decision": parts[3],
                       "detail": parts[4], "link": parts[5] if len(parts) > 5 else ""})
    return events


def collect(events, watchlist, memory, now):
    """Return (signals, notes) for the digest. Only watchlist people count."""
    last_sent = max((i for i, e in enumerate(events) if e["source"] == "Slack" and e["detail"].startswith(SENT_PREFIX)), default=None)
    if last_sent is None:
        cutoff = (now - timedelta(days=FIRST_DIGEST_DAYS)).strftime("%Y-%m-%d %H:%M:%S")
        window = [e for e in events if e["time"] >= cutoff]
    else:
        window = events[last_sent + 1:]

    companies = {slugify(w["name"]): w.get("company", "") for w in watchlist}
    watched = set(companies)
    signals = [
        {"name": e["person"], "decision": e["decision"], "detail": e["detail"], "link": e["link"],
         "company": memory.get(slugify(e["person"]), {}).get("company") or companies[slugify(e["person"])]}
        for e in window
        if e["decision"] in engine.SIGNALS and slugify(e["person"]) in watched
    ]

    # A person we couldn't check: their newest line is a Skipped/Error (a later good check clears it).
    notes = []
    newest = {}
    for e in window:
        if e["source"] == "Profile":
            newest[e["person"]] = e
    for w in watchlist:
        if newest.get(w["name"], {}).get("decision") in ("Skipped", "Error"):
            notes.append(f"Couldn't check {w['name']}'s profile today.")
    if any(e["person"] == "-" and e["source"] == "Run" and e["decision"] == "Error" for e in window):
        notes.append("Today's check couldn't run. See logs/run.log.")
    return signals, notes


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--root", default=str(ROOT), help="project folder holding watchlist.json, data/, logs/, .env")
    ap.add_argument("--clay", help="Clay rows file (default: <root>/data/clay_latest.csv or .json)")
    ap.add_argument("--no-engine", action="store_true", help="skip the check and summarize what is already logged")
    ap.add_argument("--dry-run", action="store_true", help="print the message instead of sending it")
    ap.add_argument("--late", action="store_true", help="label the message as a late summary")
    args = ap.parse_args()

    root = Path(args.root)
    log = engine.RunLog(root / "logs" / "run.log")
    if not args.no_engine:
        engine.run(root, args.clay or str(engine.default_clay_path(root)))  # failures are logged and show up as a note

    signals, notes = collect(
        parse_log(root / "logs" / "run.log"),
        engine.load_json(root / "watchlist.json", []),
        engine.load_json(root / "data" / "memory.json", {}),
        datetime.now(),
    )

    page_url = f"http://127.0.0.1:{os.environ.get('PORT', '8765')}"
    text, blocks = slack.build_digest(signals, notes, late=args.late, page_url=page_url)
    if args.dry_run:
        print(text)
        for b in blocks[1:]:
            print(b.get("text", {}).get("text") or b["elements"][0]["text"], end="\n\n")
        return

    jobs = sum(s["decision"] == "Job change" for s in signals)
    try:
        slack.post_message(outreach.load_config(root / ".env", ("SLACK_BOT_TOKEN", "SLACK_USER_ID")), text, blocks)
    except slack.SlackError as e:
        log.write("-", "Slack", "Error", f"Could not send daily digest: {e}")
        print(f"Could not send the digest: {e}", file=sys.stderr)
        sys.exit(1)
    log.write("-", "Slack", "Info", f"{SENT_PREFIX} ({jobs} job change{'s' if jobs != 1 else ''}, {len(signals) - jobs} possible, {len(notes)} note{'s' if len(notes) != 1 else ''})")
    print(f"Sent: {text}")


if __name__ == "__main__":
    main()
