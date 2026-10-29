"""Approve the outreach email from Slack by reacting with a green check.

Flow: digest.py calls offer() after the daily digest. For each person in it who has a valid email, it posts a
separate DM with the exact draft (To, Subject, body) and records it in data/approvals.json. process() then looks
for the user's green-check reaction on that DM and, only then, sends that exact text through Gmail (outreach.py)
and logs it like a send from the page. Nothing is sent without the reaction from SLACK_USER_ID.

Safety rules: the text sent is the text shown; the address is re-read from data/memory.json and must still match
the one shown; one email per signal (a Sent line in the log blocks a second); offers expire after 48 hours.
Editing is done on the history page, not here. Needs the reactions:read bot scope on top of chat:write.

Run:    python3 approvals.py [--root DIR] [--watch] [--interval SECONDS]
"""
import argparse
import json
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

import engine
import outreach
import slack
from common import slugify

ROOT = Path(__file__).parent
EXPIRES_AFTER = timedelta(hours=48)
MAX_SHOWN = 2500  # a Slack text block holds 3000 characters; never approve text that can't be shown whole
STAMP = "%Y-%m-%d %H:%M:%S"
SLACK_KEYS = ("SLACK_BOT_TOKEN", "SLACK_USER_ID")


def store_path(root):
    return Path(root) / "data" / "approvals.json"


def load(root):
    items = engine.load_json(store_path(root), [])
    return items if isinstance(items, list) else []


def save(root, items):
    path = store_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(items, indent=2))
    tmp.replace(path)


def offer_blocks(name, to, subject, body, demo=False):
    text = ("[Demo] " if demo else "") + f"Draft email to {name}"
    shown = f"*To:* {slack.esc(to)}\n*Subject:* {slack.esc(subject)}\n```{slack.esc(body)}```"
    hint = (":white_check_mark: Demo: a green check only logs a pretend send. No email is ever sent from the demo."
            if demo else
            ":white_check_mark: React with a green check to send this email exactly as shown. "
            "To change it, edit it on the history page instead. This offer expires in 48 hours.")
    return text, [
        {"type": "header", "text": {"type": "plain_text", "text": text}},
        {"type": "section", "text": {"type": "mrkdwn", "text": shown}},
        {"type": "context", "elements": [{"type": "mrkdwn", "text": hint}]},
    ]


def offer(root, cfg, signals, log, now=None, urlopen=None, demo=False, limit=None):
    """Post one draft DM per digest signal that can be emailed (at most `limit`). Returns how many were offered.
    demo=True marks the DMs and the stored offers so approving them can never send real mail."""
    root, now = Path(root), now or datetime.now()
    memory = engine.load_json(root / "data" / "memory.json", {})
    items = load(root)
    kwargs = {"urlopen": urlopen} if urlopen else {}
    offered = 0
    for s in signals:
        if limit is not None and offered >= limit:
            break
        name = s["name"]
        mem = memory.get(slugify(name), {})
        to = mem.get("email", "")
        if not outreach.valid_email(to):
            continue
        if any(i["name"] == name and i["signal_time"] == s["time"] for i in items):
            continue  # already offered for this signal
        draft = outreach.build_draft(name, s["decision"], mem.get("title", ""), mem.get("company", ""), cfg.get("SENDER_NAME", ""))
        problem = outreach.check_message(draft["subject"], draft["body"])
        if not problem and len(draft["body"]) > MAX_SHOWN:
            problem = "The draft is too long to show in Slack."
        if problem:
            log.write(name, "Slack", "Info", f"Did not offer a Slack email draft: {problem}")
            continue
        text, blocks = offer_blocks(name, to, draft["subject"], draft["body"], demo)
        try:
            reply = slack.post_message(cfg, text, blocks, **kwargs)
        except slack.SlackError as e:
            log.write(name, "Slack", "Error", f"Could not post the email draft: {e}")
            continue
        items.append({"name": name, "to": to, "subject": draft["subject"], "body": draft["body"],
                      "signal_time": s["time"], "channel": reply.get("channel", ""), "ts": reply.get("ts", ""),
                      "created": now.strftime(STAMP), "state": "pending", "demo": demo})
        save(root, items)  # saved per message so a crash never loses an offer that is already in Slack
        log.write(name, "Slack", "Info", f'Offered the email draft "{draft["subject"]}" for approval in Slack')
        offered += 1
    return offered


