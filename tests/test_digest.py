import io
import json
import sys
import unittest
import urllib.error
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import digest  # noqa: E402
import slack  # noqa: E402

NOW = datetime(2026, 10, 28, 22, 0, 0)
WATCH = [{"name": "Sarah Chen", "company": "Acme"}, {"name": "Raj Patel", "company": "Helio"}]
MEM = {"sarah-chen": {"company": "Globex"}}


def ev(time, person, source, decision, detail, link=""):
    return {"time": time, "person": person, "source": source, "decision": decision, "detail": detail, "link": link}


JOB = ev("2026-10-28 21:00:00", "Sarah Chen", "Profile", "Job change", "Company changed from Acme to Globex", "https://linkedin.com/in/sarah-chen")


class Collect(unittest.TestCase):
    def test_only_events_after_last_sent_digest(self):
        events = [
            ev("2026-10-27 22:00:00", "Raj Patel", "Profile", "Job change", "Company changed from Helio to Zed"),
            ev("2026-10-27 22:05:00", "-", "Slack", "Info", "Sent daily digest (1 job change, 0 possible, 0 notes)"),
            JOB,
        ]
        signals, notes = digest.collect(events, WATCH, MEM, NOW)
        self.assertEqual([s["name"] for s in signals], ["Sarah Chen"])
        self.assertEqual(signals[0]["company"], "Globex")  # memory wins over the watchlist company
        self.assertEqual(notes, [])

    def test_failed_send_is_not_a_sent_digest(self):
        events = [JOB, ev("2026-10-28 22:01:00", "-", "Slack", "Error", "Could not send daily digest: Slack said: invalid_auth")]
        signals, _ = digest.collect(events, WATCH, MEM, NOW)
        self.assertEqual(len(signals), 1)

    def test_first_digest_looks_back_a_week_only(self):
        old = ev("2026-10-01 10:00:00", "Raj Patel", "Profile", "Job change", "Company changed from Helio to Zed")
        signals, _ = digest.collect([old, JOB], WATCH, MEM, NOW)
        self.assertEqual([s["name"] for s in signals], ["Sarah Chen"])

    def test_people_off_the_watchlist_are_ignored(self):
        other = ev("2026-10-28 21:00:00", "Nobody Known", "Profile", "Job change", "Company changed from A to B")
        self.assertEqual(digest.collect([other], WATCH, MEM, NOW)[0], [])

    def test_couldnt_check_note_clears_after_a_good_check(self):
        skipped = ev("2026-10-28 20:00:00", "Raj Patel", "Profile", "Skipped", "Clay returned blank data.")
        good = ev("2026-10-28 21:30:00", "Raj Patel", "Profile", "No change", "Company and title match")
        self.assertEqual(digest.collect([skipped], WATCH, MEM, NOW)[1], ["Couldn't check Raj Patel's profile today."])
        self.assertEqual(digest.collect([skipped, good], WATCH, MEM, NOW)[1], [])

    def test_run_error_becomes_a_note(self):
        err = ev("2026-10-28 21:00:00", "-", "Run", "Error", "Could not read the watchlist or Clay data: x")
        self.assertEqual(digest.collect([err], WATCH, MEM, NOW)[1], ["Today's check couldn't run. See logs/run.log."])


class Build(unittest.TestCase):
    item = {"name": "Sarah <Chen>", "company": "Globex & Co", "decision": "Job change",
            "detail": "Company changed from Acme to Globex", "link": "https://linkedin.com/in/x"}

    def test_nothing_today(self):
        text, blocks = slack.build_digest([], [])
        self.assertEqual(text, "Watchlist: Nothing today")
        self.assertIn("No job changes today.", json.dumps(blocks))

    def test_late_label_and_sections(self):
        maybe = {**self.item, "name": "Raj Patel", "decision": "Possible move", "detail": "Title changed from A to B. Same company."}
        text, blocks = slack.build_digest([self.item, maybe], ["Couldn't check Lee Wu's profile today."], late=True, page_url="http://127.0.0.1:8765")
        self.assertEqual(text, "Late summary. Watchlist: 1 job change, 1 possible")
        body = json.dumps(blocks)
        self.assertLess(body.index("Job changes"), body.index("Possible moves"))
        self.assertIn("Couldn't check Lee Wu", body)
        self.assertIn("Likely available now", body)

    def test_slack_markup_is_escaped(self):
        body = json.dumps(slack.build_digest([self.item], [])[1])
        self.assertIn("Sarah &lt;Chen&gt;", body)
        self.assertIn("Globex &amp; Co", body)

    def test_non_http_link_is_dropped(self):
        line = slack.signal_line({**self.item, "link": "javascript:x|y"})
        self.assertNotIn("javascript", line)


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def replying(*replies):
    calls = []

    def opener(request, timeout=None):
        calls.append(request)
        r = replies[min(len(calls) - 1, len(replies) - 1)]
        if isinstance(r, Exception):
            raise r
        return FakeResponse(json.dumps(r).encode())
    opener.calls = calls
    return opener


CFG = {"SLACK_BOT_TOKEN": "xoxb-secret", "SLACK_USER_ID": "U123"}


class Post(unittest.TestCase):
    def test_sends_once_when_ok(self):
        op = replying({"ok": True})
        slack.post_message(CFG, "hi", [], urlopen=op, sleep=lambda s: None)
        self.assertEqual(len(op.calls), 1)
        self.assertEqual(json.loads(op.calls[0].data)["channel"], "U123")

    def test_retries_once_then_succeeds(self):
        op = replying(urllib.error.URLError("down"), {"ok": True})
        slack.post_message(CFG, "hi", [], urlopen=op, sleep=lambda s: None)
        self.assertEqual(len(op.calls), 2)

    def test_gives_up_after_one_retry(self):
        op = replying({"ok": False, "error": "ratelimited"})
        with self.assertRaises(slack.SlackError) as cm:
            slack.post_message(CFG, "hi", [], urlopen=op, sleep=lambda s: None)
        self.assertEqual(len(op.calls), 2)
        self.assertIn("ratelimited", str(cm.exception))

    def test_bad_token_is_not_retried_and_never_leaked(self):
        op = replying({"ok": False, "error": "invalid_auth"})
        with self.assertRaises(slack.SlackError) as cm:
            slack.post_message(CFG, "hi", [], urlopen=op, sleep=lambda s: None)
        self.assertEqual(len(op.calls), 1)
        self.assertNotIn("xoxb", str(cm.exception))

    def test_missing_setup(self):
        with self.assertRaises(slack.SlackError):
            slack.post_message({}, "hi", [])


if __name__ == "__main__":
    unittest.main()
