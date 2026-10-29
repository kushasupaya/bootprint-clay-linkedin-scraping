"""Format the daily digest and send it to the user as a Slack direct message.

Alerts only: nothing here changes anything except posting one private message. Credentials live in
.env (SLACK_BOT_TOKEN = bot token with chat:write, SLACK_USER_ID = the user's member ID, e.g. U012ABCDEF).
A bot can DM a user by posting to their member ID.
"""
import json
import time
import urllib.error
import urllib.parse
import urllib.request

API_URL = "https://slack.com/api/chat.postMessage"
REACTIONS_URL = "https://slack.com/api/reactions.get"
APPROVE_REACTIONS = ("white_check_mark", "heavy_check_mark")  # the green check emoji
WHY = {
    "Job change": "Likely available now. Reach out this week.",
    "Possible move": "Unconfirmed. Check their profile before writing.",
}


class SlackError(Exception):
    pass


def esc(text):
    """Slack treats & < > as markup."""
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def signal_line(item):
    """item: name, company, decision, detail, link. One bullet for the digest."""
    head = f"*{esc(item['name'])}*" + (f", {esc(item['company'])}" if item.get("company") else "")
    link = f" <{item['link']}|View profile>" if item.get("link", "").startswith("http") else ""
    return f"{head}: {esc(item['detail'])}\n_{WHY[item['decision']]}_{link}"


def build_digest(signals, notes, late=False, page_url="", demo=False):
    """Return (fallback_text, blocks). signals are Job change / Possible move items; notes are plain strings.
    demo=True marks the message as made-up data so it is easy to spot and delete in Slack."""
    jobs = [s for s in signals if s["decision"] == "Job change"]
    maybe = [s for s in signals if s["decision"] == "Possible move"]
    prefix = ("[Demo] " if demo else "") + ("Late summary. " if late else "")

    if jobs:
        headline = f"{len(jobs)} job change{'s' if len(jobs) != 1 else ''}" + (f", {len(maybe)} possible" if maybe else "")
    elif maybe:
        headline = f"{len(maybe)} possible move{'s' if len(maybe) != 1 else ''}"
    else:
        headline = "Nothing today"
    text = f"{prefix}Watchlist: {headline}"

    def section(md):
        return {"type": "section", "text": {"type": "mrkdwn", "text": md}}

    blocks = [{"type": "header", "text": {"type": "plain_text", "text": text}}]
    if jobs:
        blocks.append(section("*Job changes*\n\n" + "\n\n".join(signal_line(s) for s in jobs)))
    if maybe:
        blocks.append(section("*Possible moves*\n\n" + "\n\n".join(signal_line(s) for s in maybe)))
    if not signals:
        blocks.append(section("No job changes today."))
    if notes:
        blocks.append(section("\n".join(f"• {esc(n)}" for n in notes)))
    if signals and page_url:
        blocks.append({"type": "context", "elements": [
            {"type": "mrkdwn", "text": f"Read the details and email them from the history page: {esc(page_url)}"}]})
    if demo:
        blocks.append({"type": "context", "elements": [{"type": "mrkdwn", "text": "Demo data: these changes are made up."}]})
    return text, blocks


def post_message(cfg, text, blocks, urlopen=urllib.request.urlopen, sleep=time.sleep, channel=None, thread_ts=None):
    """Send the DM (or a threaded reply when channel and thread_ts are given) and return Slack's reply, which
    holds the DM's channel ID and the message ts. Retries once on failure, then raises SlackError (the reason
    never includes the token)."""
    token, user = cfg.get("SLACK_BOT_TOKEN", ""), cfg.get("SLACK_USER_ID", "")
    if not token or not user:
        raise SlackError("Slack isn't set up. Add SLACK_BOT_TOKEN and SLACK_USER_ID to .env.")
    payload = {"channel": channel or user, "text": text, "unfurl_links": False}
    if blocks:
        payload["blocks"] = blocks
    if thread_ts:
        payload["thread_ts"] = thread_ts
    body = json.dumps(payload).encode()
    request = urllib.request.Request(API_URL, data=body, headers={
        "Authorization": f"Bearer {token}", "Content-Type": "application/json; charset=utf-8"})

    last = ""
    for attempt in range(2):
        if attempt:
            sleep(5)
        try:
            with urlopen(request, timeout=20) as resp:
                reply = json.loads(resp.read().decode())
            if reply.get("ok"):
                return reply
            last = f"Slack said: {reply.get('error', 'unknown error')}"
            if reply.get("error") in ("invalid_auth", "not_authed", "token_revoked", "account_inactive", "channel_not_found", "user_not_found"):
                break  # a retry cannot fix a bad token or ID
        except (urllib.error.URLError, OSError, ValueError) as e:
            last = f"Could not reach Slack ({type(e).__name__})"
    raise SlackError(last)


def approved_by_user(cfg, channel, ts, urlopen=urllib.request.urlopen):
    """True when the user (SLACK_USER_ID) has put a green check reaction on the message. Read-only; needs the
    reactions:read bot scope. Raises SlackError on any failure (never includes the token)."""
    token, user = cfg.get("SLACK_BOT_TOKEN", ""), cfg.get("SLACK_USER_ID", "")
    if not token or not user:
        raise SlackError("Slack isn't set up. Add SLACK_BOT_TOKEN and SLACK_USER_ID to .env.")
    query = urllib.parse.urlencode({"channel": channel, "timestamp": ts})
    request = urllib.request.Request(f"{REACTIONS_URL}?{query}", headers={"Authorization": f"Bearer {token}"})
    try:
        with urlopen(request, timeout=20) as resp:
            reply = json.loads(resp.read().decode())
    except (urllib.error.URLError, OSError, ValueError) as e:
        raise SlackError(f"Could not reach Slack ({type(e).__name__})")
    if not reply.get("ok"):
        raise SlackError(f"Slack said: {reply.get('error', 'unknown error')}")
    return any(r.get("name") in APPROVE_REACTIONS and user in r.get("users", [])
               for r in reply.get("message", {}).get("reactions", []))