def already_emailed(events, name, since):
    return any(e["person"] == name and e["source"] == "Email" and e["detail"].startswith("Sent ") and e["time"] >= since
               for e in events)


def process(root, cfg, log, now=None, urlopen=None, smtp_factory=None, parse_log=None, demo=False):
    """Check every pending offer for the user's green check and send the approved ones. Returns how many were sent.
    Demo offers (or demo=True) log a pretend send and never touch Gmail."""
    import digest  # local import: digest imports this module
    root, now = Path(root), now or datetime.now()
    items = load(root)
    if not any(i["state"] == "pending" for i in items):
        return 0
    memory = engine.load_json(root / "data" / "memory.json", {})
    events = (parse_log or digest.parse_log)(root / "logs" / "run.log")
    slack_kw = {"urlopen": urlopen} if urlopen else {}
    mail_kw = {"smtp_factory": smtp_factory} if smtp_factory else {}
    sent = 0

    def reply(item, text):
        try:
            slack.post_message(cfg, text, None, channel=item["channel"], thread_ts=item["ts"], **slack_kw)
        except slack.SlackError:
            pass  # the log below is the record; a missing thread reply is not worth failing over

    for item in items:
        if item["state"] != "pending":
            continue
        name = item["name"]
        if now - datetime.strptime(item["created"], STAMP) > EXPIRES_AFTER:
            item["state"] = "expired"
            log.write(name, "Slack", "Info", f'The email draft "{item["subject"]}" expired without approval')
            continue
        try:
            if not slack.approved_by_user(cfg, item["channel"], item["ts"], **slack_kw):
                continue
        except slack.SlackError as e:
            log.write(name, "Slack", "Error", f"Could not check for approval: {e}")
            continue
        # Approved. Final checks before anything leaves the building.
        if already_emailed(events, name, item["signal_time"]):
            item["state"] = "skipped"
            log.write(name, "Slack", "Info", "Approved in Slack, but an email for this move was already sent. Nothing sent.")
            reply(item, "An email for this move was already sent. Nothing sent.")
            continue
        current = memory.get(slugify(name), {}).get("email", "")
        if current != item["to"]:
            item["state"] = "skipped"
            log.write(name, "Slack", "Error", "Approved in Slack, but the saved email address changed since the draft. Nothing sent.")
            reply(item, "The saved email address changed since this draft. Nothing sent. Use the history page.")
            continue
        pretend = demo or item.get("demo")
        try:
            if not pretend:
                outreach.send_email(cfg, item["to"], item["subject"], item["body"], **mail_kw)
        except ValueError as e:
            item["state"] = "failed"
            log.write(name, "Email", "Error", f"Could not send to {item['to']}: {e}")
            reply(item, f"Not sent: {e}")
            continue
        except Exception as e:  # SMTP and network failures
            item["state"] = "failed"
            log.write(name, "Email", "Error", f"Could not send to {item['to']}: {type(e).__name__}")
            reply(item, "Gmail refused or couldn't be reached. Nothing was sent. Use the history page to retry.")
            continue
        item["state"] = "sent"
        sent += 1
        log.write(name, "Email", "Info", f'Sent "{item["subject"]}" to {item["to"]} (approved in Slack)'
                  + (" (demo, not actually sent)" if pretend else ""))
        reply(item, "Demo: approved, but nothing was actually sent." if pretend else f"Sent to {item['to']}.")
    save(root, items)
    return sent


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--root", default=str(ROOT), help="project folder holding data/, logs/, .env")
    ap.add_argument("--watch", action="store_true", help="keep checking until stopped (Ctrl-C)")
    ap.add_argument("--interval", type=int, default=30, help="seconds between checks with --watch")
    args = ap.parse_args()

    root = Path(args.root)
    log = engine.RunLog(root / "logs" / "run.log")
    cfg = outreach.load_config(root / ".env", outreach.CONFIG_KEYS + SLACK_KEYS)
    while True:
        n = process(root, cfg, log)
        if n:
            print(f"Sent {n} approved email{'s' if n != 1 else ''}.")
        if not args.watch:
            return
        try:
            time.sleep(max(args.interval, 10))
        except KeyboardInterrupt:
            return


if __name__ == "__main__":
    sys.exit(main())
