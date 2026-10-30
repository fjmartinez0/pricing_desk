"""Build the published page: site/template.html with data/desk.json injected into pd-data.

The template is the dashboard exactly as designed, with its data block replaced
by the placeholder __PD_DATA__. Nothing else in the page is touched.

Usage:
  python3 scripts/build_site.py                 # writes _site/index.html (+ meta.json) for GitHub Pages
  python3 scripts/build_site.py --out preview.html   # a standalone preview you can open offline
"""
from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

from common import DESK, META, PS_DIR, REPORTS, ROOT, SITE, load_json, now, ps_period_week

PLACEHOLDER = "__PD_DATA__"


def render() -> str:
    template = (SITE / "template.html").read_text(encoding="utf-8")
    if template.count(PLACEHOLDER) != 1:
        raise SystemExit("site/template.html must contain __PD_DATA__ exactly once")
    desk = load_json(DESK)
    # "Last updated" on the page = the last pipeline run (data/meta.json), not stored in desk.json.
    desk["updated_at"] = (load_json(META, {}) or {}).get("last_run_at")
    desk["backfill"] = backfill_status()
    data = json.dumps(desk, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    return template.replace(PLACEHOLDER, data)


def backfill_status() -> dict:
    """Per week: PricingSaaS reports still waiting for a decision, and how many changes PricingSaaS listed
    (data/pricingsaas/feed/). Not stored in desk.json: it changes every run and is only shown on the page."""
    pending: dict[str, int] = {}
    for r in (load_json(REPORTS, {"reports": []}) or {}).get("reports", []):
        if r.get("status") in ("todo", "decided"):
            pending[r["week"]] = pending.get(r["week"], 0) + 1
    listed: dict[str, int] = {}
    for f in sorted((PS_DIR / "feed").glob("*.json")):
        week = ps_period_week(f.stem)[0]
        listed[week] = len((load_json(f, {}) or {}).get("rows", []))
    return {"pending": pending, "listed": listed}


def last_data_change() -> str | None:
    """Time of the last commit that touched data/ (the honest 'last updated')."""
    try:
        out = subprocess.run(["git", "log", "-1", "--format=%cI", "--", "data/desk.json"], cwd=ROOT,
                             capture_output=True, text=True, timeout=20)
        return out.stdout.strip() or None
    except Exception:
        return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", help="write a single preview file here instead of _site/")
    args = ap.parse_args()
    html = render()
    if args.out:
        Path(args.out).write_text(html, encoding="utf-8")
        print(f"wrote {args.out}")
        return 0
    out = ROOT / "_site"
    out.mkdir(exist_ok=True)
    (out / "index.html").write_text(html, encoding="utf-8")
    (out / "meta.json").write_text(json.dumps({"last_data_change": last_data_change(),
                                               "built_at": now().isoformat(timespec="seconds")}), encoding="utf-8")
    (out / ".nojekyll").write_text("", encoding="utf-8")
    print("wrote _site/index.html")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
