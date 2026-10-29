"""Run the check, then send one Slack direct message with whatever changed since the last digest.

Reads:  logs/run.log, data/memory.json, watchlist.json, .env (SLACK_BOT_TOKEN, SLACK_USER_ID)
Writes: logs/run.log (a "Slack" line per send; the engine's lines when it runs)
Run:    python3 digest.py [--root DIR] [--clay FILE] [--no-engine] [--dry-run] [--late]

The digest covers every Job change / Possible move logged after the last digest that was actually
sent, so a failed send is picked up next time and nothing is reported twice. Anything logged more than
48 hours ago is left out of the message (stale news is not an alert); it stays in the log and on the
page with its tier, and the omission is logged.
"""
import argparse
import os
import sys
from collections import namedtuple
from datetime import datetime
from pathlib import Path

import engine
import outreach
import slack
from common import slugify

ROOT = Path(__file__).parent
MAX_AGE = engine.STALE_AFTER  # same 48-hour freshness rule the engine applies to Clay data
SENT_PREFIX = "Sent daily digest"
Digest = namedtuple("Digest", "signals notes text blocks left_out")


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
    """Return (signals, notes, left_out) for the digest. Only watchlist people count.

    Only events from the last 48 hours are used. left_out names the people whose Job change / Possible move
    was logged since the last sent digest but is too old to alert on (it stays on the page with its tier)."""
    last_sent = max((i for i, e in enumerate(events) if e["source"] == "Slack" and e["detail"].startswith(SENT_PREFIX)), default=None)
    unreported = events if last_sent is None else events[last_sent + 1:]
    cutoff = (now - MAX_AGE).strftime("%Y-%m-%d %H:%M:%S")
    window = [e for e in unreported if e["time"] >= cutoff]

    companies = {slugify(w["name"]): w.get("company", "") for w in watchlist}
    watched = set(companies)
    left_out = list(dict.fromkeys(
        e["person"] for e in unreported
        if e["time"] < cutoff and e["decision"] in engine.SIGNALS and slugify(e["person"]) in watched
    ))
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
    return signals, notes, left_out


def compose(root, now, late=False, page_url="", demo=False):
    """Read the log under root and build the digest. Returns a Digest(signals, notes, text, blocks, left_out)."""
    root = Path(root)
    signals, notes, left_out = collect(
        parse_log(root / "logs" / "run.log"),
        engine.load_json(root / "watchlist.json", []),
        engine.load_json(root / "data" / "memory.json", {}),
        now,
    )
    text, blocks = slack.build_digest(signals, notes, late=late, page_url=page_url, demo=demo)
    return Digest(signals, notes, text, blocks, left_out)


def left_out_line(left_out):
    """The log detail recording who was kept out of a digest for being older than 48 hours."""
    n = len(left_out)
    return f"Left {n} change{'s' if n != 1 else ''} out of the digest (older than 48 hours, still on the page): {', '.join(left_out)}"


def sent_line(signals, notes):
    """The log detail that marks a digest as sent (collect() looks for SENT_PREFIX)."""
    jobs = sum(s["decision"] == "Job change" for s in signals)
    return f"{SENT_PREFIX} ({jobs} job change{'s' if jobs != 1 else ''}, {len(signals) - jobs} possible, {len(notes)} note{'s' if len(notes) != 1 else ''})"


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

    page_url = f"http://127.0.0.1:{os.environ.get('PORT', '8765')}"
    result = compose(root, datetime.now(), late=args.late, page_url=page_url)
    signals, notes, text, blocks = result.signals, result.notes, result.text, result.blocks
    if args.dry_run:
        print(text)
        for b in blocks[1:]:
            print(b.get("text", {}).get("text") or b["elements"][0]["text"], end="\n\n")
        if result.left_out:
            print(left_out_line(result.left_out))
        return

    try:
        slack.post_message(outreach.load_config(root / ".env", ("SLACK_BOT_TOKEN", "SLACK_USER_ID")), text, blocks)
    except slack.SlackError as e:
        log.write("-", "Slack", "Error", f"Could not send daily digest: {e}")
        print(f"Could not send the digest: {e}", file=sys.stderr)
        sys.exit(1)
    log.write("-", "Slack", "Info", sent_line(signals, notes))
    if result.left_out:
        log.write("-", "Slack", "Info", left_out_line(result.left_out))
    print(f"Sent: {text}")


if __name__ == "__main__":
    main()
