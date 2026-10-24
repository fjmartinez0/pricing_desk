"""Create or extend data/registry.json: every company in desk.json plus the watchlist.

Safe to re-run: existing registry entries are never overwritten, only missing
companies are added. Companies without a known pricing URL get status
"needs_url"; the registry agent proposes URLs for them, a batch each morning,
and capture.py verifies each URL on its first capture.

Usage: python3 scripts/seed_registry.py
"""
from __future__ import annotations

from collections import Counter

from common import DESK, REGISTRY, WATCHLIST, load_json, log, now, save_json

# Watchlist companies (D15): known pricing pages. They start as "candidate" and are
# verified on the first capture like any other URL.
WATCHLIST_SEED = {
    "notion": ("Notion", "Collaboration & Productivity", "Both", ["notion.com", "notion.so"], ["https://www.notion.com/pricing"]),
    "canva": ("Canva", None, "Both", ["canva.com"], ["https://www.canva.com/pricing/"]),
    "slack": ("Slack", "Collaboration & Productivity", "B2B", ["slack.com"], ["https://slack.com/pricing"]),
    "hubspot": ("HubSpot", None, "B2B", ["hubspot.com"], ["https://www.hubspot.com/pricing/marketing", "https://www.hubspot.com/pricing/sales"]),
    "figma": ("Figma", None, "B2B", ["figma.com"], ["https://www.figma.com/pricing/"]),
    "1password": ("1Password", "Cybersecurity & Identity Management", "Both", ["1password.com"], ["https://1password.com/pricing"]),
    "duolingo": ("Duolingo", "Collaboration & Productivity", "B2C", ["duolingo.com"], []),
    "zoom": ("Zoom", "Collaboration & Productivity", "Both", ["zoom.us", "zoom.com"], ["https://zoom.us/pricing"]),
    "atlassian": ("Atlassian", None, "B2B", ["atlassian.com"], ["https://www.atlassian.com/software/jira/pricing", "https://www.atlassian.com/software/confluence/pricing"]),
    "microsoft-365": ("Microsoft 365", "Collaboration & Productivity", "Both", ["microsoft.com"], ["https://www.microsoft.com/en-us/microsoft-365/business/compare-all-microsoft-365-business-products"]),
    "adobe": ("Adobe", "Marketing & Content", "Both", ["adobe.com"], ["https://www.adobe.com/creativecloud/plans.html"]),
    "openai": ("OpenAI", None, "Both", ["openai.com", "chatgpt.com"], ["https://openai.com/chatgpt/pricing/", "https://openai.com/api/pricing/"]),
    "linear": ("Linear", "Project Management", "B2B", ["linear.app"], ["https://linear.app/pricing"]),
    "airtable": ("Airtable", None, "B2B", ["airtable.com"], ["https://www.airtable.com/pricing"]),
    "calendly": ("Calendly", "Business Operations", "Both", ["calendly.com"], ["https://calendly.com/pricing"]),
    "dropbox": ("Dropbox", None, "Both", ["dropbox.com"], ["https://www.dropbox.com/plans"]),
    "salesforce": ("Salesforce", None, "B2B", ["salesforce.com"], ["https://www.salesforce.com/sales/pricing/"]),
    "intercom": ("Intercom", None, "B2B", ["intercom.com"], ["https://www.intercom.com/pricing"]),
    "zapier": ("Zapier", "Business Operations", "Both", ["zapier.com"], ["https://zapier.com/pricing"]),
    "grammarly": ("Grammarly", "Collaboration & Productivity", "Both", ["grammarly.com"], ["https://www.grammarly.com/plans"]),
}
assert set(WATCHLIST_SEED) == set(WATCHLIST)


def blank(name: str) -> dict:
    return {"name": name, "tier": 3, "category": None, "segment": None, "watch": False, "pricing_urls": [],
            "domains": [], "capture": "static", "status": "needs_url", "aiNative": None, "ownership": None,
            "hq": None, "funding": None, "employees": None, "ignore_patterns": [], "added": now().date().isoformat(),
            "source": "seed", "source_url": None, "url_attempts": 0, "notes": ""}


def main() -> int:
    desk = load_json(DESK)
    registry = load_json(REGISTRY, {"version": 1, "companies": {}})
    companies = registry["companies"]
    seg = {}
    for c in desk["changes"]:
        seg.setdefault(c["company"], Counter())[c["seg"]] += 1
    added = 0
    for slug, info in desk["companies"].items():
        if slug in companies:
            continue
        e = blank(info["name"])
        for k in ("tier", "category", "aiNative", "ownership", "hq", "funding", "employees"):
            e[k] = info.get(k)
        e["tier"] = e["tier"] or 3          # promo-only companies have no tier on the page
        if slug in seg:
            e["segment"] = seg[slug].most_common(1)[0][0]
        companies[slug] = e
        added += 1
    for slug, (name, category, segment, domains, urls) in WATCHLIST_SEED.items():
        e = companies.get(slug) or blank(name)
        if slug not in companies:
            added += 1
        e.update(tier=1, watch=True, segment=e.get("segment") or segment, domains=e["domains"] or domains)
        e["category"] = e.get("category") or category
        if not e["pricing_urls"] and urls and e["status"] == "needs_url":
            e.update(pricing_urls=urls, status="candidate")
        companies[slug] = e
    registry["companies"] = dict(sorted(companies.items()))
    save_json(REGISTRY, registry)
    log(f"seed_registry: {added} companies added, {len(companies)} total")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
