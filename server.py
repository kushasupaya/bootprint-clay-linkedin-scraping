"""Local history page for the LinkedIn job-change watchlist.

Reads watchlist.json, data/memory.json and logs/run.log. It has two writes, both limited to this page
on this laptop: POST /api/refresh runs the engine once (same as `python3 engine.py`), and
POST /api/outreach/send sends the outreach email the user reviewed and approved on the page.
Run: python3 server.py   then open http://127.0.0.1:8765
"""
import csv
import json
import os
import random
import threading
from datetime import date, datetime, timedelta
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import approvals
import digest
import engine
import outreach
import slack
from brief import build_brief
from common import slugify

ROOT = Path(os.environ.get("WATCHLIST_ROOT") or Path(__file__).parent).resolve()
WEB = Path(__file__).parent / "web"
# Demo mode (python3 demo.py): fake data in its own folder, and Send only pretends so no real person is emailed.
DEMO = bool(os.environ.get("WATCHLIST_DEMO"))
# Test mode (python3 testmode.py): invented candidates whose addresses all land in the user's own inbox; Send is real.
TEST = bool(os.environ.get("WATCHLIST_TEST"))
BANNER = (
    "Demo data: made-up job changes. Sending an email here is only simulated; nobody is contacted." if DEMO
    else "Test mode: invented candidates. Emails really send, but every address is your own inbox." if TEST
    else ""
)
HOST, PORT = "127.0.0.1", int(os.environ.get("PORT", 8765))
ALLOWED_HOSTS = {f"127.0.0.1:{PORT}", f"localhost:{PORT}"}
REFRESH_LOCK = threading.Lock()
SEND_LOCK = threading.Lock()
SLACK_LOCK = threading.Lock()
SLACK_KEYS = ("SLACK_BOT_TOKEN", "SLACK_USER_ID")
MAX_REQUEST = 20000
TIER_ORDER = {"A": 0, "B": 1, "C": 2}
DEMO_COMPANIES = ["Summit Veterinary Partners", "Bluewater Animal Specialists", "Redwood Pet Health", "Keystone Veterinary Group", "Harborview Animal Hospital"]
DEMO_TITLES = ["Senior Veterinary Surgeon", "Head of Surgery", "Director of Surgical Services", "Chief Medical Officer", "Lead Surgeon"]
STRIP_DAYS = 14
# Strongest decision wins when summarising a day.
RANK = {"Job change": 4, "Possible move": 3, "Error": 2, "Skipped": 2, "Ignored": 1, "No change": 1}


def load_json(path, default):
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return default


def parse_log():
    """Log line: time | person | source | decision | detail | link (optional)."""
    events = []
    try:
        lines = (ROOT / "logs" / "run.log").read_text().splitlines()
    except OSError:
        return events
    for line in lines:
        if not line.strip() or line.startswith("#"):
            continue
        parts = [p.strip() for p in line.split(" | ")]
        if len(parts) < 5:
            continue
        try:
            datetime.strptime(parts[0], "%Y-%m-%d %H:%M:%S")
        except ValueError:
            continue
        events.append({
            "time": parts[0],
            "person": parts[1],
            "source": parts[2],
            "decision": parts[3],
            "detail": parts[4],
            "link": parts[5] if len(parts) > 5 else "",
        })
    return events


def sent_after(events, since):
    """Time of the first 'Sent' email logged at or after the signal, else None."""
    for e in sorted(events, key=lambda e: e["time"]):
        if e["source"] == "Email" and e["detail"].startswith("Sent ") and e["time"] >= since:
            return e["time"]
    return None


def outreach_info(name, mem, signal, events, cfg):
    """What the page needs to offer an outreach email. None when the person has no signal."""
    if not signal:
        return None
    email = mem.get("email", "")
    draft = outreach.build_draft(name, signal["decision"], mem.get("title", ""), mem.get("company", ""), cfg.get("SENDER_NAME", ""))
    return {
        "to": email if outreach.valid_email(email) else "",
        "sent_at": sent_after(events, signal["time"]),
        "can_send": DEMO or bool(cfg.get("GMAIL_ADDRESS") and cfg.get("GMAIL_APP_PASSWORD")),
        **draft,
    }


