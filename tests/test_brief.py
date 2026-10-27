import sys
import unittest
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import brief  # noqa: E402

NOW = datetime(2026, 10, 27, 12, 0, 0)


def sig(decision, detail, time="2026-10-26 22:00:00"):
    return {"decision": decision, "detail": detail, "time": time}


JOB = "Company changed from Northwind to Globex. Title is now VP of Product. (Clay data from Oct 26, 21:55)"
MOVE = "Title changed from Director to Senior Director. Same company. (Clay data from Oct 26, 21:55)"
MEM = {"title": "VP of Product", "company": "Globex", "email": "a@globex.com"}


class Tier(unittest.TestCase):
    def tier(self, decision, days, override=""):
        return brief.pick_tier(decision, days, override)[0]

    def test_rules(self):
        self.assertEqual(self.tier("Job change", 2), "A")
        self.assertEqual(self.tier("Job change", 7), "A")
        self.assertEqual(self.tier("Job change", 8), "B")
        self.assertEqual(self.tier("Possible move", 1), "B")
        self.assertEqual(self.tier("Possible move", 30), "C")

    def test_override_wins_and_bad_override_ignored(self):
        self.assertEqual(self.tier("Possible move", 30, "A"), "A")
        self.assertEqual(self.tier("Possible move", 30, "Z"), "C")


class Brief(unittest.TestCase):
    def test_no_signal(self):
        self.assertIsNone(brief.build_brief("X", MEM, None, NOW))

    def test_job_change_summary(self):
        b = brief.build_brief("Sarah Chen", MEM, sig("Job change", JOB), NOW)
        self.assertEqual(b["tier"], "A")
        self.assertIn("Moved from Northwind to Globex.", b["summary"])
        self.assertIn("Now VP of Product at Globex.", b["summary"])
        self.assertIn("Spotted today.", b["summary"])

    def test_title_change_summary(self):
        b = brief.build_brief("Sarah Chen", MEM, sig("Possible move", MOVE, "2026-10-20 22:00:00"), NOW)
        self.assertEqual(b["tier"], "B")
        self.assertIn("Title changed from Director to Senior Director at Globex.", b["summary"])
        self.assertIn("Spotted 6 days ago.", b["summary"])

    def test_unparseable_detail_shown_as_logged(self):
        b = brief.build_brief("X", MEM, sig("Possible move", '"Big things ahead." No company named.'), NOW)
        self.assertIn("Big things ahead", b["summary"])

    def test_email_status_notes(self):
        self.assertIn("No email address", brief.build_brief("X", {**MEM, "email": ""}, sig("Job change", JOB), NOW)["summary"])
        self.assertIn("already emailed", brief.build_brief("X", MEM, sig("Job change", JOB), NOW, sent_at="2026-10-27 09:00:00")["summary"])


if __name__ == "__main__":
    unittest.main()
