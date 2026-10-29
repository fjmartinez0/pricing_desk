"""Unit tests on known cases. Run: python3 -m unittest discover -s tests -v"""
from __future__ import annotations

import datetime as dt
import json
import os
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
import desk as desk_mod  # noqa: E402
import pricingsaas_capture as ps  # noqa: E402
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

    def test_edition_due_tuesday_evening_only(self):
        tz = common.TZ
        monday_pm = dt.datetime(2026, 11, 2, 19, tzinfo=tz)
        tuesday_am = dt.datetime(2026, 11, 3, 7, tzinfo=tz)
        tuesday_pm = dt.datetime(2026, 11, 3, 19, tzinfo=tz)
        self.assertIsNone(close_week.due_week("2026-W44", monday_pm))          # PricingSaaS batch still arriving
        self.assertIsNone(close_week.due_week("2026-W44", tuesday_am))
        self.assertEqual(close_week.due_week("2026-W44", tuesday_pm), "2026-W45")
        self.assertIsNone(close_week.due_week("2026-W45", tuesday_pm))         # already published
        self.assertIsNone(close_week.due_week("2026-W42", dt.datetime(2026, 10, 26, 19, tzinfo=tz)))  # too early
        self.assertEqual(close_week.due_week("2026-W42", dt.datetime(2026, 10, 27, 19, tzinfo=tz)), "2026-W44")  # first auto
        self.assertIsNone(close_week.due_week("2026-W42", dt.datetime(2026, 10, 20, 19, tzinfo=tz)))  # W43: before W44


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

    def test_reapplied_proposal_adds_nothing(self):
        self.merge(self.card())
        n = len(self.desk["changes"])
        r = self.merge(self.card())                       # --recover on a run that was partly applied
        self.assertEqual((r["added"], len(self.desk["changes"])), ([], n))

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


class PricingSaaSPages(unittest.TestCase):
    """Reading PricingSaaS (hybrid, D39): links, periods, page text."""

    def test_links_are_canonical_and_filtered(self):
        links = ps.parse_links((FIX / "ps_review.html").read_text())
        self.assertEqual(links, [
            "https://pricingsaas.com/news/article/shopify-raises-annual-grow-to-89-mo-advanced-to-359-mo",
            "https://pricingsaas.com/companies/shopify/diffs/2026W43",
            "https://pricingsaas.com/companies/shopify/diffs/2026D288",
            "https://pricingsaas.com/companies/atlassian.bitbucket/diffs/2026W43",
            "https://pricingsaas.com/companies/intercom/diffs/2026W36"])
        self.assertEqual(ps.diff_week(links[4]), "2026-W36")      # the review keeps only its own week

    def test_periods(self):
        self.assertEqual(common.ps_period_week("2026W43"), ("2026-W43", None))
        self.assertEqual(common.ps_period_week("2026D294"), ("2026-W44", dt.date(2026, 10, 21)))  # Oct 20 → 21
        self.assertEqual(common.ps_period_week("2026D292")[0], "2026-W43")   # Mon 19 Oct: old page last seen Sun 18 (D28)
        today = dt.date(2026, 10, 24)
        self.assertFalse(ps.weekly_page_final("2026W44", today))           # week still running: defer
        self.assertTrue(ps.weekly_page_final("2026W43", today))
        self.assertTrue(ps.weekly_page_final("2026D296", today))

    def test_diff_text_is_cut_to_this_change(self):
        from normalize import html_to_text
        html = (FIX / "ps_diff.html").read_text()
        text = ps.cut_text(html_to_text(html))
        self.assertIn("$7.25", text)
        self.assertNotIn("9.05", text)          # history of older changes is cut
        self.assertNotIn("ClickUp", text)       # peers are cut
        self.assertEqual(ps.title_of(html), "Atlassian raises Bitbucket Premium to $8")
        self.assertEqual(ps.meta(html, "article:published_time"), "2026-10-15T06:10:00+00:00")

    def test_reports_group_by_company_and_week(self):
        q = {"reports": []}
        a = ps.queue_report(q, "https://pricingsaas.com/companies/shopify/diffs/2026D288", "f1", [], "t", "r1")
        b = ps.queue_report(q, "https://pricingsaas.com/companies/shopify/diffs/2026W43", "f2", ["a1"], "t", "r1")
        self.assertEqual((a, b), ("shopify:2026-W43", "shopify:2026-W43"))
        self.assertEqual(q["reports"][0]["files"], ["f1", "f2"])
        self.assertEqual(ps.queue_report(q, "https://pricingsaas.com/companies/shopify/diffs/2026W43", "f2", [], "t", "r2"), "known")
        q["reports"][0]["status"] = "done"
        c = ps.queue_report(q, "https://pricingsaas.com/companies/shopify/diffs/2026D289", "f3", [], "t", "r3")
        self.assertEqual(c, "shopify:2026-W43#2")    # after the decision: a follow-up report


