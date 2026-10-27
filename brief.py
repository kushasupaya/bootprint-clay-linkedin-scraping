"""One-paragraph brief and priority tier for a person who has a Job change or Possible move.

Tiers are about how worth contacting them is right now, based on how recent the signal is:
  A  Job change in the last 7 days (just moved; the best time to reach out)
  B  Job change older than that, or a Possible move in the last 7 days
  C  Possible move older than that
A tier set by hand in watchlist.json ("tier": "A") overrides the rule.
Age counts from when the system logged the signal, since Clay does not say when the change happened.
"""
import re
from datetime import datetime

FRESH_DAYS = 7
TIERS = ("A", "B", "C")

COMPANY_CHANGE = re.compile(r"Company changed from (?P<old>.+?) to (?P<new>.+?)(?:\. Title is now (?P<title>.+?)\.)?(?: \(Clay data.*)?$")
TITLE_CHANGE = re.compile(r"Title changed from (?P<old>.+?) to (?P<new>.+?)\. Same company\.(?: \(Clay data.*)?$")


def age_days(signal_time, now):
    return max((now - datetime.strptime(signal_time, "%Y-%m-%d %H:%M:%S")).total_seconds() / 86400, 0)


def pick_tier(decision, age, override=""):
    """Return (tier, reason)."""
    if override in TIERS:
        return override, "Set by you in watchlist.json."
    fresh = age <= FRESH_DAYS
    if decision == "Job change":
        return ("A", f"Job change in the last {FRESH_DAYS} days. Just moved, best time to reach out.") if fresh else (
            "B", f"Job change more than {FRESH_DAYS} days ago. Still worth a note.")
    return ("B", f"Possible move in the last {FRESH_DAYS} days. Unconfirmed, check before writing.") if fresh else (
        "C", f"Possible move more than {FRESH_DAYS} days ago. Lowest priority.")


def ago(age):
    days = int(age)
    if days < 1:
        return "today"
    return "yesterday" if days == 1 else f"{days} days ago"


def build_brief(name, mem, signal, now, override="", sent_at=None):
    """signal is the latest Job change / Possible move log event. Returns None when there is none."""
    if not signal:
        return None
    age = age_days(signal["time"], now)
    tier, reason = pick_tier(signal["decision"], age, override)
    title, company = mem.get("title", ""), mem.get("company", "")
    now_role = f"{title} at {company}" if title and company else (title or company)

    detail = signal["detail"]
    m = COMPANY_CHANGE.match(detail) if signal["decision"] == "Job change" else TITLE_CHANGE.match(detail)
    if m and signal["decision"] == "Job change":
        what = f"Moved from {m['old']} to {m['new']}."
    elif m:
        what = f"Title changed from {m['old']} to {m['new']} at {company}."
    else:
        what = detail  # e.g. a quoted post; show it as logged

    parts = [what]
    if now_role and signal["decision"] == "Job change":
        parts.append(f"Now {now_role}.")
    parts.append(f"Spotted {ago(age)}.")
    if sent_at:
        parts.append("You have already emailed them.")
    elif not mem.get("email"):
        parts.append("No email address from Clay yet.")
    return {"tier": tier, "reason": reason, "summary": " ".join(parts), "decision": signal["decision"]}
