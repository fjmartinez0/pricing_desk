"""Helpers that keep data/desk.json consistent: weeks, ranks, companies, weekly stats.

All derived numbers are computed here in code, never written by the agent.
"""
from __future__ import annotations

from collections import Counter

from common import (FIRST_AUTO_EDITION, HEADLINE_COMPANIES, NEWS_WINDOW_WEEKS, TIERS, week_key, week_range_label,
                    week_start)

COMPANY_FIELDS = ["name", "tier", "category", "aiNative", "ownership", "hq", "funding", "employees"]


REPORTED_WEEK_NOTE = ("Our own captures didn’t cover all of this week (they started on 24 Oct 2026), so it shows mainly "
                      "the changes PricingSaaS published in its daily briefings and weekly review. Totals are far below "
                      "the whole market.")


def ensure_week(desk: dict, week: str, reported: bool = False) -> None:
    """Add a week to weeks[] and week_order (newest first) if it isn't there.

    A week first created by a PricingSaaS report before our automated editions started gets a coverage note."""
    if week not in desk["week_order"]:
        desk["week_order"].append(week)
        desk["week_order"].sort(key=week_key, reverse=True)
    if not any(w["week"] == week for w in desk["weeks"]):
        w = {"week": week, "label": week_range_label(week), "start": week_start(week).isoformat(),
             "source_week": "Pricing Desk capture"}
        if reported and week_key(week) < week_key(FIRST_AUTO_EDITION):
            w.update(source_week="PricingSaaS reports", coverage="partial", note=REPORTED_WEEK_NOTE)
        desk["weeks"].append(w)
        desk["weeks"].sort(key=lambda w: week_key(w["week"]), reverse=True)


EDITION_TEXT = ("news", "patterns", "stats_analysis", "news_trends")


def news_window(desk: dict, week: str) -> list[dict]:
    """Stories of the editions before `week`, at most NEWS_WINDOW_WEEKS back, newest first, each tagged with
    its edition's week. Market Trends is written from these plus the week's own stories (D56)."""
    y, n = week_key(week)
    out = []
    for w, ed in sorted((desk.get("editions") or {}).items(), key=lambda kv: week_key(kv[0]), reverse=True):
        wy, wn = week_key(w)
        gap = (y - wy) * 52 + (n - wn)
        if 0 < gap <= NEWS_WINDOW_WEEKS:
            out += [dict(nw, week=w) for nw in ed.get("news", [])]
    return out


def show_edition(desk: dict, week: str) -> None:
    """Copy a stored edition's text to the top level, where the page reads the current edition."""
    ed = desk["editions"][week]
    desk.update({k: ed.get(k, []) for k in EDITION_TEXT})


def _magnitude_size(c: dict) -> float:
    m = c.get("magnitude") or {}
    return max(abs(m.get("low") or 0), abs(m.get("high") or 0))


PLAN_REACH = {"all": 3, "free": 3, "entry": 2, "mid": 2, "top": 1, "enterprise": 1, "add-on": 1}


def importance(c: dict) -> float:
    """How much a change matters to buyers, within its tier (D54):
    company weight (HEADLINE_COMPANIES 1.5) × who it hits (reach 1–3, or from the plan level)
    × size (10 + % change, capped at 100; 15 when no % is given) × 1.5 for a list or unit price move.
    A one-line record counts half. Comparable across weeks, so a month view ranks on it too."""
    reach = c.get("reach") or PLAN_REACH.get(c.get("planLevel"), 2)
    size = min(_magnitude_size(c), 100) or 15
    basis = (c.get("magnitude") or {}).get("basis")
    return ((1.5 if c.get("company") in HEADLINE_COMPANIES else 1.0) * reach * (10 + size)
            * (1.5 if basis in ("list price", "unit price") else 1.0) * (0.5 if c.get("detail") == "line" else 1.0))


def rerank(desk: dict, week: str) -> None:
    """D9 + D54: tier first (1, 2, 3), then importance(); full cards before one-line records only as part of
    importance. Ties keep their old order. Stores rank (within the week) and score (across weeks)."""
    rows = [c for c in desk["changes"] if c["week"] == week]
    for c in rows:
        c["score"] = round(importance(c), 1)
    rows.sort(key=lambda c: (c.get("tier") or 3, -c["score"], c.get("rank") or 999))
    for i, c in enumerate(rows, 1):
        c["rank"] = i


def rerank_all(desk: dict) -> None:
    for w in {c["week"] for c in desk["changes"]}:
        rerank(desk, w)


def sync_company(desk: dict, registry: dict, slug: str) -> None:
    """Copy a company's display fields from the registry into desk.companies."""
    entry = registry["companies"][slug]
    desk["companies"][slug] = {k: entry.get(k) for k in COMPANY_FIELDS}


def week_stats(desk: dict, week: str) -> dict:
    """Counts the edition agent may quote. Every number in stats_analysis.fig must come from here."""
    rows = [c for c in desk["changes"] if c["week"] == week]
    main = [c for c in rows if c.get("main", (c.get("tier") or 3) <= 2)]
    by = lambda key, items: dict(Counter(str(c.get(key)) for c in items))
    tier_group = Counter(f"tier{c.get('tier')}:{c['group']}" for c in rows)
    tier_pattern = Counter(f"tier{c.get('tier')}:{c['pattern']}" for c in rows)
    return {
        "week": week,
        "total": len(rows), "relevant": len(main), "full_cards": sum(c.get("detail") != "line" for c in rows),
        "by_group": by("group", rows), "by_tier": by("tier", rows), "by_pattern": by("pattern", rows),
        "by_segment": by("seg", rows), "by_plan_level": by("planLevel", rows), "ai": sum(bool(c.get("ai")) for c in rows),
        "relevant_by_group": by("group", main), "relevant_by_pattern": by("pattern", main),
        "tier_group": dict(tier_group), "tier_pattern": dict(tier_pattern),
        "promos": sum(p["week"] == week for p in desk["promos"]),
        "tier_sizes": {str(t): sum(c.get("tier") == t for c in rows) for t in TIERS},
    }


def stats_numbers(stats: dict) -> set[str]:
    """Flatten every number in week_stats to strings, for checking agent-written figures."""
    out = set()

    def walk(x):
        if isinstance(x, dict):
            for v in x.values():
                walk(v)
        elif isinstance(x, bool):
            return
        elif isinstance(x, int):
            out.add(str(x))
    walk(stats)
    return out
