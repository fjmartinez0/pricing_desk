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

from common import DESK, ROOT, SITE, load_json, now

PLACEHOLDER = "__PD_DATA__"


def render() -> str:
    template = (SITE / "template.html").read_text(encoding="utf-8")
    if template.count(PLACEHOLDER) != 1:
        raise SystemExit("site/template.html must contain __PD_DATA__ exactly once")
    data = json.dumps(load_json(DESK), ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    return template.replace(PLACEHOLDER, data)


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
