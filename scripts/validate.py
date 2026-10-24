"""Integrity rules for data/desk.json and data/registry.json.

Runs at the end of every local run (a failure stops the commit) and again in
GitHub Actions before publishing (a failure stops the deploy), so a bad edit
can never go live. Exit code 1 lists every problem found.

Usage: python3 scripts/validate.py
"""
from __future__ import annotations

import sys
from collections import Counter

from common import (AGGREGATOR_DOMAINS, APPLIES_TO, CAPTURE_MODES, DESK, GROUPS, MAX_ROWS, PATTERNS, PLAN_LEVELS,
                    PROMO_KINDS, REGISTRY, REGISTRY_STATUS, SEGMENTS, SRC_CAPTURE, SRC_REPORTED, TIERS, WATCHLIST, domain_of, is_http_url,
                    load_json, week_key)

REQUIRED_TOP = ["current_week", "today", "edition_date", "period", "week_order", "weeks", "tiers", "pattern_cats",
                "categories", "changes", "companies", "promos", "news", "patterns", "stats_analysis",
                "news_trends", "market_context"]
PROSE = ["short", "headline", "who", "read", "caveat", "stated"]


def validate_desk(d: dict) -> list[str]:
    errs = [f"missing top-level key {k}" for k in REQUIRED_TOP if k not in d]
    if errs:
        return errs
    order = d["week_order"]
    if order != sorted(order, key=week_key, reverse=True) or len(set(order)) != len(order):
        errs.append("week_order must be unique and newest first")
    if set(order) != {w["week"] for w in d["weeks"]}:
        errs.append("week_order and weeks[] list different weeks")
    if d["current_week"] not in order:
        errs.append("current_week is not in week_order")

    ids = Counter(c.get("id") for c in d["changes"])
    errs += [f"duplicate change id {i}" for i, n in ids.items() if n > 1]
    ranks = Counter((c.get("week"), c.get("rank")) for c in d["changes"])
    errs += [f"duplicate rank {r} in {w}" for (w, r), n in ranks.items() if n > 1]
    for c in d["changes"]:
        cid = c.get("id")
        def bad(msg):
            errs.append(f"{cid}: {msg}")
        if c.get("week") not in order:
            bad("week not in week_order")
        if c.get("company") not in d["companies"]:
            bad("company not in companies")
        if c.get("group") not in GROUPS:
            bad(f"group {c.get('group')!r}")
        if c.get("seg") not in SEGMENTS:
            bad(f"seg {c.get('seg')!r}")
        if c.get("planLevel") not in PLAN_LEVELS:
            bad(f"planLevel {c.get('planLevel')!r}")
        if c.get("pattern") not in PATTERNS:
            bad(f"pattern {c.get('pattern')!r}")
        if c.get("tier") not in TIERS:
            bad(f"tier {c.get('tier')!r}")
        if not isinstance(c.get("rank"), int) or c["rank"] < 1:
            bad("rank must be a positive integer")
        ours = c.get("src") in (SRC_CAPTURE, SRC_REPORTED)   # records before automation were built by hand: looser rules
        if not is_http_url(c.get("url")) and (ours or c.get("url") is not None):
            bad("url must be http(s)")
        if c.get("src") == SRC_REPORTED and (domain_of(c.get("url") or "") != "pricingsaas.com" or not c.get("reported")):
            bad("a PricingSaaS report must link its PricingSaaS diff page and be marked reported")
        if c.get("src") == SRC_CAPTURE and domain_of(c.get("url") or "") in AGGREGATOR_DOMAINS:
            bad("our own capture can't point to an aggregator")
        for f in PROSE:
            if isinstance(c.get(f), str) and ("http://" in c[f] or "https://" in c[f]):
                bad(f"{f} contains a URL")
        if c.get("detail") == "line":
            continue
        rows = c.get("rows")
        max_rows = MAX_ROWS if ours else 8
        if not (isinstance(rows, list) and 1 <= len(rows) <= max_rows and all(len(r) == 3 for r in rows)):
            bad(f"rows must be 1–{max_rows} rows of [label, before, after]")
        if c.get("appliesTo") not in APPLIES_TO:
            bad(f"appliesTo {c.get('appliesTo')!r}")
        for f in ("plan", "headline", "who", "read"):
            if not c.get(f):
                bad(f"full card missing {f}")
        if c.get("stated") and ours and not is_http_url(c.get("statedUrl")):
            bad("stated needs statedUrl")
        m = c.get("magnitude")
        if m is not None and not (isinstance(m, dict) and {"low", "high", "basis"} <= set(m)):
            bad("magnitude must be {low, high, basis} or null")

    pids = Counter(p.get("id") for p in d["promos"])
    errs += [f"duplicate promo id {i}" for i, n in pids.items() if n > 1]
    for p in d["promos"]:
        if p.get("week") not in order or p.get("kind") not in PROMO_KINDS or p.get("company") not in d["companies"]:
            errs.append(f"promo {p.get('id')}: bad week, kind or company")

    current = {c["id"] for c in d["changes"] if c["week"] == d["current_week"]}
    for section in ("patterns", "stats_analysis"):
        for item in d[section]:
            missing = set(item.get("ids", [])) - current
            if missing:
                errs.append(f"{section} '{item.get('t')}' points outside the current week: {sorted(missing)}")
    news_ids = {n["id"] for n in d["news"]}
    for n in d["news"]:
        if not is_http_url(n.get("url")):
            errs.append(f"news {n.get('id')}: url must be http(s)")
    for t in d["news_trends"]:
        if set(t.get("news", [])) - news_ids or set(t.get("changes", [])) - set(ids):
            errs.append(f"news_trends '{t.get('t')}' points to missing news or changes")
    return errs


def validate_registry(r: dict) -> list[str]:
    errs = []
    for slug, e in r.get("companies", {}).items():
        if e.get("status") not in REGISTRY_STATUS:
            errs.append(f"registry {slug}: status {e.get('status')!r}")
        if e.get("capture") not in CAPTURE_MODES:
            errs.append(f"registry {slug}: capture {e.get('capture')!r}")
        urls = e.get("pricing_urls") or []
        if e.get("status") in ("active", "candidate") and not urls:
            errs.append(f"registry {slug}: {e['status']} without pricing_urls")
        for u in urls:
            if not is_http_url(u) or domain_of(u) in AGGREGATOR_DOMAINS:
                errs.append(f"registry {slug}: bad pricing url {u}")
        if slug in WATCHLIST and e.get("tier") != 1:
            errs.append(f"registry {slug}: watchlist companies are tier 1")
    return errs


def main() -> int:
    errs = validate_desk(load_json(DESK)) + validate_registry(load_json(REGISTRY, {"companies": {}}))
    for e in errs:
        print(f"INVALID: {e}")
    print(f"validate: {'OK' if not errs else str(len(errs)) + ' problems'}")
    return 1 if errs else 0


if __name__ == "__main__":
    sys.exit(main())
