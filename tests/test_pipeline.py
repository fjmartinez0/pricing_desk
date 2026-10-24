"""Unit tests on known cases. Run: python3 -m unittest discover -s tests -v"""
from __future__ import annotations

import datetime as dt
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import apply_proposals as ap  # noqa: E402
import capture  # noqa: E402
import close_week  # noqa: E402
import common  # noqa: E402
from normalize import html_to_text, looks_like_pricing  # noqa: E402

FIX = ROOT / "tests" / "fixtures"


class Weeks(unittest.TestCase):
    def test_labels_match_existing_data(self):
        desk = common.load_json(common.DESK)
        for w in desk["weeks"]:
            start = dt.date.fromisoformat(w["start"])
            self.assertEqual(common.week_label(start), w["week"])
            self.assertEqual(common.week_label(start + dt.timedelta(days=6)), w["week"])
            self.assertEqual(common.week_start(w["week"]), start)
            self.assertEqual(common.week_range_label(w["week"]), w["label"])

    def test_edition_due_monday_evening_only(self):
        tz = common.TZ
        monday_am = dt.datetime(2026, 11, 2, 7, tzinfo=tz)
        monday_pm = dt.datetime(2026, 11, 2, 19, tzinfo=tz)
        self.assertIsNone(close_week.due_week("2026-W44", monday_am))
        self.assertEqual(close_week.due_week("2026-W44", monday_pm), "2026-W45")
        self.assertIsNone(close_week.due_week("2026-W45", monday_pm))          # already published
        self.assertIsNone(close_week.due_week("2026-W42", dt.datetime(2026, 10, 26, 19, tzinfo=tz)))  # before W45


class Text(unittest.TestCase):
    def test_normalize_drops_scripts_nav_footer(self):
        text = html_to_text((FIX / "intercom_before.html").read_text())
        self.assertIn("$29 per seat/month billed annually", text)
        self.assertNotIn("var x", text)
        self.assertNotIn("Home Product", text)
        self.assertNotIn("©", text)
        self.assertTrue(looks_like_pricing(text))

    def test_numbers(self):
        self.assertEqual(common.numbers_in("$1,200 and 1.6K and $0.10"), {"1200", "1600", "0.1"})
        self.assertEqual(common.claimed_numbers("−34% to $19, ×2 in 2026"), {"19"})


