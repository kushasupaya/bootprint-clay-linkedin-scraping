"""Compare Clay's current title and company with the saved memory, then log the result.

Reads:  watchlist.json, data/clay_latest.json or .csv (rows from Clay), data/memory.json
Writes: logs/run.log (append), data/memory.json
Run:    python3 engine.py [--clay FILE] [--root DIR]

Clay rows look like:
  {"name": "...", "company": "...", "title": "...", "linkedin_url": "...", "enriched_at": "2026-10-26 21:55:00"}
A row may carry "error" instead of data. Blank or missing data is never treated as a change.
"""
import argparse
import csv
import json
import os
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

from common import slugify

ROOT = Path(__file__).parent
STALE_AFTER = timedelta(hours=48)
COMPANY_SUFFIXES = {
    "inc", "incorporated", "llc", "ltd", "limited", "corp", "corporation",
    "co", "company", "gmbh", "plc", "ag", "sa", "bv", "pty",
}
SIGNALS = ("Job change", "Possible move")


def normalize_url(url):
    u = (url or "").strip().lower()
    u = re.sub(r"^https?://", "", u)
    u = re.sub(r"^www\.", "", u)
    return u.split("?")[0].split("#")[0].rstrip("/")


def normalize_company(name):
    """Lowercase, drop punctuation and legal suffixes so 'Acme' and 'Acme, Inc.' match."""
    words = re.sub(r"[^\w\s]", " ", (name or "").lower().replace("&", " and ")).split()
    while len(words) > 1 and words[-1] in COMPANY_SUFFIXES:
        words.pop()
    return " ".join(words)


def normalize_title(title):
    return " ".join(re.sub(r"[^\w\s]", " ", (title or "").lower()).split())


TIME_FORMATS = (
    "%m/%d/%Y %H:%M:%S", "%m/%d/%Y %H:%M", "%m/%d/%Y %I:%M:%S %p", "%m/%d/%Y %I:%M %p", "%m/%d/%Y",
)


def parse_time(value):
    """Parse ISO or US-style sheet timestamps into local naive time. Returns None if unreadable."""
    s = str(value or "").strip()
    if not s:
        return None
    try:
        t = datetime.fromisoformat(s.replace("Z", "+00:00"))
        return t.astimezone().replace(tzinfo=None) if t.tzinfo else t
    except ValueError:
        pass
    for fmt in TIME_FORMATS:
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


US_STATES = {
    "al","ak","az","ar","ca","co","ct","de","fl","ga","hi","id","il","in","ia","ks","ky","la","me","md","ma","mi",
    "mn","ms","mo","mt","ne","nv","nh","nj","nm","ny","nc","nd","oh","ok","or","pa","ri","sc","sd","tn","tx","ut",
    "vt","va","wa","wv","wi","wy","dc",
}


def clean_title(title):
    """Drop a trailing employer from the title: 'Surgeon at Northside' -> 'Surgeon'."""
    t = re.split(r"\s+(?:at|@)\s+", (title or "").strip(), maxsplit=1, flags=re.IGNORECASE)[0].strip()
    return t or (title or "").strip()


def clean_company(name):
    """Drop a trailing '(branch)' and a trailing ', City' or ', ST' so site names don't read as company changes."""
    n = re.sub(r"\s*\([^)]*\)\s*$", "", (name or "").strip()).strip()
    head, sep, tail = n.rpartition(",")
    tail = tail.strip()
    words = tail.split()
    looks_like_place = (
        sep
        and 1 <= len(words) <= 3
        and "&" not in tail
        and (tail.lower() in US_STATES or all(w[:1].isupper() for w in words))
        and tail.lower().rstrip(".") not in COMPANY_SUFFIXES
        and len(head.split()) >= 2
    )
    return head.strip() if looks_like_place else n or (name or "").strip()


def describe(title, company):
    return f"{title} at {company}" if title else company


def evaluate(row, saved, now):
    """Return (decision, detail, new_memory). new_memory is None when no comparison happened."""
    if row is None:
        return "Skipped", "Clay sent no row for this person. Comparison skipped for today.", None
    if row.get("error"):
        return "Error", f"Clay reported an error ({row['error']}). Comparison skipped for today.", None

    company = clean_company(row.get("company"))
    title = clean_title(row.get("title"))
    if saved:
        saved = {**saved, "company": clean_company(saved.get("company")), "title": clean_title(saved.get("title"))}
    if not company:
        return "Skipped", "Clay returned blank data. Comparison skipped for today.", None

    enriched = parse_time(row.get("enriched_at"))
    if enriched and now - enriched > STALE_AFTER:
        return (
            "Skipped",
            f"Clay data is stale (last refreshed {enriched:%Y-%m-%d %H:%M}). Comparison skipped for today.",
            None,
        )

    # A blank title never overwrites a saved one.
    new = {"title": title or (saved or {}).get("title", ""), "company": company}
    if enriched:
        new["data_as_of"] = enriched.strftime("%Y-%m-%d %H:%M")
    source = f" (Clay data from {enriched:%b %d, %H:%M})" if enriched else ""

    if not saved:
        return "Info", f"First run: saved {describe(new['title'], company)} as the starting point{source}", new

    if normalize_company(company) != normalize_company(saved.get("company", "")):
        detail = f"Company changed from {saved.get('company', '')} to {company}"
        if title and normalize_title(title) != normalize_title(saved.get("title", "")):
            detail += f". Title is now {title}."
        return "Job change", detail + source, new

    if title and normalize_title(title) != normalize_title(saved.get("title", "")):
        return (
            "Possible move",
            f"Title changed from {saved.get('title', '')} to {title}. Same company.{source}",
            new,
        )

    # Same company and title, or a spelling-only difference: keep what was saved.
    kept = {
        "title": saved.get("title", "") or new["title"],
        "company": saved.get("company", "") or company,
    }
    if "data_as_of" in new:
        kept["data_as_of"] = new["data_as_of"]
    return "No change", f"Company and title match the saved values{source}", kept


