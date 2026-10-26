"""Small helpers shared by server.py and engine.py."""
import re


def slugify(name):
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