class PricingSaaSFeed(unittest.TestCase):
    """The move explorer (/feed): every row comes from the embedded data, not only the 50 the table shows."""

    def setUp(self):
        self.html = (FIX / "ps_feed.html").read_text()
        self.tmp = Path(tempfile.mkdtemp())
        self._saved = ps.PS_DIR
        ps.PS_DIR = self.tmp

    def tearDown(self):
        ps.PS_DIR = self._saved
        shutil.rmtree(self.tmp)

    def test_rows_from_embedded_data(self):
        rows = ps.feed_rows(self.html)
        self.assertEqual([r["slug"] for r in rows], ["example", "sample.api"])   # bad slug dropped, duplicate once
        self.assertEqual(rows[0]["detail"], 'Example Co raises Pro from $10 to "$12"')
        self.assertNotIn("logo", rows[0])

    def test_links_rows_first_then_markup(self):
        self.assertEqual(ps.feed_links(self.html), [
            "https://pricingsaas.com/companies/example/diffs/2026W43",
            "https://pricingsaas.com/companies/sample.api/diffs/2026W43",
            "https://pricingsaas.com/companies/other/diffs/2026W43"])

    def test_row_list_is_kept_and_merged(self):
        rows = ps.feed_rows(self.html)
        self.assertEqual(ps.save_feed_rows(rows[:1]), {"2026W43": 1})
        self.assertEqual(ps.save_feed_rows(rows), {"2026W43": 2})
        self.assertEqual(ps.save_feed_rows(rows), {"2026W43": 2})          # reading it again adds nothing

    def test_page_without_data(self):
        self.assertEqual(ps.feed_rows("<html><body>Sign in</body></html>"), [])

    TABLE = ('<table><tr data-slot="table-row"><td><time datetime="2026-09-14T01:15:22+00:00">Sep 14, 2026</time></td>'
             '<td><span><div>C<img src="x.png" alt="Casemark &amp; Co"></div>Casemark</span></td>'
             '<td><span>●</span><span>Limit increase +2</span></td><td>Casemark reveals $200/user pricing</td>'
             '<td>—</td><td><a href="/companies/casemark/diffs/2026W38">View</a></td></tr>'
             '<tr data-slot="table-row"><td>x</td><td>Example Co</td><td>Price increase</td><td>dup of the data row</td>'
             '<td>$10 → $12</td><td><a href="/companies/example/diffs/2026W43">View</a></td></tr></table>')

    def test_table_rows_from_saved_full_history(self):
        rows = ps.table_rows(self.TABLE)
        self.assertEqual(rows[0], {"at": "2026-09-14T01:15:22+00:00", "company": "Casemark & Co", "slug": "casemark",
                                   "period": "2026W38", "change": "Limit increase +2",
                                   "detail": "Casemark reveals $200/user pricing", "move": "", "category": None, "url": None})
        both = ps.all_feed_rows(self.html + self.TABLE)
        self.assertEqual([(r["slug"], r["period"]) for r in both],
                         [("example", "2026W43"), ("sample.api", "2026W43"), ("casemark", "2026W38")])
        self.assertEqual(both[0]["category"], "Developer Tools")      # the embedded row wins

    def test_manual_import_waits_for_a_running_run(self):
        saved = ps.RUN
        ps.RUN = self.tmp / ".run"
        try:
            (ps.RUN / "lock").mkdir(parents=True)
            argv, sys.argv = sys.argv, ["pricingsaas_capture.py", "--feed-file", str(FIX / "ps_feed.html")]
            try:
                self.assertEqual(ps.main(), 1)
            finally:
                sys.argv = argv
            self.assertTrue((ps.RUN / "lock").exists())                # the run's lock is left alone
        finally:
            ps.RUN = saved


