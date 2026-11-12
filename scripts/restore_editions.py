"""Put every edition published before the archive (D56) back into desk.json, from git history.

Before 12 Nov 2026 desk.json held only the current edition's text, and each new edition replaced it. Every
published edition is still in the git history of data/desk.json: for each week this takes the last commit in
which that week was the current edition and stores its news, patterns, stats analysis and news trends under
editions[<week>] (format 1: paragraphs). Links to records that no longer exist are dropped. Weeks already in
the archive are left alone, so running it twice changes nothing.

Usage: python3 scripts/restore_editions.py [--dry-run]
"""
from __future__ import annotations

import argparse
import json
import subprocess

from common import DESK, ROOT, load_json, log, save_json, week_key
from desk import EDITION_TEXT


def history() -> dict[str, dict]:
    """week → desk.json of the last commit in which it was the current edition."""
    out = subprocess.run(["git", "log", "--format=%H", "--", "data/desk.json"], cwd=ROOT,
                         capture_output=True, text=True, check=True).stdout.split()
    found: dict[str, dict] = {}
    for h in out:                                  # newest first, so the first sighting is the final text
        text = subprocess.run(["git", "show", f"{h}:data/desk.json"], cwd=ROOT, capture_output=True, text=True)
        if text.returncode:
            continue
        d = json.loads(text.stdout)
        found.setdefault(d["current_week"], d)
    return found


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    desk = load_json(DESK)
    eds = desk.setdefault("editions", {})
    ids = {c["id"] for c in desk["changes"]}
    cur = desk["current_week"]
    past = history()
    past[cur] = desk                               # the current edition comes from the live file
    added = []
    for week, d in sorted(past.items(), key=lambda kv: week_key(kv[0])):
        if week in eds or week not in desk["week_order"] or not d.get("news"):
            continue
        ed = {"week": week, "edition_date": d.get("edition_date"), "period": d.get("period"), "format": 1,
              **{k: json.loads(json.dumps(d.get(k, []))) for k in EDITION_TEXT}}
        for section in ("patterns", "stats_analysis"):
            for item in ed[section]:
                item["ids"] = [i for i in item.get("ids", []) if i in ids]
            ed[section] = [item for item in ed[section] if item["ids"]]
        for t in ed["news_trends"]:
            t["changes"] = [i for i in t.get("changes", []) if i in ids]
        eds[week] = ed
        added.append(f"{week} ({len(ed['news'])} stories, {len(ed['patterns'])} patterns)")
    log("restore_editions: " + (", ".join(added) if added else "nothing to restore"))
    if added and not args.dry_run:
        save_json(DESK, desk)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
