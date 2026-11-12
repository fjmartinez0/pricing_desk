"""Decide whether a weekly edition is due, and prepare the agent's input if so.

An edition covers one Monday–Sunday week. It is due when:
  * the previous week is later than desk.current_week and not before FIRST_AUTO_EDITION, and
  * at least EDITION_READY_AFTER has passed since the week ended (so Sunday changes are confirmed).
If the edition agent fails, nothing is published and the next run tries again.

When no edition is due, the run writes one catch-up edition instead (D56): the first week in EDITION_BACKFILL
whose stored edition is missing or older than EDITION_FORMAT and hasn't been rejected EDITION_BACKFILL_TRIES
times. A catch-up edition is archived under its week; it replaces the page's current edition only when it is
for the current week.

Writes .run/edition_due_<run>.json ({"week", "mode": "due"|"backfill"}), .run/week_stats_<run>.json and
.run/news_window_<run>.json (stories of the earlier editions, for Market Trends).
Exit code: 0 = an edition to write (files written), 10 = nothing to write.

Usage: python3 scripts/close_week.py [--force-week 2026-W45]
"""
from __future__ import annotations

import argparse
import datetime as dt

from common import (DESK, EDITION_BACKFILL, EDITION_BACKFILL_STATE, EDITION_BACKFILL_TRIES, EDITION_FORMAT,
                    EDITION_READY_AFTER, FIRST_AUTO_EDITION, RUN, TZ, load_json, log, now, run_id, save_json, week_key,
                    week_label, week_start)
from desk import news_window, week_stats

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


def backfill_week(desk: dict, tries: dict) -> str | None:
    """The next catch-up edition to write, or None when the list is done."""
    weeks = {c["week"] for c in desk["changes"]}
    for w in EDITION_BACKFILL:
        stored = (desk.get("editions") or {}).get(w) or {}
        if (w in weeks and stored.get("format", 1) < EDITION_FORMAT and tries.get(w, 0) < EDITION_BACKFILL_TRIES
                and week_key(w) <= week_key(desk["current_week"])):
            return w
    return None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--force-week", help="prepare this week even if not due (for testing)")
    args = ap.parse_args()
    desk = load_json(DESK)
    week, mode = args.force_week or due_week(desk["current_week"], now()), "due"
    if not week:
        week, mode = backfill_week(desk, load_json(EDITION_BACKFILL_STATE, {}) or {}), "backfill"
    if not week:
        return NOT_DUE
    save_json(RUN / f"edition_due_{run_id()}.json", {"week": week, "mode": mode})
    save_json(RUN / f"week_stats_{run_id()}.json", week_stats(desk, week))
    save_json(RUN / f"news_window_{run_id()}.json", {"week": week, "news": news_window(desk, week)})
    log(f"edition {'due' if mode == 'due' else 'catch-up'} for {week}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
