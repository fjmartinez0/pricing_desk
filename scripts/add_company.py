"""Manually add a company, or fix one's pricing URL (manual add tool).

Examples:
  python3 scripts/add_company.py --name "Loom" --url https://www.loom.com/pricing --category "Collaboration & Productivity"
  python3 scripts/add_company.py --slug duolingo --url https://www.duolingo.com/super --domain duolingo.com
  python3 scripts/add_company.py --slug notion --browser          # force browser capture
  python3 scripts/add_company.py --slug psychz --status paused

A new or changed URL becomes "candidate" and is verified on the next capture.
"""
from __future__ import annotations

import argparse

from apply_proposals import slugify
from common import CAPTURE_MODES, DESK, REGISTRY, REGISTRY_STATUS, domain_of, load_json, save_json
from seed_registry import blank


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--slug")
    ap.add_argument("--name")
    ap.add_argument("--url", action="append", help="pricing page URL (repeat for several)")
    ap.add_argument("--domain", action="append", help="company domain(s); defaults to the URL's domain")
    ap.add_argument("--category")
    ap.add_argument("--tier", type=int, choices=[1, 2, 3])
    ap.add_argument("--segment", choices=["B2B", "B2C", "Both"])
    ap.add_argument("--browser", action="store_true", help="capture with the browser")
    ap.add_argument("--status", choices=sorted(REGISTRY_STATUS))
    a = ap.parse_args()

    registry = load_json(REGISTRY)
    companies = registry["companies"]
    slug = a.slug or (slugify(a.name) if a.name else None)
    if not slug:
        ap.error("give --slug or --name")
    if slug not in companies:
        if not a.name:
            ap.error(f"{slug} is not in the registry; give --name to add it")
        companies[slug] = blank(a.name)
        companies[slug]["source"] = "manual"
    e = companies[slug]
    if a.category:
        cats = {c["name"] for c in load_json(DESK)["categories"]}
        if a.category not in cats:
            ap.error(f"category must be one of: {', '.join(sorted(cats))}")
        e["category"] = a.category
    if a.url:
        e["pricing_urls"] = a.url
        e["domains"] = a.domain or sorted({domain_of(u) for u in a.url})
        e["status"] = "candidate"
        e["url_attempts"] = 0
    for field, value in (("tier", a.tier), ("segment", a.segment), ("status", a.status)):
        if value is not None:
            e[field] = value
    if a.browser:
        e["capture"] = "browser"
    assert e["capture"] in CAPTURE_MODES
    save_json(REGISTRY, registry)
    print(f"{slug}: {e['status']}, {e['capture']}, {', '.join(e['pricing_urls']) or 'no URL yet'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
