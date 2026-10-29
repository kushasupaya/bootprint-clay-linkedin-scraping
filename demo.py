"""Build a self-contained demo (made-up job changes) in demo/ and serve it on port 8766.

Run: python3 demo.py        Re-run it before presenting so the "days ago" and tiers are fresh.
Uses your real watchlist names, but with invented moves, so it is shown only on your laptop and is
git-ignored. Sending email is simulated in demo mode. Your real data/ and logs/ are never touched.
In the demo, clicking "Check for updates" finds two new Job changes live, and the Demo controls panel on the
page can simulate a job change or title change for anyone, or reset the demo. Its "Slack alert" button previews the
digest and can really send it to your own Slack DM (SLACK_USER_ID in .env, marked [Demo]); nobody else is reachable.
Three invented candidates (example.org addresses) are added alongside your real watchlist.
"""
import csv
import json
import os
import shutil
import sys
from datetime import datetime, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEMO = HERE / "demo"
sys.path.insert(0, str(HERE))
from engine import clean_company, clean_title  # noqa: E402
import outreach  # noqa: E402
from common import slugify  # noqa: E402

# Invented candidates added after the real watchlist: (name, company, title, email).
EXTRAS = [
    ("Dana Whitfield", "Cedar Ridge Animal Hospital", "Veterinary Surgeon", "dana.whitfield@example.org"),
    ("Lena Fischer", "Greenfield Animal Specialists", "Veterinary Surgeon", "lena.fischer@example.org"),
    ("Marcus Bell", "Summit Pet Care", "Veterinary Surgeon", "marcus.bell@example.org"),
]

# What happens to whom. "who" is a position in watchlist.json (so no real contact is named in this file)
# or the name of an extra. Destinations are invented. Keys:
#   kind     "Job change" (new company) or "Possible move" (new title), logged `days` days ago
#   company, title   the new value; leave one out to keep the old one
#   emailed  days ago the demo email was "sent"
#   stale    days ago the Clay data was too old to compare
#   live     (company, title) Clay shows now but memory does not; "Check for updates" finds it
# Tiers come from recency: A = Job change within 7 days, B = older Job change or recent Possible move, C = older Possible move.
SCENARIOS = [
    {"who": 0, "kind": "Job change", "days": 1, "company": "Evergreen Animal Specialists"},
    {"who": "Dana Whitfield", "kind": "Job change", "days": 1, "company": "Cascadia Veterinary Referral", "title": "Board-Certified Veterinary Surgeon"},
    {"who": "Lena Fischer", "kind": "Job change", "days": 5, "company": "Harborview Pet Health", "emailed": 4},
    {"who": 3, "kind": "Job change", "days": 9, "company": "Lakeshore Veterinary Specialists"},
    {"who": 1, "kind": "Possible move", "days": 2, "title": "Director of Surgery"},
    {"who": 5, "kind": "Possible move", "days": 20, "title": "Lead Staff Surgeon"},
    {"who": 7, "stale": 1},
    {"who": 6, "live": ("Pinecrest Veterinary Partners", "Veterinary Surgeon")},
    {"who": "Marcus Bell", "live": ("Meridian Animal Health", "Head of Surgery")},
]

CSV_FIELDS = ["Full Name", "First Name", "Last Name", "LinkedIn", "Current Title", "Current Org", "Email", "Last Enriched"]


def stamp(t):
    return t.strftime("%Y-%m-%d %H:%M:%S")


def load_clay_rows():
    """The user's Clay export, by name, plus a row for each invented extra."""
    with (HERE / "data" / "clay_new.csv").open(newline="", encoding="utf-8-sig") as f:
        rows = {r["Full Name"].strip(): r for r in csv.DictReader(f)}
    for name, company, title, email in EXTRAS:
        rows[name] = {"Full Name": name, "First Name": name.split()[0], "Last Name": name.split()[-1],
                      "LinkedIn": f"https://www.linkedin.com/in/{slugify(name)}-demo",
                      "Current Title": title, "Current Org": company, "Email": email}
    return rows


def resolve(scenarios, watchlist, rows):
    """Turn SCENARIOS into per-name tables: moves, emailed, stale, live."""
    moves, emailed, stale, live = {}, {}, {}, {}
    for s in scenarios:
        name = watchlist[s["who"]]["name"] if isinstance(s["who"], int) else s["who"]
        if "kind" in s:
            old_co, old_ti = clean_company(rows[name]["Current Org"]), clean_title(rows[name]["Current Title"])
            moves[name] = (s["kind"], s["days"], s.get("company", old_co), s.get("title", old_ti), old_co, old_ti)
        if "emailed" in s:
            emailed[name] = s["emailed"]
        if "stale" in s:
            stale[name] = s["stale"]
        if "live" in s:
            live[name] = s["live"]
    return moves, emailed, stale, live