class Debounce(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self._patch = (capture.SNAPSHOTS, capture.ROOT)
        capture.SNAPSHOTS, capture.ROOT = self.tmp / "data" / "snapshots", self.tmp

    def tearDown(self):
        capture.SNAPSHOTS, capture.ROOT = self._patch
        shutil.rmtree(self.tmp)

    def test_change_needs_two_captures(self):
        st = capture.blank_state()
        self.assertIsNone(capture.step_company(st, "x", "A $10/mo", None, "2026-10-26T07", "2026-10-26T07:00:00-04:00"))
        self.assertIsNone(capture.step_company(st, "x", "B $12/mo", "B $12/mo", "2026-10-26T19", "2026-10-26T19:00:00-04:00"))
        ev = capture.step_company(st, "x", "B $12/mo", "B $12/mo", "2026-10-27T07", "2026-10-27T07:00:00-04:00")
        self.assertIsNotNone(ev)
        self.assertEqual(ev["week"], "2026-W45")      # last old capture was Mon 26 Oct 07:00
        self.assertEqual(ev["first_new_at"], "2026-10-26T19:00:00-04:00")

    def test_one_off_glitch_is_ignored(self):
        st = capture.blank_state()
        capture.step_company(st, "x", "A", None, "r1", "2026-10-26T07:00:00-04:00")
        capture.step_company(st, "x", "glitch", "glitch", "r2", "2026-10-26T19:00:00-04:00")
        self.assertIsNone(capture.step_company(st, "x", "A", None, "r3", "2026-10-27T07:00:00-04:00"))
        self.assertEqual(st["pending_count"], 0)

    def test_flipping_page_is_reported_as_test(self):
        st = capture.blank_state()
        capture.step_company(st, "x", "A $29", None, "r0", "2026-10-26T07:00:00-04:00")
        evs = [capture.step_company(st, "x", "A $19", "A $29", f"r{i}", f"2026-10-2{6 + i}T19:00:00-04:00") for i in (1, 2, 3)]
        self.assertIsNone(evs[0])
        self.assertTrue(evs[2]["unstable"])


class Merge(unittest.TestCase):
    """The AI proposes; code decides."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self._root = ap.ROOT
        ap.ROOT = self.tmp
        snap = self.tmp / "snap"
        snap.mkdir()
        (snap / "before.txt").write_text(html_to_text((FIX / "intercom_before.html").read_text()))
        (snap / "after.txt").write_text(html_to_text((FIX / "intercom_after.html").read_text()))
        self.event = {"diff_id": "intercom-r1", "company": "intercom", "week": "2026-W45", "unstable": False,
                      "before_file": "snap/before.txt", "after_file": "snap/after.txt",
                      "last_old_at": "2026-10-26T07:00:00-04:00", "first_new_at": "2026-10-26T19:00:00-04:00"}
        self.desk = common.load_json(common.DESK)
        self.registry = {"companies": {"intercom": {
            "name": "Intercom", "tier": 2, "category": "Sales & Customer Relationship Management (CRM)",
            "pricing_urls": ["https://www.intercom.com/pricing"], "domains": ["intercom.com"], "status": "active"}}}

    def tearDown(self):
        ap.ROOT = self._root
        shutil.rmtree(self.tmp)

    def card(self, **over):
        rec = {"plan": "Essential seat", "group": "down", "delta": "−34%", "deltaSub": "entry seat, annual",
               "short": "Essential seat cut from $29 to $19 a month.", "headline": "Intercom cut its Essential seat.",
               "rows": [["Essential seat", "$29", "$19"], ["Advanced", "$85", "$85"]],
               "who": "New Essential buyers.", "stated": None, "statedUrl": None, "read": "Aimed at small teams.",
               "pattern": "Price cut", "seg": "B2B", "ai": False, "planLevel": "entry", "model": "Seat",
               "modelBefore": "Seat", "modelAfter": "Seat", "appliesTo": "new",
               "magnitude": {"low": -34, "high": -34, "basis": "list price"}, "reach": 3}
        rec.update(over)
        return {"diff_id": "intercom-r1", "kind": "price_cut", "detail": "card", "record": rec}

    def merge(self, item):
        result = {"added": [], "promos": [], "dropped": [], "rejected": [], "registry": []}
        ap.apply_changes(self.desk, self.registry, {"items": [item]}, {"changes": [self.event]}, result)
        return result

    def added(self, result):
        return next(c for c in self.desk["changes"] if c["id"] == result["added"][0])

    def test_traceable_card_is_accepted(self):
        r = self.merge(self.card())
        c = self.added(r)
        self.assertNotIn("detail", c)
        self.assertEqual((c["id"], c["tier"], c["week"], c["src"]), ("intercom-2026w45", 1, "2026-W45", common.SRC_CAPTURE))  # watchlist → tier 1 (D16)

    def test_invented_number_downgrades_card_to_line(self):
        r = self.merge(self.card(rows=[["Essential seat", "$29", "$17"]]))
        self.assertEqual(self.added(r)["detail"], "line")

    def test_invented_number_in_line_is_held_back(self):
        r = self.merge(self.card(rows=[["Essential seat", "$29", "$17"]], short="Seat cut from $29 to $17."))
        self.assertEqual(r["added"], [])
        self.assertIn("held back", r["rejected"][0]["why"])

    def test_stated_needs_company_site(self):
        r = self.merge(self.card(stated="We made it cheaper.", statedUrl="https://pricingsaas.com/x"))
        self.assertIsNone(self.added(r)["stated"])

    def test_drop_kind_and_promo(self):
        r = self.merge({"diff_id": "intercom-r1", "kind": "wording", "why": "copy"})
        self.assertEqual(len(r["dropped"]), 1)
        r = self.merge({"diff_id": "intercom-r1", "kind": "promo", "promo": {"kind": "new", "text": "Essential at $19 for now"}})
        self.assertEqual(len(r["promos"]), 1)

    def test_price_reveal_is_dropped(self):
        r = self.merge(self.card(rows=[["Essential seat", "Contact sales", "$19"]]))
        self.assertIn("price reveal", r["rejected"][0]["why"])

    def test_bad_enum_rejected(self):
        r = self.merge(self.card(pattern="Price slash"))
        self.assertIn("pattern", r["rejected"][0]["why"])


class Site(unittest.TestCase):
    def test_template_and_data(self):
        import build_site
        import validate
        self.assertEqual(validate.validate_desk(common.load_json(common.DESK)), [])
        html = build_site.render()
        self.assertNotIn("__PD_DATA__", html)
        self.assertIn('"current_week":', html)


if __name__ == "__main__":
    unittest.main()