COLUMN_ALIASES = {
    "name": ("name", "full name", "full_name", "fullname"),
    "company": ("company", "current company", "current org", "current organization", "org", "organization", "employer"),
    "title": ("title", "job title", "current title", "current job title", "position"),
    "linkedin_url": ("linkedin_url", "linkedin url", "linkedin", "linkedin profile", "profile url", "url"),
    "enriched_at": ("enriched_at", "enriched at", "last enriched", "last updated", "updated at", "timestamp", "date"),
    "error": ("error", "status error"),
    "email": ("email", "email address", "work email", "personal email", "e-mail"),
}


def load_rows(path):
    """Read Clay rows from JSON or a CSV export, mapping common header names to ours."""
    path = Path(path)
    if path.suffix.lower() != ".csv":
        rows = json.loads(path.read_text())
        if not isinstance(rows, list):
            raise ValueError("expected a list of rows")
        return rows
    with path.open(newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        lookup = {}
        for header in reader.fieldnames or []:
            for key, aliases in COLUMN_ALIASES.items():
                if header.strip().lower() in aliases and key not in lookup:
                    lookup[key] = header
        missing = [k for k in ("name", "company", "linkedin_url") if k not in lookup]
        if missing:
            raise ValueError(f"CSV is missing columns for: {', '.join(missing)}")
        return [{key: (r.get(h) or "").strip() for key, h in lookup.items()} for r in reader]


def newest_per_person(rows):
    """One row per LinkedIn URL: the one with the latest timestamp. Untimed rows lose to timed ones; later rows win ties."""
    best = {}
    for r in rows:
        key = normalize_url(r.get("linkedin_url"))
        stamp = parse_time(r.get("enriched_at")) or datetime.min
        if key not in best or stamp >= best[key][0]:
            best[key] = (stamp, r)
    return {k: v[1] for k, v in best.items()}


def load_json(path, default):
    try:
        return json.loads(path.read_text())
    except FileNotFoundError:
        return default


def save_json_atomic(path, data):
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2) + "\n")
    os.replace(tmp, path)


class RunLog:
    def __init__(self, path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)

    def write(self, person, source, decision, detail, link=""):
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        fields = [now, person, source, decision, detail.replace("|", "/"), link]
        with self.path.open("a") as f:
            f.write(" | ".join(fields).rstrip(" |") + "\n")


def default_clay_path(root):
    data_dir = Path(root) / "data"
    csv_path = data_dir / "clay_latest.csv"
    return csv_path if csv_path.exists() else data_dir / "clay_latest.json"


def run(root, clay_path, trigger="scheduled"):
    """trigger is 'scheduled' or 'manual'; manual runs say so in the log."""
    root = Path(root)
    log = RunLog(root / "logs" / "run.log")
    log.write("-", "Run", "Info", "Run started (manual refresh)" if trigger == "manual" else "Run started")

    try:
        watchlist = json.loads((root / "watchlist.json").read_text())
        rows = load_rows(clay_path)
    except (OSError, ValueError) as e:
        log.write("-", "Run", "Error", f"Could not read the watchlist or Clay data: {e}")
        log.write("-", "Run", "Info", "Run finished")
        return None

    memory_path = root / "data" / "memory.json"
    memory = load_json(memory_path, {})
    now = datetime.now()
    by_url = newest_per_person(rows)
    watched_urls = {normalize_url(p.get("linkedin_url")) for p in watchlist}

    flagged = []
    notes = []
    for person in watchlist:
        name, url = person["name"], person.get("linkedin_url", "")
        slug = slugify(name)
        decision, detail, new_mem = evaluate(by_url.get(normalize_url(url)), memory.get(slug), now)
        log.write(name, "Profile", decision, detail, url if decision in SIGNALS else "")
        if new_mem is not None:
            # Contact email (for outreach) comes from Clay; a blank one never erases a saved one.
            email = ((by_url.get(normalize_url(url)) or {}).get("email") or "").strip() or memory.get(slug, {}).get("email", "")
            if email:
                new_mem["email"] = email
            memory[slug] = {**new_mem, "last_checked": now.strftime("%Y-%m-%d %H:%M")}
        if decision in SIGNALS:
            flagged.append((name, decision, detail, url))
        elif decision in ("Skipped", "Error"):
            notes.append(f"Couldn't check {name}'s profile today.")

    for url, row in by_url.items():
        if url not in watched_urls:
            log.write(row.get("name") or "-", "Profile", "Ignored", "Clay row is not on the watchlist")

    save_json_atomic(memory_path, memory)
    log.write("-", "Run", "Info", "Run finished")
    return {"flagged": flagged, "notes": notes}


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--root", default=str(ROOT), help="project folder holding watchlist.json, data/, logs/")
    ap.add_argument("--clay", help="Clay rows file (JSON or CSV; default: <root>/data/clay_latest.json)")
    args = ap.parse_args()

    clay = args.clay or str(default_clay_path(args.root))
    result = run(args.root, clay)
    if result is None:
        print("Run failed. See logs/run.log.", file=sys.stderr)
        sys.exit(1)
    if not result["flagged"] and not result["notes"]:
        print("Nothing today.")
    for name, decision, detail, url in result["flagged"]:
        print(f"{decision}: {name}. {detail} {url}")
    for note in result["notes"]:
        print(note)


if __name__ == "__main__":
    main()