def write_clay_and_memory(now, watchlist, rows, moves, live):
    """Clay shows each person's current values (the live ones are ahead of memory); memory holds what we knew."""
    enriched = now - timedelta(minutes=20)
    memory, out_rows = {}, []
    for p in watchlist:
        name = p["name"]
        r = dict(rows[name])
        if name in moves:
            r["Current Org"], r["Current Title"] = moves[name][2], moves[name][3]
        known = {"title": clean_title(r["Current Title"]), "company": clean_company(r["Current Org"])}
        if name in live:
            r["Current Org"], r["Current Title"] = live[name]
        r["Last Enriched"] = enriched.strftime("%m/%d/%Y %I:%M %p")
        out_rows.append({k: r.get(k, "") for k in CSV_FIELDS})
        memory[slugify(name)] = {
            **known,
            "data_as_of": enriched.strftime("%Y-%m-%d %H:%M"),
            "last_checked": now.strftime("%Y-%m-%d %H:%M"),
            **({"email": r["Email"]} if r.get("Email") else {}),
        }
    with (DEMO / "data" / "clay_latest.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        w.writeheader()
        w.writerows(out_rows)
    (DEMO / "data" / "memory.json").write_text(json.dumps(memory, indent=2) + "\n")


def write_log(now, watchlist, rows, moves, emailed, stale):
    """One morning run per day for the last three weeks, plus an extra manual refresh a few days ago."""
    lines = []
    for d in range(21, -1, -1):
        run_at = (now - timedelta(days=d)).replace(hour=7, minute=0, second=0)
        if run_at > now:
            continue
        runs = [(run_at, "Run started")]
        if d == 5:
            runs.append((run_at + timedelta(hours=3), "Run started (manual refresh)"))
        for at, label in runs:
            lines.append((at, f"{stamp(at)} | - | Run | Info | {label}"))
            note = f" (Clay data from {at - timedelta(hours=2):%b %d, %H:%M})"
            for i, p in enumerate(watchlist):
                name, url = p["name"], p["linkedin_url"]
                t = at + timedelta(seconds=i + 1)
                move = moves.get(name)
                if move and d == move[1] and label == "Run started":
                    kind, _, new_co, new_ti, old_co, old_ti = move
                    if kind == "Job change":
                        detail = f"Company changed from {old_co} to {new_co}. Title is now {new_ti}.{note}"
                    else:
                        detail = f"Title changed from {old_ti} to {new_ti}. Same company.{note}"
                    lines.append((t, f"{stamp(t)} | {name} | Profile | {kind} | {detail} | {url}"))
                elif stale.get(name) == d:
                    detail = f"Clay data is stale (last refreshed {at - timedelta(days=4):%Y-%m-%d %H:%M}). Comparison skipped for today."
                    lines.append((t, f"{stamp(t)} | {name} | Profile | Skipped | {detail}"))
                else:
                    lines.append((t, f"{stamp(t)} | {name} | Profile | No change | Company and title match the saved values{note}"))
            end = at + timedelta(seconds=len(watchlist) + 2)
            lines.append((end, f"{stamp(end)} | - | Run | Info | Run finished"))
    for name, d in emailed.items():
        t = (now - timedelta(days=d)).replace(hour=9, minute=30, second=0)
        lines.append((t, f'{stamp(t)} | {name} | Email | Info | Sent "Congratulations on the move to {moves[name][2]}" '
                         f'to {rows[name]["Email"]} (demo, not actually sent)'))
    lines.sort(key=lambda x: x[0])
    (DEMO / "logs" / "run.log").write_text("\n".join(l for _, l in lines) + "\n")


def build():
    now = datetime.now().replace(microsecond=0)
    if DEMO.exists():
        shutil.rmtree(DEMO)
    (DEMO / "data").mkdir(parents=True)
    (DEMO / "logs").mkdir()

    watchlist = json.loads((HERE / "watchlist.json").read_text())
    real_count = len(watchlist)
    watchlist += [{"name": n, "company": c, "linkedin_url": f"https://www.linkedin.com/in/{slugify(n)}-demo"} for n, c, _, _ in EXTRAS]
    (DEMO / "watchlist.json").write_text(json.dumps(watchlist, indent=2) + "\n")
    # Only the Slack keys come over, so the demo's Slack alert reaches your own DM. Gmail is deliberately left out:
    # demo email stays simulated because the demo uses your real contacts' addresses.
    real_env = outreach.load_config(HERE / ".env", ())
    slack_lines = [f"{k}={real_env[k]}" for k in ("SLACK_BOT_TOKEN", "SLACK_USER_ID") if real_env.get(k)]
    (DEMO / ".env").write_text("\n".join(["SENDER_NAME=Demo Recruiter", *slack_lines]) + "\n")

    rows = load_clay_rows()
    scenarios = [s for s in SCENARIOS if not isinstance(s["who"], int) or s["who"] < real_count]
    moves, emailed, stale, live = resolve(scenarios, watchlist, rows)
    write_clay_and_memory(now, watchlist, rows, moves, live)
    write_log(now, watchlist, rows, moves, emailed, stale)


if __name__ == "__main__":
    build()
    os.environ.update(WATCHLIST_ROOT=str(DEMO), WATCHLIST_DEMO="1", PORT=os.environ.get("PORT", "8766"))
    import server
    print(f"Demo built in {DEMO}. Try 'Check for updates' and the Demo controls on the page.")
    server.ThreadingHTTPServer((server.HOST, server.PORT), server.Handler).serve_forever()
