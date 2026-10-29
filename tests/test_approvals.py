import io
import json
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import approvals  # noqa: E402
import engine  # noqa: E402
import slack  # noqa: E402

NOW = datetime(2026, 10, 28, 22, 0, 0)
CFG = {"SLACK_BOT_TOKEN": "xoxb-secret", "SLACK_USER_ID": "U123", "GMAIL_ADDRESS": "me@example.com",
       "GMAIL_APP_PASSWORD": "pw", "SENDER_NAME": "Sam Recruiter"}
SIGNAL = {"name": "Sarah Chen", "decision": "Job change", "detail": "Company changed from Acme to Globex",
          "link": "", "company": "Globex", "time": "2026-10-28 21:00:00"}


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class FakeSlack:
    """Stands in for urlopen: records requests, answers chat.postMessage and reactions.get."""

    def __init__(self, reactions=None):
        self.reactions = reactions or []
        self.requests = []

    def __call__(self, request, timeout=None):
        self.requests.append(request)
        if "reactions.get" in request.full_url:
            reply = {"ok": True, "message": {"reactions": self.reactions}}
        else:
            reply = {"ok": True, "channel": "D1", "ts": "111.222"}
        return FakeResponse(json.dumps(reply).encode())

    def posts(self):
        return [json.loads(r.data) for r in self.requests if "chat.postMessage" in r.full_url]


class FakeSMTP:
    sent = []

    def __init__(self, host, port, timeout=None):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def login(self, user, pw):
        pass

    def send_message(self, msg):
        FakeSMTP.sent.append(msg)


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / "data").mkdir()
        (self.root / "data" / "memory.json").write_text(json.dumps(
            {"sarah-chen": {"title": "VP", "company": "Globex", "email": "sarah@example.org"}}))
        self.log = engine.RunLog(self.root / "logs" / "run.log")
        FakeSMTP.sent = []

    def offer(self, fake=None, signals=None):
        fake = fake or FakeSlack()
        n = approvals.offer(self.root, CFG, signals if signals is not None else [SIGNAL], self.log, now=NOW, urlopen=fake)
        return n, fake

    def process(self, fake, now=NOW, events=None):
        return approvals.process(self.root, CFG, self.log, now=now, urlopen=fake, smtp_factory=FakeSMTP,
                                 parse_log=(lambda p: events) if events is not None else None)

    def state(self):
        return approvals.load(self.root)[0]["state"]


class Offer(Base):
    def test_posts_the_exact_draft_and_records_it(self):
        n, fake = self.offer()
        self.assertEqual(n, 1)
        shown = json.dumps(fake.posts()[0]["blocks"])
        self.assertIn("sarah@example.org", shown)
        item = approvals.load(self.root)[0]
        self.assertIn(item["subject"], shown)
        self.assertEqual((item["channel"], item["ts"], item["state"]), ("D1", "111.222", "pending"))

    def test_no_valid_email_means_no_offer(self):
        (self.root / "data" / "memory.json").write_text(json.dumps({"sarah-chen": {"email": ""}}))
        self.assertEqual(self.offer()[0], 0)

    def test_same_signal_is_not_offered_twice(self):
        self.offer()
        self.assertEqual(self.offer()[0], 0)

    def test_placeholder_name_is_not_offered(self):
        fake = FakeSlack()
        n = approvals.offer(self.root, {**CFG, "SENDER_NAME": ""}, [SIGNAL], self.log, now=NOW, urlopen=fake)
        self.assertEqual((n, fake.posts()), (0, []))


