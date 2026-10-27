"""Build 4 invented candidates in testmode/ and serve them on port 8767 to check tiers and email for real.

Run: python3 testmode.py     Re-run it to reset (ages and tiers are relative to now).
Needs .env with GMAIL_ADDRESS and GMAIL_APP_PASSWORD. Every candidate's address is TEST_EMAIL (or GMAIL_ADDRESS)
with a +tag, e.g. you+avery@gmail.com, so every email you send lands in your own inbox and nobody else is contacted.
Unlike demo mode, Send really goes out through Gmail.
Expected order on the page: Avery Stone (A), Jordan Pike (A), Riley Marsh (B), Casey Doyle (C).
After you send to Avery, she should drop below Jordan and show "Email sent".
"""
import csv
import json
import os
import shutil
import sys
from datetime import datetime, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
TESTDIR = HERE / "testmode"
sys.path.insert(0, str(HERE))
import outreach  # noqa: E402
from common import slugify  # noqa: E402

# name, old company, old title, decision, days ago, new company, new title
CANDIDATES = [
    ("Avery Stone", "Cedar Hollow Veterinary", "Veterinary Surgeon", "Job change", 1, "Brightwater Specialty Vets", "Veterinary Surgeon"),
    ("Jordan Pike", "Alder Animal Hospital", "Small Animal Surgeon", "Job change", 3, "Redwood Pet Health", "Small Animal Surgeon"),
    ("Riley Marsh", "Marsh Veterinary Group", "Associate Surgeon", "Possible move", 2, "Marsh Veterinary Group", "Lead Surgeon"),
    ("Casey Doyle", "Stonebridge Animal Clinic", "Staff Surgeon", "Possible move", 25, "Stonebridge Animal Clinic", "Senior Staff Surgeon"),
]


def stamp(t):
    return t.strftime("%Y-%m-%d %H:%M:%S")


def test_address(cfg, name):
    base = cfg.get("TEST_EMAIL") or cfg.get("GMAIL_ADDRESS") or ""
    local, _, domain = base.partition("@")
    return f"{local}+{slugify(name.split()[0])}@{domain}" if local and domain else ""


def build():
    cfg = outreach.load_config(HERE / ".env")
    if not (cfg.get("TEST_EMAIL") or cfg.get("GMAIL_ADDRESS")):
        sys.exit("Put GMAIL_ADDRESS (and GMAIL_APP_PASSWORD) in .env first; see .env.example. Test emails are sent to that address.")
    if not outreach.valid_email(test_address(cfg, "x")):
        sys.exit("TEST_EMAIL / GMAIL_ADDRESS in .env doesn't look like an email address.")
    if not cfg.get("GMAIL_APP_PASSWORD"):
        print("Note: GMAIL_APP_PASSWORD is not set in .env, so Send will say email isn't set up.")

    now = datetime.now().replace(microsecond=0)
    if TESTDIR.exists():
        shutil.rmtree(TESTDIR)
    (TESTDIR / "data").mkdir(parents=True)
    (TESTDIR / "logs").mkdir()
    shutil.copy(HERE / ".env", TESTDIR / ".env") if (HERE / ".env").exists() else None

    watchlist, memory, rows = [], {}, []
    for name, old_co, old_ti, dec, days, new_co, new_ti in CANDIDATES:
        url = f"https://www.linkedin.com/in/{slugify(name)}-test"
        email = test_address(cfg, name)
        watchlist.append({"name": name, "company": new_co, "linkedin_url": url})
        memory[slugify(name)] = {"title": new_ti, "company": new_co, "email": email,
                                 "data_as_of": (now - timedelta(minutes=20)).strftime("%Y-%m-%d %H:%M"),
                                 "last_checked": now.strftime("%Y-%m-%d %H:%M")}
        rows.append({"Full Name": name, "LinkedIn": url, "Current Title": new_ti, "Current Org": new_co, "Email": email,
                     "Last Enriched": (now - timedelta(minutes=20)).strftime("%m/%d/%Y %I:%M %p")})
    (TESTDIR / "watchlist.json").write_text(json.dumps(watchlist, indent=2) + "\n")
    (TESTDIR / "data" / "memory.json").write_text(json.dumps(memory, indent=2) + "\n")
    with (TESTDIR / "data" / "clay_latest.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)

    lines = []
    for d in range(27, -1, -1):
        at = (now - timedelta(days=d)).replace(hour=7, minute=0, second=0)
        if at > now:
            continue
        lines.append((at, f"{stamp(at)} | - | Run | Info | Run started"))
        for i, (name, old_co, old_ti, dec, days, new_co, new_ti) in enumerate(CANDIDATES):
            t = at + timedelta(seconds=i + 1)
            note = f" (Clay data from {at - timedelta(hours=2):%b %d, %H:%M})"
            if d == days:
                detail = (f"Company changed from {old_co} to {new_co}. Title is now {new_ti}.{note}" if dec == "Job change"
                          else f"Title changed from {old_ti} to {new_ti}. Same company.{note}")
                lines.append((t, f"{stamp(t)} | {name} | Profile | {dec} | {detail} | {watchlist[i]['linkedin_url']}"))
            else:
                lines.append((t, f"{stamp(t)} | {name} | Profile | No change | Company and title match the saved values{note}"))
        end = at + timedelta(seconds=len(CANDIDATES) + 2)
        lines.append((end, f"{stamp(end)} | - | Run | Info | Run finished"))
    lines.sort(key=lambda x: x[0])
    (TESTDIR / "logs" / "run.log").write_text("\n".join(l for _, l in lines) + "\n")


if __name__ == "__main__":
    build()
    os.environ.update(WATCHLIST_ROOT=str(TESTDIR), WATCHLIST_TEST="1", PORT=os.environ.get("PORT", "8767"))
    import server
    print("Test mode ready: 4 invented candidates, emails go to your own inbox.")
    server.ThreadingHTTPServer((server.HOST, server.PORT), server.Handler).serve_forever()