def build_data():
    watchlist = load_json(ROOT / "watchlist.json", [])
    memory = load_json(ROOT / "data" / "memory.json", {})
    events = parse_log()
    today = date.today()
    days = [(today - timedelta(days=i)).isoformat() for i in range(STRIP_DAYS - 1, -1, -1)]

    cfg = outreach.load_config(ROOT / ".env")
    people = []
    for w in watchlist:
        slug = slugify(w["name"])
        mem = memory.get(slug, {})
        mine = sorted((e for e in events if e["person"] == w["name"]), key=lambda e: e["time"], reverse=True)
        by_day = {}
        for e in mine:
            d = e["time"][:10]
            if RANK.get(e["decision"], 0) > RANK.get(by_day.get(d), 0):
                by_day[d] = e["decision"]
        signals = [e for e in mine if e["decision"] in ("Job change", "Possible move")]
        info = outreach_info(w["name"], mem, signals[0] if signals else None, mine, cfg)
        people.append({
            "slug": slug,
            "name": w["name"],
            "linkedin_url": w.get("linkedin_url", ""),
            "title": mem.get("title", ""),
            "company": mem.get("company", w.get("company", "")),
            "last_checked": mem.get("last_checked", ""),
            "data_as_of": mem.get("data_as_of", ""),
            "latest_signal": signals[0] if signals else None,
            "outreach": info,
            "brief": build_brief(w["name"], mem, signals[0] if signals else None, datetime.now(), w.get("tier", ""), info and info["sent_at"]),
            "strip": [{"day": d, "decision": by_day.get(d)} for d in days],
            "events": mine,
        })

    # Tier A first; within a tier, people not yet emailed come before those already emailed. Unflagged keep list order.
    people.sort(key=lambda p: (
        TIER_ORDER.get(p["brief"]["tier"], 9) if p["brief"] else 9,
        bool(p["outreach"] and p["outreach"]["sent_at"]),
    ))

    runs = [e for e in events if e["source"] == "Run" and e["detail"].startswith("Run finished")]
    return {
        "people": people,
        "last_run": runs[-1]["time"] if runs else "",
        "today": today.isoformat(),
        "demo": DEMO,
        "banner": BANNER,
    }


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(WEB), **kwargs)

    def do_GET(self):
        if DEMO and self.path.split("?")[0] == "/api/demo/slack":
            self.demo_slack_preview()
            return
        if self.path.split("?")[0] == "/api/data":
            body = json.dumps(build_data()).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)
            return
        super().do_GET()

    def send_json(self, status, payload):
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def same_page_only(self):
        """Only this page may trigger a write: right host, same-origin, and a custom header
        (which a website in another tab cannot add without our permission)."""
        origin = self.headers.get("Origin")
        if (
            self.headers.get("Host") not in ALLOWED_HOSTS
            or (origin and origin.split("://", 1)[-1] not in ALLOWED_HOSTS)
            or self.headers.get("X-Requested-With") != "watchlist-page"
        ):
            self.send_json(403, {"ok": False, "error": "This action is only allowed from the page itself."})
            return False
        return True

    def do_POST(self):
        path = self.path.split("?")[0]
        allowed = ("/api/refresh", "/api/outreach/send") + (("/api/demo/simulate", "/api/demo/reset", "/api/demo/slack") if DEMO else ())
        if path not in allowed:
            self.send_error(405, "Not allowed")
            return
        if not self.same_page_only():
            return
        if path == "/api/demo/slack":
            self.demo_slack_send()
            return
        if path.startswith("/api/demo/"):
            self.demo_action(path)
            return
        if path == "/api/outreach/send":
            self.send_outreach()
            return
        if not REFRESH_LOCK.acquire(blocking=False):
            self.send_json(409, {"ok": False, "error": "A refresh is already running. Try again in a moment."})
            return
        try:
            result = engine.run(ROOT, engine.default_clay_path(ROOT), trigger="manual")
        finally:
            REFRESH_LOCK.release()
        if result is None:
            self.send_json(500, {"ok": False, "error": "Couldn't read the Clay data. See logs/run.log for the reason."})
            return
        self.send_json(200, {
            "ok": True,
            "flagged": [{"name": n, "decision": d, "detail": det} for n, d, det, _ in result["flagged"]],
            "notes": result["notes"],
        })

    def demo_slack_message(self):
        """What the Slack digest would say right now, built from the demo log. Marked [Demo] so it is easy to spot."""
        return digest.compose(ROOT, datetime.now(), page_url=f"http://{HOST}:{PORT}", demo=True)

    def demo_slack_preview(self):
        """Demo mode only, read-only: the message the digest would send, for the page to draw."""
        msg = self.demo_slack_message()
        cfg = outreach.load_config(ROOT / ".env", SLACK_KEYS)
        self.send_json(200, {"text": msg.text, "blocks": msg.blocks, "signals": len(msg.signals), "notes": len(msg.notes),
                             "left_out": len(msg.left_out),
                             "can_send": bool(cfg.get("SLACK_BOT_TOKEN") and cfg.get("SLACK_USER_ID"))})

    def demo_slack_send(self):
        """Demo mode only: really DM the demo digest to the user's own Slack (SLACK_USER_ID from .env, never from the request)."""
        if not SLACK_LOCK.acquire(blocking=False):
            self.send_json(409, {"ok": False, "error": "A Slack message is already being sent. Try again in a moment."})
            return
        try:
            msg = self.demo_slack_message()
            log = engine.RunLog(ROOT / "logs" / "run.log")
            try:
                slack.post_message(outreach.load_config(ROOT / ".env", SLACK_KEYS), msg.text, msg.blocks)
            except slack.SlackError as e:
                log.write("-", "Slack", "Error", f"Could not send daily digest: {e}")
                self.send_json(502, {"ok": False, "error": str(e)})
                return
            log.write("-", "Slack", "Info", digest.sent_line(msg.signals, msg.notes) + " (demo)")
            if msg.left_out:
                log.write("-", "Slack", "Info", digest.left_out_line(msg.left_out))
            # Two demo draft DMs to approve with a green check; approving only logs a pretend send (see demo.py).
            cfg = outreach.load_config(ROOT / ".env", SLACK_KEYS + ("SENDER_NAME",))
            offered = approvals.offer(ROOT, cfg, msg.signals, log, demo=True, limit=2)
            self.send_json(200, {"ok": True, "text": msg.text, "drafts": offered})
        finally:
            SLACK_LOCK.release()

    def demo_action(self, path):
        """Demo mode only: fake a new move for someone (so the presenter can show the page react), or reset the demo."""
        if not REFRESH_LOCK.acquire(blocking=False):
            self.send_json(409, {"ok": False, "error": "A refresh is already running. Try again in a moment."})
            return
        try:
            if path == "/api/demo/reset":
                import demo
                demo.build()
                self.send_json(200, {"ok": True})
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                req = json.loads(self.rfile.read(length))
                slug, kind = req["slug"], req["kind"]
                assert kind in ("job", "title")
            except (ValueError, KeyError, TypeError, AssertionError):
                self.send_json(400, {"ok": False, "error": "The request was malformed."})
                return
            watchlist = load_json(ROOT / "watchlist.json", [])
            person = next((w for w in watchlist if slugify(w["name"]) == slug), None)
            memory_path = ROOT / "data" / "memory.json"
            memory = load_json(memory_path, {})
            mem = memory.get(slug)
            if not person or not mem:
                self.send_json(404, {"ok": False, "error": "Unknown person."})
                return
            now = datetime.now()
            note = f" (Clay data from {now:%b %d, %H:%M})"
            old_co, old_ti = mem.get("company", ""), mem.get("title", "")
            if kind == "job":
                new_co = random.choice([c for c in DEMO_COMPANIES if engine.normalize_company(c) != engine.normalize_company(old_co)])
                decision, new_ti = "Job change", old_ti
                detail = f"Company changed from {old_co} to {new_co}." + (f" Title is now {new_ti}." if new_ti else "") + note
            else:
                new_co = old_co
                new_ti = random.choice([t for t in DEMO_TITLES if engine.normalize_title(t) != engine.normalize_title(old_ti)])
                decision = "Possible move"
                detail = f"Title changed from {old_ti} to {new_ti}. Same company.{note}"
            log = engine.RunLog(ROOT / "logs" / "run.log")
            log.write("-", "Run", "Info", "Run started (manual refresh)")
            log.write(person["name"], "Profile", decision, detail, person.get("linkedin_url", ""))
            log.write("-", "Run", "Info", "Run finished")
            memory[slug] = {**mem, "title": new_ti, "company": new_co, "last_checked": now.strftime("%Y-%m-%d %H:%M")}
            engine.save_json_atomic(memory_path, memory)
            # Keep the demo's Clay file in step, or the next "Check for updates" would see a change back.
            clay_path = ROOT / "data" / "clay_latest.csv"
            with clay_path.open(newline="") as f:
                reader = csv.DictReader(f)
                fields, rows = reader.fieldnames, list(reader)
            for r in rows:
                if r.get("Full Name") == person["name"]:
                    r["Current Org"], r["Current Title"] = new_co, new_ti
            with clay_path.open("w", newline="") as f:
                w = csv.DictWriter(f, fieldnames=fields)
                w.writeheader()
                w.writerows(rows)
            self.send_json(200, {"ok": True, "name": person["name"], "decision": decision})
        finally:
            REFRESH_LOCK.release()

    def send_outreach(self):
        """Send the email the user approved. The address comes from memory.json, never from the request."""
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= MAX_REQUEST:
                raise ValueError
            req = json.loads(self.rfile.read(length))
            slug, subject, body = req["slug"], req["subject"], req["body"]
            if not all(isinstance(x, str) for x in (slug, subject, body)):
                raise ValueError
        except (ValueError, KeyError, TypeError):
            self.send_json(400, {"ok": False, "error": "The request was malformed."})
            return
        person = next((p for p in build_data()["people"] if p["slug"] == slug), None)
        info = person and person["outreach"]
        if not info:
            self.send_json(404, {"ok": False, "error": "No job-change or possible-move signal for this person."})
            return
        if not info["to"]:
            self.send_json(400, {"ok": False, "error": "No valid email address from Clay for this person."})
            return
        problem = outreach.check_message(subject, body)
        if problem:
            self.send_json(400, {"ok": False, "error": problem})
            return
        if not SEND_LOCK.acquire(blocking=False):
            self.send_json(409, {"ok": False, "error": "An email is already being sent. Try again in a moment."})
            return
        log = engine.RunLog(ROOT / "logs" / "run.log")
        try:
            # Re-check under the lock so a double click cannot send twice.
            fresh = next(p for p in build_data()["people"] if p["slug"] == slug)["outreach"]
            if fresh["sent_at"]:
                self.send_json(409, {"ok": False, "error": f"Already emailed at {fresh['sent_at']}."})
                return
            try:
                if not DEMO:
                    outreach.send_email(outreach.load_config(ROOT / ".env"), info["to"], subject, body)
            except ValueError as e:
                self.send_json(400, {"ok": False, "error": str(e)})
                return
            except Exception as e:  # SMTP and network failures
                log.write(person["name"], "Email", "Error", f"Could not send to {info['to']}: {type(e).__name__}")
                self.send_json(502, {"ok": False, "error": "Gmail refused or couldn't be reached. Nothing was sent. See logs/run.log."})
                return
            log.write(person["name"], "Email", "Info", f'Sent "{subject}" to {info["to"]}' + (" (demo, not actually sent)" if DEMO else ""))
        finally:
            SEND_LOCK.release()
        self.send_json(200, {"ok": True})

    do_PUT = do_DELETE = do_PATCH = lambda self: self.send_error(405, "Not allowed")

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    print(f"Watchlist history{' (DEMO DATA)' if DEMO else ' (TEST MODE)' if TEST else ''}: http://{HOST}:{PORT}")
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()
