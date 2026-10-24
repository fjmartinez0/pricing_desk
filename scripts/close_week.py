"""Decide whether a weekly edition is due, and prepare the agent's input if so.

An edition covers one Monday–Sunday week. It is due when:
  * the previous week is later than desk.current_week and not before FIRST_AUTO_EDITION, and
  * at least EDITION_READY_AFTER has passed since the week ended (so Sunday changes are confirmed).
If the edition agent fails, nothing is published and the next run tries again.

Writes .run/edition_due_<run>.json and .run/week_stats_<run>.json.
Exit code: 0 = due (files written), 10 = not due.

Usage: python3 scripts/close_week.py [--force-week 2026-W45]
"""
from __future__ import annotations

import argparse
import datetime as dt

from common import DESK, EDITION_READY_AFTER, FIRST_AUTO_EDITION, RUN, TZ, load_json, log, now, run_id, save_json, week_key, week_label, week_start
from desk import week_stats

NOT_DUE = 10


def due_week(current_week: str, at: dt.datetime) -> str | None:
    this_week = week_label(at.date())
    previous = week_label(at.date() - dt.timedelta(days=7))
    week_end = dt.datetime.combine(week_start(this_week), dt.time(0), TZ)
    if at < week_end + EDITION_READY_AFTER:
        return None
    if week_key(previous) <= week_key(current_week) or week_key(previous) < week_key(FIRST_AUTO_EDITION):
        return None
    return previous


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--force-week", help="prepare this week even if not due (for testing)")
    args = ap.parse_args()
    desk = load_json(DESK)
    week = args.force_week or due_week(desk["current_week"], now())
    if not week:
        return NOT_DUE
    save_json(RUN / f"edition_due_{run_id()}.json", {"week": week})
    save_json(RUN / f"week_stats_{run_id()}.json", week_stats(desk, week))
    log(f"edition due for {week}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