class ReportParts(unittest.TestCase):
    """Reports go to the agent in parts; only answered parts count (D46)."""

    def setUp(self):
        import prepare_reports as pr
        self.pr = pr
        self.tmp = Path(tempfile.mkdtemp())
        (self.tmp / "proposals").mkdir()
        self._saved = (pr.PROPOSALS, pr.REPORTS, pr.REGISTRY, pr.RUN, pr.REPORTS_BATCH, pr.REPORTS_PARTS,
                       common.RUN, common.CHECKS, os.environ.get("PD_RUN_ID"))
        pr.PROPOSALS, pr.REPORTS, pr.REGISTRY = self.tmp / "proposals", self.tmp / "reports.json", self.tmp / "registry.json"
        pr.RUN = common.RUN = self.tmp / ".run"
        common.CHECKS = self.tmp / "checks.jsonl"
        pr.REPORTS_BATCH, pr.REPORTS_PARTS = 2, 2
        os.environ["PD_RUN_ID"] = "2026-10-26T07"
        common.save_json(pr.REGISTRY, {"companies": {}})
        common.save_json(pr.REPORTS, {"reports": [
            {"report_id": f"c{i}:2026-W43", "ps_slug": f"c{i}", "week": "2026-W43", "change_date": None,
             "urls": [], "files": [], "article_files": [], "title": "", "status": "todo"} for i in range(5)]})

    def tearDown(self):
        pr = self.pr
        (pr.PROPOSALS, pr.REPORTS, pr.REGISTRY, pr.RUN, pr.REPORTS_BATCH, pr.REPORTS_PARTS,
         common.RUN, common.CHECKS, rid) = self._saved
        if rid is None:
            os.environ.pop("PD_RUN_ID", None)
        else:
            os.environ["PD_RUN_ID"] = rid
        shutil.rmtree(self.tmp)

    def test_split_and_merge_answered_parts_only(self):
        pr, P = self.pr, self.tmp / "proposals"
        self.assertEqual(pr.main([]), 0)
        parts = sorted(f.name for f in P.glob("*.reports_input.*.json"))
        self.assertEqual(parts, ["2026-10-26T07.reports_input.0.json", "2026-10-26T07.reports_input.1.json"])
        first = [r["report_id"] for r in common.load_json(P / parts[0])["reports"]]
        common.save_json(P / "2026-10-26T07.reports.0.json",
                         {"type": "reports", "items": [{"report_id": first[0], "kind": "wording"}]})
        (P / "2026-10-26T07.reports.1.json").write_text("{not json")
        self.assertEqual(pr.main(["--merge"]), 0)
        handed = [r["report_id"] for r in common.load_json(P / "2026-10-26T07.reports_input.json")["reports"]]
        self.assertEqual(handed, first)                   # part 1 was not answered: it costs no attempt
        self.assertEqual(len(common.load_json(P / "2026-10-26T07.reports.json")["items"]), 1)
        self.assertEqual(sorted(f.name for f in P.iterdir()),
                         ["2026-10-26T07.reports.json", "2026-10-26T07.reports_input.json"])

    def test_nothing_answered_writes_nothing(self):
        pr, P = self.pr, self.tmp / "proposals"
        pr.main([])
        pr.main(["--merge"])
        self.assertEqual(list(P.iterdir()), [])


