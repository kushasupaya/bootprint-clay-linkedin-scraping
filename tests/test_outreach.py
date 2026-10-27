import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import engine  # noqa: E402
import outreach  # noqa: E402

CFG = {"GMAIL_ADDRESS": "me@example.com", "GMAIL_APP_PASSWORD": "pw", "SENDER_NAME": "Sam Recruiter"}


class FakeSMTP:
    sent = []
    login_args = None

    def __init__(self, host, port, timeout=None):
        self.host, self.port = host, port

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def login(self, user, pw):
        FakeSMTP.login_args = (user, pw)

    def send_message(self, msg):
        FakeSMTP.sent.append(msg)


class Draft(unittest.TestCase):
    def test_job_change_names_company_and_first_name(self):
        d = outreach.build_draft("Sarah Chen", "Job change", "VP of Product", "Globex", "Sam")
        self.assertIn("Globex", d["subject"])
        self.assertTrue(d["body"].startswith("Hi Sarah,"))
        self.assertIn("as VP of Product", d["body"])
        self.assertTrue(d["body"].endswith("Best,\nSam"))

    def test_possible_move_wording(self):
        d = outreach.build_draft("Sarah Chen", "Possible move", "Head of Product", "Acme")
        self.assertIn("Head of Product at Acme", d["body"])
        self.assertIn(outreach.PLACEHOLDER, d["body"])

    def test_placeholder_blocks_send(self):
        d = outreach.build_draft("Sarah Chen", "Job change", "", "Globex")
        self.assertIn("Replace", outreach.check_message(d["subject"], d["body"]))

    def test_check_message(self):
        self.assertIsNone(outreach.check_message("Hi", "Hello there"))
        self.assertTrue(outreach.check_message("", "x"))
        self.assertTrue(outreach.check_message("a\nb", "x"))
        self.assertTrue(outreach.check_message("a", "  "))
        self.assertTrue(outreach.check_message("a", "x" * (outreach.MAX_BODY + 1)))


class Send(unittest.TestCase):
    def setUp(self):
        FakeSMTP.sent = []

    def test_sends_with_login_and_headers(self):
        outreach.send_email(CFG, "sarah@globex.com", "Congrats", "Hi", smtp_factory=FakeSMTP)
        msg = FakeSMTP.sent[0]
        self.assertEqual(FakeSMTP.login_args, ("me@example.com", "pw"))
        self.assertEqual(msg["To"], "sarah@globex.com")
        self.assertIn("Sam Recruiter", msg["From"])

    def test_missing_credentials(self):
        with self.assertRaises(ValueError):
            outreach.send_email({}, "a@b.co", "s", "b", smtp_factory=FakeSMTP)
        self.assertEqual(FakeSMTP.sent, [])

    def test_bad_address(self):
        for bad in ("", "nope", "a@b", "a@b.co, c@d.co"):
            with self.assertRaises(ValueError):
                outreach.send_email(CFG, bad, "s", "b", smtp_factory=FakeSMTP)

    def test_header_injection_rejected(self):
        with self.assertRaises(ValueError):
            outreach.send_email(CFG, "a@b.co", "s\nBcc: x@y.co", "b", smtp_factory=FakeSMTP)


class Config(unittest.TestCase):
    def test_load_config(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / ".env"
            p.write_text('# c\nGMAIL_ADDRESS="me@example.com"\nSENDER_NAME = Sam\n')
            cfg = outreach.load_config(p)
        self.assertEqual(cfg["GMAIL_ADDRESS"], "me@example.com")
        self.assertEqual(cfg["SENDER_NAME"], "Sam")

    def test_missing_file(self):
        self.assertEqual(outreach.load_config("/nonexistent/.env").get("GMAIL_ADDRESS"), None)


class EngineEmail(unittest.TestCase):
    def run_once(self, root, email):
        (root / "data").mkdir(exist_ok=True)
        (root / "watchlist.json").write_text('[{"name": "Sarah Chen", "linkedin_url": "https://linkedin.com/in/sc"}]')
        clay = root / "clay.csv"
        clay.write_text(f"Full Name,LinkedIn,Current Org,Current Title,Email\nSarah Chen,https://linkedin.com/in/sc,Acme,VP,{email}\n")
        engine.run(root, clay)
        return engine.load_json(root / "data" / "memory.json", {})["sarah-chen"]

    def test_email_saved_and_blank_never_erases(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            self.assertEqual(self.run_once(root, "sarah@acme.com")["email"], "sarah@acme.com")
            self.assertEqual(self.run_once(root, "")["email"], "sarah@acme.com")


if __name__ == "__main__":
    unittest.main()
