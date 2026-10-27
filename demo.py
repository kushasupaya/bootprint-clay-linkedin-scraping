"""Build a self-contained demo (made-up job changes) in demo/ and serve it on port 8766.

Run: python3 demo.py        Re-run it before presenting so the "days ago" and tiers are fresh.
Uses your real watchlist names, but with invented moves, so it is shown only on your laptop and is
git-ignored. Sending email is simulated in demo mode. Your real data/ and logs/ are never touched.
In the demo, clicking "Check for updates" finds two new Job changes live, and the Demo controls panel on the
page can simulate a job change or title change for anyone, or reset the demo.
Seven invented candidates (example.org addresses) are added alongside your real watchlist.
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
from common import slugify  # noqa: E402

# name -> (decision, days ago, new company, new title, old company, old title)
STAGED = {}
# Moves for the real watchlist people, by position in watchlist.json (so no contact is named in this file).
# position -> (decision, days ago, new company or None to keep, new title or None to keep). Destinations are invented.
REAL_STAGED = {
    0: ("Job change", 1, "Alderbrook Veterinary Health", None),
    3: ("Job change", 3, "Northfield Pet Hospital", None),
    1: ("Possible move", 2, None, "Chief of Surgery"),
    2: ("Possible move", 4, None, "Section Head, Surgery"),
    8: ("Job change", 12, "Silverline Pet Healthcare", None),
    5: ("Possible move", 20, None, "Senior Veterinary Surgeon"),
}
REAL_EMAILED = {3: 2}                       # position -> days ago the demo email was "sent"
REAL_STALE = {7: 1}                         # position -> day with a skipped (stale Clay data) check
REAL_LIVE = {6: ("Mission Veterinary Partners", "Veterinary Surgeon")}  # shown by the CSV, not yet in memory
# Invented candidates: (name, company, title, email). Their moves are staged below like everyone else's.
EXTRAS = [
    ("Dana Whitfield", "Cedar Ridge Animal Hospital", "Veterinary Surgeon", "dana.whitfield@example.org"),
    ("Omar Haddad", "Lakeside Pet Hospital", "Small Animal Surgeon", "omar.haddad@example.org"),
    ("Priyanka Rao", "Harbor Animal Clinic", "Associate Veterinarian", "priyanka.rao@example.org"),
    ("Tom Lindqvist", "Northgate Veterinary Group", "Veterinary Surgeon", "tom.lindqvist@example.org"),
    ("Aiko Tanaka", "Willow Creek Veterinary Center", "Staff Surgeon", "aiko.tanaka@example.org"),
    ("Lena Fischer", "Greenfield Animal Specialists", "Veterinary Surgeon", "lena.fischer@example.org"),
    ("Marcus Bell", "Summit Pet Care", "Veterinary Surgeon", "marcus.bell@example.org"),
]
STAGED.update({
    "Dana Whitfield": ("Job change", 1, "Pacific Coast Veterinary Specialists", "Board-Certified Veterinary Surgeon", "Cedar Ridge Animal Hospital", "Veterinary Surgeon"),
    "Omar Haddad": ("Job change", 2, "Alderbrook Veterinary Health", "Small Animal Surgeon", "Lakeside Pet Hospital", "Small Animal Surgeon"),
    "Priyanka Rao": ("Possible move", 3, "Harbor Animal Clinic", "Lead Veterinarian", "Harbor Animal Clinic", "Associate Veterinarian"),
    "Tom Lindqvist": ("Job change", 9, "Silverline Pet Healthcare", "Veterinary Surgeon", "Northgate Veterinary Group", "Veterinary Surgeon"),
    "Aiko Tanaka": ("Possible move", 16, "Willow Creek Veterinary Center", "Senior Staff Surgeon", "Willow Creek Veterinary Center", "Staff Surgeon"),
    "Lena Fischer": ("Job change", 5, "Redwood Pet Health", "Veterinary Surgeon", "Greenfield Animal Specialists", "Veterinary Surgeon"),
})
EMAILED = {"Lena Fischer": 4}  # name -> days ago the demo email was "sent"
STALE = {}
# name -> (company, title) the demo CSV shows but memory does not yet; "Check for updates" finds these live
LIVE = {"Marcus Bell": ("Keystone Veterinary Group", "Chief of Surgery")}


def stamp(t):
    return t.strftime("%Y-%m-%d %H:%M:%S")


def build():
    now = datetime.now().replace(microsecond=0)
    if DEMO.exists():
        shutil.rmtree(DEMO)
    (DEMO / "data").mkdir(parents=True)
    (DEMO / "logs").mkdir()
    watchlist = json.loads((HERE / "watchlist.json").read_text())
    n_real = len(watchlist)
    for name, company, title, email in EXTRAS:
        watchlist.append({"name": name, "company": company, "linkedin_url": f"https://www.linkedin.com/in/{slugify(name)}-demo"})
    (DEMO / "watchlist.json").write_text(json.dumps(watchlist, indent=2) + "\n")
    (DEMO / ".env").write_text("SENDER_NAME=Demo Recruiter\n")
    with (HERE / "data" / "clay_new.csv").open(newline="", encoding="utf-8-sig") as f:
        rows = {r["Full Name"].strip(): r for r in csv.DictReader(f)}
    for pos, (dec, days, new_co, new_ti) in REAL_STAGED.items():
        if pos < n_real:
            name = watchlist[pos]["name"]
            old_co, old_ti = clean_company(rows[name]["Current Org"]), clean_title(rows[name]["Current Title"])
            STAGED[name] = (dec, days, new_co or old_co, new_ti or old_ti, old_co, old_ti)
    for table, spec in ((EMAILED, REAL_EMAILED), (STALE, REAL_STALE), (LIVE, REAL_LIVE)):
        for pos, value in spec.items():
            if pos < n_real:
                table[watchlist[pos]["name"]] = value
    for name, company, title, email in EXTRAS:
        rows[name] = {"Full Name": name, "First Name": name.split()[0], "Last Name": name.split()[-1],
                      "LinkedIn": f"https://www.linkedin.com/in/{slugify(name)}-demo",
                      "Current Title": title, "Current Org": company, "Email": email}

    fields = ["Full Name", "First Name", "Last Name", "LinkedIn", "Current Title", "Current Org", "Email", "Last Enriched"]
    memory, out_rows = {}, []
    for p in watchlist:
        name = p["name"]
        r = dict(rows[name])
        if name in STAGED:
            r["Current Org"], r["Current Title"] = STAGED[name][2], STAGED[name][3]
        r["Last Enriched"] = (now - timedelta(minutes=20)).strftime("%m/%d/%Y %I:%M %p")
        out_rows.append({k: r.get(k, "") for k in fields})
        title, company = clean_title(r["Current Title"]), clean_company(r["Current Org"])
        if name in LIVE:
            r["Current Org"], r["Current Title"] = LIVE[name]
            out_rows[-1]["Current Org"], out_rows[-1]["Current Title"] = LIVE[name]
        memory[slugify(name)] = {
            "title": title, "company": company,
            "data_as_of": (now - timedelta(minutes=20)).strftime("%Y-%m-%d %H:%M"),
            "last_checked": now.strftime("%Y-%m-%d %H:%M"),
            **({"email": r["Email"]} if r.get("Email") else {}),
        }
    with (DEMO / "data" / "clay_latest.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(out_rows)
    (DEMO / "data" / "memory.json").write_text(json.dumps(memory, indent=2) + "\n")

    # One morning run per day for the last three weeks, plus an extra manual refresh a few days ago.
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
            for i, p in enumerate(watchlist):
                name, url = p["name"], p["linkedin_url"]
                t = at + timedelta(seconds=i + 1)
                stg = STAGED.get(name)
                note = f" (Clay data from {at - timedelta(hours=2):%b %d, %H:%M})"
                if stg and d == stg[1] and label == "Run started":
                    dec, _, new_co, new_ti, old_co, old_ti = stg
                    if dec == "Job change":
                        detail = f"Company changed from {old_co} to {new_co}. Title is now {new_ti}.{note}"
                    else:
                        detail = f"Title changed from {old_ti} to {new_ti}. Same company.{note}"
                    lines.append((t, f"{stamp(t)} | {name} | Profile | {dec} | {detail} | {url}"))
                elif STALE.get(name) == d:
                    detail = f"Clay data is stale (last refreshed {at - timedelta(days=4):%Y-%m-%d %H:%M}). Comparison skipped for today."
                    lines.append((t, f"{stamp(t)} | {name} | Profile | Skipped | {detail}"))
                else:
                    lines.append((t, f"{stamp(t)} | {name} | Profile | No change | Company and title match the saved values{note}"))
            end = at + timedelta(seconds=len(watchlist) + 2)
            lines.append((end, f"{stamp(end)} | - | Run | Info | Run finished"))
    for name, d in EMAILED.items():
        t = (now - timedelta(days=d)).replace(hour=9, minute=30, second=0)
        co = STAGED[name][2]
        lines.append((t, f'{stamp(t)} | {name} | Email | Info | Sent "Congratulations on the move to {co}" to {rows[name]["Email"]} (demo, not actually sent)'))
    lines.sort(key=lambda x: x[0])
    (DEMO / "logs" / "run.log").write_text("\n".join(l for _, l in lines) + "\n")


if __name__ == "__main__":
    build()
    os.environ.update(WATCHLIST_ROOT=str(DEMO), WATCHLIST_DEMO="1", PORT=os.environ.get("PORT", "8766"))
    import server
    print(f"Demo built in {DEMO}. Try 'Check for updates' and the Demo controls on the page.")
    server.ThreadingHTTPServer((server.HOST, server.PORT), server.Handler).serve_forever()