class Reports(unittest.TestCase):
    """PricingSaaS reports (D40–D41): the agent proposes, code decides."""

    def setUp(self):
        from normalize import html_to_text
        self.tmp = Path(tempfile.mkdtemp())
        self._saved = (ap.ROOT, ap.REPORTS, ap.SNAPSHOTS, common.RUN, common.CHECKS)
        ap.ROOT, ap.REPORTS, ap.SNAPSHOTS = self.tmp, self.tmp / "reports.json", self.tmp / "snap"
        common.RUN, common.CHECKS = self.tmp / ".run", self.tmp / "checks.jsonl"
        (self.tmp / "p").mkdir()
        (self.tmp / "p" / "diff.txt").write_text(ps.cut_text(html_to_text((FIX / "ps_diff.html").read_text())))
        self.desk = common.load_json(common.DESK)
        self.registry = {"companies": {"atlassian": {
            "name": "Atlassian", "tier": 1, "category": "Project Management", "pricing_urls": ["https://www.atlassian.com/software/bitbucket/pricing"],
            "domains": ["atlassian.com"], "status": "active"}}}
        self.report = {"report_id": "atlassian.bitbucket:2026-W44", "ps_slug": "atlassian.bitbucket", "week": "2026-W44",
                       "change_date": "2026-10-21", "urls": ["https://pricingsaas.com/companies/atlassian.bitbucket/diffs/2026D294"],
                       "files": ["p/diff.txt"], "article_files": [], "status": "todo", "attempts": 1, "waits": 0}
        common.save_json(ap.REPORTS, {"reports": [self.report]})

    def tearDown(self):
        ap.ROOT, ap.REPORTS, ap.SNAPSHOTS, common.RUN, common.CHECKS = self._saved
        shutil.rmtree(self.tmp)

    def item(self, **over):
        rec = {"plan": "Bitbucket Premium", "group": "up", "delta": "+10%", "deltaSub": "per user, monthly",
               "short": "Bitbucket Premium rises from $7.25 to $8 per user a month.",
               "headline": "Atlassian raised Bitbucket Premium.", "rows": [["Premium, per user per month", "$7.25", "$8"]],
               "who": "Bitbucket Premium teams.", "stated": None, "statedUrl": None, "read": "A small list-price step.",
               "pattern": "Price increase", "seg": "B2B", "ai": False, "planLevel": "mid", "model": "Seat",
               "modelBefore": "Seat", "modelAfter": "Seat", "appliesTo": "all",
               "magnitude": {"low": 10, "high": 10, "basis": "list price"}, "reach": 2}
        if "record" in over and over["record"] is None:
            rec = over.pop("record")
        else:
            rec.update(over.pop("record", {}))
        it = {"report_id": "atlassian.bitbucket:2026-W44", "company": "atlassian", "kind": "price_increase",
              "why": "Premium up", "detail": "card", "record": rec, "promo": None}
        it.update(over)
        return it

    def merge(self, item=None):
        result = {"added": [], "promos": [], "dropped": [], "rejected": [], "registry": []}
        ap.apply_reports(self.desk, self.registry, {"items": [item]} if item else None, result)
        return result

    def stored(self):
        return common.load_json(ap.REPORTS)["reports"][0]

    def test_report_at_untracked_company_is_published_as_reported(self):
        r = self.merge(self.item())
        c = next(x for x in self.desk["changes"] if x["id"] == r["added"][0])
        self.assertEqual((c["src"], c["reported"], c["week"], c["tier"], c["when"]),
                         (common.SRC_REPORTED, True, "2026-W44", 1, "21 Oct"))
        self.assertTrue(c["url"].startswith("https://pricingsaas.com/"))
        self.assertNotIn("detail", c)
        self.assertEqual(self.registry["companies"]["atlassian"]["ps_slugs"], ["atlassian.bitbucket"])
        self.assertIn("2026-W44", self.desk["week_order"])
        d = {"week_order": [], "weeks": []}                        # a week first created by a report, before
        desk_mod.ensure_week(d, "2026-W30", reported=True)        # automatic editions, gets a coverage note
        self.assertEqual(d["weeks"][0]["coverage"], "partial")
        import validate
        self.assertEqual(validate.validate_desk(self.desk), [])

    def test_own_record_in_same_week_does_not_break_the_merge(self):
        own = dict(next(c for c in self.desk["changes"] if not c.get("reported")))
        own.update(id="atlassian-2026w44-own", company="atlassian", week="2026-W44")
        own.pop("reported", None)                         # our own captures carry no "reported" key
        self.desk["changes"].append(own)
        r = self.merge(self.item())                       # crashed with TypeError before 29 Oct
        self.assertEqual(len(r["added"]), 1)

    def test_failed_merge_puts_backlog_and_reports_back(self):
        saved = (ap.BACKLOG, ap.merge)
        ap.BACKLOG = self.tmp / "backlog.json"
        common.save_json(ap.BACKLOG, {"changes": [{"diff_id": "x"}]})
        before = (ap.BACKLOG.read_bytes(), ap.REPORTS.read_bytes())

        def broken(run, recovering=False):
            common.save_json(ap.BACKLOG, {"changes": []})
            common.save_json(ap.REPORTS, {"reports": []})
            raise TypeError("boom")
        ap.merge = broken
        argv, sys.argv = sys.argv, ["apply_proposals.py", "--run", "2026-10-28T07"]
        try:
            with self.assertRaises(TypeError):
                ap.main()
            self.assertEqual((ap.BACKLOG.read_bytes(), ap.REPORTS.read_bytes()), before)
        finally:
            sys.argv = argv
            ap.BACKLOG, ap.merge = saved

    def test_number_not_in_report_is_held_back(self):
        r = self.merge(self.item(record={"rows": [["Premium", "$7.25", "$9"]], "short": "Premium rises to $9."}))
        self.assertEqual(r["added"], [])
        self.assertTrue(self.stored()["outcome"].startswith("rejected: held back"))

    def test_history_numbers_are_not_evidence(self):
        r = self.merge(self.item(record={"rows": [["Jira Standard", "$9.05", "$9.50"]], "short": "Jira from $9.05 to $9.50."}))
        self.assertEqual(r["added"], [])

    def test_new_company_is_added_to_registry(self):
        self.report.update(report_id="tailscale:2026-W44", ps_slug="tailscale")
        common.save_json(ap.REPORTS, {"reports": [self.report]})
        it = self.item(report_id="tailscale:2026-W44", company=None, detail="line",
                       new_company={"name": "Tailscale", "category": "Cybersecurity & Identity Management", "segment": "B2B",
                                    "pricing_urls": ["https://tailscale.com/pricing"], "domains": ["tailscale.com"]})
        r = self.merge(it)
        self.assertEqual(self.registry["companies"]["tailscale"]["status"], "candidate")
        self.assertEqual(len(r["added"]), 1)

    def test_tracked_company_waits_for_our_capture_then_publishes(self):
        snap = ap.SNAPSHOTS / "atlassian"
        snap.mkdir(parents=True)
        (snap / "2026-10-19T07.txt").write_text("baseline")      # we captured it before the change
        r = self.merge(self.item())
        self.assertEqual(r["added"], [])
        self.assertEqual(self.stored()["waits"], 1)
        for _ in range(common.REPORT_WAIT_RUNS):
            r = self.merge()
        self.assertEqual(len(r["added"]), 1)                     # our capture never saw it: published + problem
        problems = (common.RUN / f"problems_{common.run_id()}.jsonl").read_text()
        self.assertIn("didn't record", problems)

    def test_our_own_record_wins(self):
        snap = ap.SNAPSHOTS / "atlassian"
        snap.mkdir(parents=True)
        (snap / "2026-10-19T07.txt").write_text("baseline")
        self.merge(self.item())
        self.desk["changes"].append({"id": "atlassian-2026w44", "company": "atlassian", "week": "2026-W44",
                                     "src": common.SRC_CAPTURE})
        r = self.merge()
        self.assertEqual(r["added"], [])
        self.assertTrue(self.stored()["outcome"].startswith("corroborates"))

    def test_hand_built_week_is_not_duplicated(self):
        self.report.update(report_id="cursor:2026-W43", ps_slug="cursor", week="2026-W43", change_date=None)
        common.save_json(ap.REPORTS, {"reports": [self.report]})
        self.registry["companies"]["cursor"] = {"name": "Cursor", "tier": 2, "category": "AI & Machine Learning",
                                                "pricing_urls": [], "domains": ["cursor.com"], "status": "needs_url"}
        r = self.merge(self.item(report_id="cursor:2026-W43", company="cursor"))
        self.assertEqual(r["added"], [])
        self.assertIn("hand-built", self.stored()["outcome"])

    def test_attempts_count_only_when_the_agent_answered(self):
        handed = {"atlassian.bitbucket:2026-W44"}
        result = {"added": [], "promos": [], "dropped": [], "rejected": [], "registry": []}
        ap.apply_reports(self.desk, self.registry, None, result, handed)            # agent never ran (usage limit)
        self.assertEqual(self.stored()["attempts"], 1)
        ap.apply_reports(self.desk, self.registry, {"items": []}, result, handed)   # agent answered, skipped it
        self.assertEqual(self.stored()["attempts"], 2)

    def test_backlog_waits_when_the_agent_did_not_run(self):
        saved = ap.BACKLOG
        ap.BACKLOG = self.tmp / "backlog.json"
        try:
            common.save_json(ap.BACKLOG, {"changes": [{"diff_id": "x-r1", "attempts": 0, "after_file": "f"}]})
            result = {"rejected": []}
            for _ in range(6):
                ap.update_backlog(None, result)
            self.assertEqual(common.load_json(ap.BACKLOG)["changes"][0]["attempts"], 0)
            for _ in range(common.BACKLOG_MAX_ATTEMPTS):
                ap.update_backlog({"items": []}, result)
            self.assertEqual(common.load_json(ap.BACKLOG)["changes"], [])        # skipped 4 times: given up
        finally:
            ap.BACKLOG = saved

    def test_drop_kind(self):
        r = self.merge(self.item(kind="price_reveal", record=None))
        self.assertEqual(len(r["dropped"]), 1)


class Site(unittest.TestCase):
    def test_template_and_data(self):
        import build_site
        import validate
        self.assertEqual(validate.validate_desk(common.load_json(common.DESK)), [])
        html = build_site.render()
        self.assertNotIn("__PD_DATA__", html)
        self.assertIn('"current_week":', html)
        self.assertIn('"updated_at":', html)              # "Updated …" line comes from data/meta.json


if __name__ == "__main__":
    unittest.main()
