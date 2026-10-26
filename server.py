"""Read-only local history page for the LinkedIn job-change watchlist.

Reads watchlist.json, data/memory.json and logs/run.log. The only write is POST /api/refresh,
which runs the engine once (same as `python3 engine.py`) and is limited to this page on this laptop.
Run: python3 server.py   then open http://127.0.0.1:8765
"""
import json
import os
import threading
from datetime import date, datetime, timedelta
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import engine
from common import slugify

ROOT = Path(__file__).parent
WEB = ROOT / "web"
HOST, PORT = "127.0.0.1", int(os.environ.get("PORT", 8765))
ALLOWED_HOSTS = {f"127.0.0.1:{PORT}", f"localhost:{PORT}"}
REFRESH_LOCK = threading.Lock()
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


def build_data():
    watchlist = load_json(ROOT / "watchlist.json", [])
    memory = load_json(ROOT / "data" / "memory.json", {})
    events = parse_log()
    today = date.today()
    days = [(today - timedelta(days=i)).isoformat() for i in range(STRIP_DAYS - 1, -1, -1)]

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
        people.append({
            "slug": slug,
            "name": w["name"],
            "linkedin_url": w.get("linkedin_url", ""),
            "title": mem.get("title", ""),
            "company": mem.get("company", w.get("company", "")),
            "last_checked": mem.get("last_checked", ""),
            "data_as_of": mem.get("data_as_of", ""),
            "latest_signal": signals[0] if signals else None,
            "strip": [{"day": d, "decision": by_day.get(d)} for d in days],
            "events": mine,
        })

    runs = [e for e in events if e["source"] == "Run" and e["detail"].startswith("Run finished")]
    return {
        "people": people,
        "last_run": runs[-1]["time"] if runs else "",
        "today": today.isoformat(),
    }


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(WEB), **kwargs)

    def do_GET(self):
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

    def do_POST(self):
        if self.path.split("?")[0] != "/api/refresh":
            self.send_error(405, "This page is read-only")
            return
        # Only this page may trigger a refresh: right host, same-origin, and a custom header
        # (which a website in another tab cannot add without our permission).
        origin = self.headers.get("Origin")
        if (
            self.headers.get("Host") not in ALLOWED_HOSTS
            or (origin and origin.split("://", 1)[-1] not in ALLOWED_HOSTS)
            or self.headers.get("X-Requested-With") != "watchlist-page"
        ):
            self.send_json(403, {"ok": False, "error": "Refresh is only allowed from this page."})
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

    do_PUT = do_DELETE = do_PATCH = lambda self: self.send_error(405, "This page is read-only")

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    print(f"Watchlist history: http://{HOST}:{PORT}")
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()
