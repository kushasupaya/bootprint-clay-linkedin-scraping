"""Draft and send the outreach email to a watched person who has moved.

Nothing here sends on its own: server.py calls send_email() only after the user reviews the draft
on the page and clicks Send. The address always comes from data/memory.json (filled from Clay),
never from the browser. Credentials live in .env (GMAIL_ADDRESS, GMAIL_APP_PASSWORD, SENDER_NAME).
"""
import os
import re
import smtplib
from email.message import EmailMessage
from pathlib import Path

SMTP_HOST, SMTP_PORT = "smtp.gmail.com", 465
PLACEHOLDER = "[Your name]"
MAX_BODY = 5000
CONFIG_KEYS = ("GMAIL_ADDRESS", "GMAIL_APP_PASSWORD", "SENDER_NAME")
EMAIL_RE = re.compile(r"^[^@\s<>,;]+@[^@\s<>,;]+\.[^@\s<>,;]+$")


def load_config(env_path, keys=CONFIG_KEYS):
    """Read KEY=VALUE lines from .env; real environment variables win for the listed keys."""
    cfg = {}
    try:
        for line in Path(env_path).read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            cfg[key.strip()] = value.strip().strip("\"'")
    except OSError:
        pass
    for key in keys:
        if os.environ.get(key):
            cfg[key] = os.environ[key]
    return cfg


def valid_email(addr):
    return bool(EMAIL_RE.match((addr or "").strip()))


def first_name(full_name):
    return (full_name or "").split()[0] if (full_name or "").split() else "there"


def build_draft(name, decision, title, company, sender_name=""):
    """Fill the template for a Job change or a Possible move. The user edits it before sending."""
    sender = sender_name or PLACEHOLDER
    hi = f"Hi {first_name(name)},"
    close = f"Best,\n{sender}"
    if decision == "Job change":
        subject = f"Congratulations on the move to {company}"
        role = f" as {title}" if title else ""
        body = (
            f"{hi}\n\nI saw you're now at {company}{role}. Congratulations!\n\n"
            "I'd love to hear how the new role is going. Would you have 15 minutes "
            f"for a quick call in the next week or two?\n\n{close}"
        )
    else:
        subject = "Congratulations on the new role"
        where = f"{title} at {company}" if title else company
        body = (
            f"{hi}\n\nI noticed your role looks to have changed recently ({where}). Congratulations!\n\n"
            "I'd love to catch up. Would you have 15 minutes for a quick call in the next week or two?"
            f"\n\n{close}"
        )
    return {"subject": subject, "body": body}


def check_message(subject, body):
    """Return an error string if the draft must not be sent, else None."""
    if not (subject or "").strip():
        return "The subject is empty."
    if "\n" in subject or "\r" in subject:
        return "The subject must be one line."
    if not (body or "").strip():
        return "The message is empty."
    if len(body) > MAX_BODY:
        return f"The message is too long (limit {MAX_BODY} characters)."
    if PLACEHOLDER in body:
        return f"Replace {PLACEHOLDER} with your name (or set SENDER_NAME in .env)."
    return None


def send_email(cfg, to, subject, body, smtp_factory=smtplib.SMTP_SSL):
    """Send one plain-text email through Gmail. Raises ValueError for setup problems, OSError/SMTP errors otherwise."""
    address, password = cfg.get("GMAIL_ADDRESS", ""), cfg.get("GMAIL_APP_PASSWORD", "")
    if not address or not password:
        raise ValueError("Email sending isn't set up. Add GMAIL_ADDRESS and GMAIL_APP_PASSWORD to .env.")
    if not valid_email(to):
        raise ValueError("The saved email address doesn't look valid.")
    msg = EmailMessage()
    sender_name = cfg.get("SENDER_NAME", "")
    msg["From"] = f"{sender_name} <{address}>" if sender_name else address
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body)
    with smtp_factory(SMTP_HOST, SMTP_PORT, timeout=20) as smtp:
        smtp.login(address, password)
        smtp.send_message(msg)