class Process(Base):
    CHECK = [{"name": "white_check_mark", "users": ["U123"]}]

    def test_no_reaction_sends_nothing(self):
        self.offer()
        self.assertEqual(self.process(FakeSlack()), 0)
        self.assertEqual((FakeSMTP.sent, self.state()), ([], "pending"))

    def test_someone_elses_reaction_does_not_count(self):
        self.offer()
        self.assertEqual(self.process(FakeSlack([{"name": "white_check_mark", "users": ["U999"]}])), 0)
        self.assertEqual(FakeSMTP.sent, [])

    def test_other_emoji_does_not_count(self):
        self.offer()
        self.assertEqual(self.process(FakeSlack([{"name": "eyes", "users": ["U123"]}])), 0)

    def test_green_check_sends_the_shown_email_and_logs_it(self):
        self.offer()
        item = approvals.load(self.root)[0]
        fake = FakeSlack(self.CHECK)
        self.assertEqual(self.process(fake), 1)
        self.assertEqual(len(FakeSMTP.sent), 1)
        msg = FakeSMTP.sent[0]
        self.assertEqual((msg["To"], msg["Subject"]), ("sarah@example.org", item["subject"]))
        self.assertEqual(msg.get_content().strip(), item["body"])
        self.assertEqual(self.state(), "sent")
        logged = (self.root / "logs" / "run.log").read_text()
        self.assertIn(f'Sarah Chen | Email | Info | Sent "{item["subject"]}" to sarah@example.org (approved in Slack)', logged)
        self.assertTrue(any(p.get("thread_ts") == "111.222" for p in fake.posts()))

    def test_second_pass_does_not_send_again(self):
        self.offer()
        self.process(FakeSlack(self.CHECK))
        self.assertEqual(self.process(FakeSlack(self.CHECK)), 0)
        self.assertEqual(len(FakeSMTP.sent), 1)

    def test_email_already_sent_from_the_page_blocks_it(self):
        self.offer()
        done = [{"time": "2026-10-28 21:30:00", "person": "Sarah Chen", "source": "Email", "decision": "Info",
                 "detail": 'Sent "Hi" to sarah@example.org', "link": ""}]
        self.assertEqual(self.process(FakeSlack(self.CHECK), events=done), 0)
        self.assertEqual((FakeSMTP.sent, self.state()), ([], "skipped"))

    def test_changed_address_blocks_it(self):
        self.offer()
        (self.root / "data" / "memory.json").write_text(json.dumps({"sarah-chen": {"email": "other@example.org"}}))
        self.assertEqual(self.process(FakeSlack(self.CHECK)), 0)
        self.assertEqual((FakeSMTP.sent, self.state()), ([], "skipped"))

    def test_expired_offer_is_not_sent_even_if_approved(self):
        self.offer()
        later = datetime(2026, 10, 31, 0, 0, 0)
        self.assertEqual(self.process(FakeSlack(self.CHECK), now=later), 0)
        self.assertEqual((FakeSMTP.sent, self.state()), ([], "expired"))

    def test_slack_failure_is_logged_and_retried_next_time(self):
        self.offer()

        def down(request, timeout=None):
            return FakeResponse(json.dumps({"ok": False, "error": "missing_scope"}).encode())
        self.assertEqual(self.process(down), 0)
        self.assertEqual(self.state(), "pending")
        self.assertIn("missing_scope", (self.root / "logs" / "run.log").read_text())

    def test_gmail_failure_sends_nothing_and_is_logged(self):
        self.offer()

        class Boom(FakeSMTP):
            def login(self, user, pw):
                raise OSError("no network")
        n = approvals.process(self.root, CFG, self.log, now=NOW, urlopen=FakeSlack(self.CHECK), smtp_factory=Boom)
        self.assertEqual((n, self.state()), (0, "failed"))
        self.assertIn("Sarah Chen | Email | Error", (self.root / "logs" / "run.log").read_text())


class Demo(Base):
    CHECK = [{"name": "white_check_mark", "users": ["U123"]}]

    def test_demo_offer_is_marked_and_limited(self):
        second = {**SIGNAL, "name": "Raj Patel", "time": "2026-10-28 21:05:00"}
        (self.root / "data" / "memory.json").write_text(json.dumps({
            "sarah-chen": {"email": "sarah@example.org"}, "raj-patel": {"email": "raj@example.org"}}))
        fake = FakeSlack()
        n = approvals.offer(self.root, CFG, [SIGNAL, second], self.log, now=NOW, urlopen=fake, demo=True, limit=1)
        self.assertEqual(n, 1)
        self.assertIn("[Demo]", json.dumps(fake.posts()[0]["blocks"]))
        self.assertTrue(approvals.load(self.root)[0]["demo"])

    def test_approving_a_demo_offer_never_touches_gmail(self):
        approvals.offer(self.root, CFG, [SIGNAL], self.log, now=NOW, urlopen=FakeSlack(), demo=True)

        class NoMail(FakeSMTP):
            def __init__(self, *a, **k):
                raise AssertionError("Gmail must not be used for a demo offer")
        # process() called WITHOUT demo=True: the stored mark alone must keep it pretend.
        n = approvals.process(self.root, CFG, self.log, now=NOW, urlopen=FakeSlack(self.CHECK), smtp_factory=NoMail)
        self.assertEqual((n, self.state()), (1, "sent"))
        self.assertIn("(demo, not actually sent)", (self.root / "logs" / "run.log").read_text())


class Reactions(unittest.TestCase):
    def test_token_is_never_in_the_error(self):
        def down(request, timeout=None):
            return FakeResponse(json.dumps({"ok": False, "error": "invalid_auth"}).encode())
        with self.assertRaises(slack.SlackError) as cm:
            slack.approved_by_user(CFG, "D1", "1.2", urlopen=down)
        self.assertNotIn("xoxb", str(cm.exception))


if __name__ == "__main__":
    unittest.main()
