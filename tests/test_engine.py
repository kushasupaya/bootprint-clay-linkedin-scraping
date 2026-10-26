import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import engine  # noqa: E402

NOW = datetime(2026, 10, 26, 22, 0, 0)
SAVED = {"title": "VP of Engineering", "company": "Acme"}


def row(**kw):
    base = {"company": "Acme", "title": "VP of Engineering", "enriched_at": "2026-10-26 21:55:00"}
    base.update(kw)
    return base


class Normalize(unittest.TestCase):
    def test_company_suffixes_and_punctuation(self):
        self.assertEqual(engine.normalize_company("Acme, Inc."), engine.normalize_company("acme"))
        self.assertEqual(engine.normalize_company("Smith & Co"), engine.normalize_company("Smith and Company"))

    def test_company_that_is_only_a_suffix_is_kept(self):
        self.assertEqual(engine.normalize_company("Co"), "co")

    def test_url(self):
        a = engine.normalize_url("https://www.linkedin.com/in/Sarah-Chen/?trk=x")
        self.assertEqual(a, "linkedin.com/in/sarah-chen")


class Cleaning(unittest.TestCase):
    def test_title_drops_trailing_employer(self):
        self.assertEqual(engine.clean_title("Veterinary Surgeon at Northside Referral Center"), "Veterinary Surgeon")
        self.assertEqual(engine.clean_title("Head of Product @ Helio"), "Head of Product")
        self.assertEqual(engine.clean_title("Veterinary Surgeon, Medical Director - New York"),
                         "Veterinary Surgeon, Medical Director - New York")

    def test_company_drops_branch_and_city(self):
        self.assertEqual(engine.clean_company("Harbor Pet Specialists, San Antonio"), "Harbor Pet Specialists")
        self.assertEqual(engine.clean_company("Metro Specialty & Emergency Center (Westchester)"),
                         "Metro Specialty & Emergency Center")
        self.assertEqual(engine.clean_company("Acme Labs, CA"), "Acme Labs")

    def test_company_keeps_legal_suffix_and_ampersand_names(self):
        self.assertEqual(engine.clean_company("Acme Labs, Inc."), "Acme Labs, Inc.")
        self.assertEqual(engine.clean_company("Smith, Jones & Partners"), "Smith, Jones & Partners")

    def test_old_uncleaned_memory_does_not_cause_false_alarm(self):
        saved = {"title": "Veterinary Surgeon at Northside", "company": "Harbor Pet Specialists, San Antonio"}
        d, _, mem = engine.evaluate(row(title="Veterinary Surgeon", company="Harbor Pet Specialists"), saved, NOW)
        self.assertEqual(d, "No change")
        self.assertEqual(mem["title"], "Veterinary Surgeon")  # memory heals to the clean value

    def test_real_company_change_still_detected_after_cleaning(self):
        saved = {"title": "Surgeon", "company": "VetOne"}
        d, _, _ = engine.evaluate(row(title="Surgeon at Cedar", company="Cedar Pet Hospital, Tampa"), saved, NOW)
        self.assertEqual(d, "Job change")


class Timestamps(unittest.TestCase):
    def test_parse_sheet_and_iso_formats(self):
        self.assertEqual(engine.parse_time("10/26/2026 9:55 PM"), datetime(2026, 10, 26, 21, 55))
        self.assertEqual(engine.parse_time("2026-10-26 21:55:00"), datetime(2026, 10, 26, 21, 55))
        self.assertIsNone(engine.parse_time("yesterday"))

    def test_newest_row_wins_per_person(self):
        rows = [
            {"linkedin_url": "https://linkedin.com/in/a", "company": "New", "enriched_at": "2026-10-26 10:00:00"},
            {"linkedin_url": "https://www.linkedin.com/in/a/", "company": "Old", "enriched_at": "2026-10-20 10:00:00"},
            {"linkedin_url": "https://linkedin.com/in/b", "company": "NoTime"},
            {"linkedin_url": "https://linkedin.com/in/b", "company": "Timed", "enriched_at": "2026-10-01 10:00:00"},
        ]
        best = engine.newest_per_person(rows)
        self.assertEqual(best["linkedin.com/in/a"]["company"], "New")
        self.assertEqual(best["linkedin.com/in/b"]["company"], "Timed")

    def test_csv_headers_are_mapped(self):
        with tempfile.TemporaryDirectory() as tmp:
            f = Path(tmp) / "c.csv"
            f.write_text("Full Name,Current Org,Job Title,LinkedIn URL,Last Enriched\n"
                         "Sarah Chen,Acme,VP,https://linkedin.com/in/s,10/26/2026 9:55 PM\n")
            rows = engine.load_rows(f)
            self.assertEqual(rows[0]["company"], "Acme")
            self.assertEqual(rows[0]["enriched_at"], "10/26/2026 9:55 PM")

    def test_csv_missing_required_column(self):
        with tempfile.TemporaryDirectory() as tmp:
            f = Path(tmp) / "c.csv"
            f.write_text("Name,Title\nSarah,VP\n")
            with self.assertRaises(ValueError):
                engine.load_rows(f)

    def test_timestamp_appears_in_detail_and_memory(self):
        _, detail, mem = engine.evaluate(row(company="Globex"), SAVED, NOW)
        self.assertIn("Clay data from Oct 26, 21:55", detail)
        self.assertEqual(mem["data_as_of"], "2026-10-26 21:55")


class Evaluate(unittest.TestCase):
    def test_first_run_saves_baseline_and_reports_nothing(self):
        d, _, mem = engine.evaluate(row(), None, NOW)
        self.assertEqual(d, "Info")
        self.assertEqual(mem["company"], "Acme")

    def test_company_change_is_job_change(self):
        d, detail, mem = engine.evaluate(row(company="Globex"), SAVED, NOW)
        self.assertEqual(d, "Job change")
        self.assertIn("from Acme to Globex", detail)
        self.assertEqual(mem["company"], "Globex")

    def test_spelling_only_company_difference_is_no_change_and_keeps_saved(self):
        d, _, mem = engine.evaluate(row(company="Acme Inc."), SAVED, NOW)
        self.assertEqual(d, "No change")
        self.assertEqual(mem["company"], "Acme")

    def test_title_change_same_company_is_possible_move(self):
        d, _, mem = engine.evaluate(row(title="SVP of Engineering"), SAVED, NOW)
        self.assertEqual(d, "Possible move")
        self.assertEqual(mem["title"], "SVP of Engineering")

    def test_blank_company_is_skipped_never_a_change(self):
        for r in (row(company=""), row(company=None), None):
            d, _, mem = engine.evaluate(r, SAVED, NOW)
            self.assertIn(d, ("Skipped",))
            self.assertIsNone(mem)

    def test_blank_title_does_not_flag_or_erase(self):
        d, _, mem = engine.evaluate(row(title=""), SAVED, NOW)
        self.assertEqual(d, "No change")
        self.assertEqual(mem["title"], "VP of Engineering")

    def test_clay_error(self):
        d, _, mem = engine.evaluate({"error": "out of credits"}, SAVED, NOW)
        self.assertEqual(d, "Error")
        self.assertIsNone(mem)

    def test_stale_row_is_skipped(self):
        old = (NOW - timedelta(days=3)).strftime("%Y-%m-%d %H:%M:%S")
        d, detail, mem = engine.evaluate(row(company="Globex", enriched_at=old), SAVED, NOW)
        self.assertEqual(d, "Skipped")
        self.assertIn("stale", detail)
        self.assertIsNone(mem)


class EndToEnd(unittest.TestCase):
    def test_run_twice_reports_change_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "data").mkdir()
            (root / "watchlist.json").write_text(json.dumps(
                [{"name": "Sarah Chen", "company": "Acme", "linkedin_url": "https://linkedin.com/in/sarah"}]))
            clay = root / "clay.json"
            fresh = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            def write_clay(company):
                clay.write_text(json.dumps([{
                    "name": "Sarah Chen", "company": company, "title": "VP",
                    "linkedin_url": "https://www.linkedin.com/in/sarah/", "enriched_at": fresh}]))

            write_clay("Acme")
            self.assertEqual(engine.run(root, clay)["flagged"], [])      # baseline
            write_clay("Globex")
            self.assertEqual(len(engine.run(root, clay)["flagged"]), 1)  # change
            self.assertEqual(engine.run(root, clay)["flagged"], [])      # not repeated
            log = (root / "logs" / "run.log").read_text()
            self.assertEqual(log.count("| Job change |"), 1)

    def test_unreadable_clay_file_logs_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "watchlist.json").write_text("[]")
            self.assertIsNone(engine.run(root, root / "missing.json"))
            self.assertIn("| Error |", (root / "logs" / "run.log").read_text())


if __name__ == "__main__":
    unittest.main()
