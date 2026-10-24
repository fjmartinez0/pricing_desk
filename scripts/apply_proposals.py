"""Step 3: merge the agent's proposals into the data. The AI proposes; this code decides.

Reads, for the current run (PD_RUN_ID):
  proposals/<run>.changes.json    page changes classified and written up by the agent
  proposals/<run>.registry.json   pricing URLs for companies that need one, new companies
  proposals/<run>.edition.json    weekly edition text (only when an edition is due)

Rules enforced here (see PROJECT_CONTEXT.md, "Rules the code enforces"):
  * keep rule: the change kind decides keep / drop / promo, from common.KEEP_KINDS etc.;
  * cards are never invented: every number on a card must appear in the captured page text;
    a card that fails is downgraded to a one-line record, a line that fails is held back;
  * "They say" is kept only with a link on the company's own site (recheck.py then checks the words);
  * tier comes from the registry, IDs, weeks, ranks and companies are assigned here;
  * records are append-only: existing records are never changed or removed.

Usage: python3 scripts/apply_proposals.py [--run RUN_ID]
"""
from __future__ import annotations

import argparse
import datetime as dt
import re

from common import (AGGREGATOR_DOMAINS, ALL_KINDS, BACKLOG, BACKLOG_MAX_ATTEMPTS, APPLIES_TO, DESK, DROP_KINDS, GROUPS, KEEP_KINDS, MAGNITUDE_BASIS,
                    MAX_ROWS, MODELS, PATTERNS, PLAN_LEVELS, PROMO_KIND, PROMO_KINDS, PROPOSALS, REACH, REGISTRY,
                    ROOT, RUN, SEGMENTS, SRC_CAPTURE, TIERS, WATCHLIST, change_id, claimed_numbers, domain_of,
                    is_http_url, load_json, log, now, numbers_in, report_problem, run_id, same_site, save_json,
                    short_date, week_range_label, week_start)
from desk import ensure_week, rerank, stats_numbers, sync_company, week_stats

PROSE_FIELDS = ["short", "headline", "who", "read", "caveat", "stated", "plan", "deltaSub"]
MAX_LEN = {"short": 240, "headline": 220, "who": 240, "read": 600, "caveat": 300, "stated": 400,
           "plan": 80, "delta": 24, "deltaSub": 40}
CARD_REQUIRED = ["plan", "group", "delta", "deltaSub", "short", "headline", "rows", "who", "read", "pattern",
                 "seg", "ai", "planLevel", "model", "modelBefore", "modelAfter", "appliesTo"]
LINE_REQUIRED = ["group", "delta", "short", "pattern", "seg", "ai", "planLevel"]


class Rejected(Exception):
    """A proposal item breaks a rule. The message says which."""


# ---------------------------------------------------------------- text helpers
def tidy(text):
    """House typography for visible text: curly apostrophes and arrows."""
    if not isinstance(text, str):
        return text
    text = re.sub(r"(?<=\w)'(?=\w)", "’", text).replace("->", "→")
    return re.sub(r"\s+", " ", text).strip()


def check_prose(rec: dict) -> None:
    for f in PROSE_FIELDS:
        v = rec.get(f)
        if v is None:
            continue
        if not isinstance(v, str):
            raise Rejected(f"{f} must be text")
        if "http" in v or "www." in v:
            raise Rejected(f"{f} contains a URL; links go in url / statedUrl only")
        if len(v) > MAX_LEN[f]:
            raise Rejected(f"{f} longer than {MAX_LEN[f]} characters")


def check_enums(rec: dict) -> None:
    def need(field, allowed):
        if rec.get(field) not in allowed:
            raise Rejected(f"{field}={rec.get(field)!r} not in {sorted(map(str, allowed))}")
    need("group", GROUPS)
    need("pattern", PATTERNS)
    need("seg", SEGMENTS)
    need("planLevel", PLAN_LEVELS)
    if not isinstance(rec.get("ai"), bool):
        raise Rejected("ai must be true or false")
    if rec.get("reach") is not None:
        need("reach", REACH)


# ---------------------------------------------------------------- evidence
def untraceable(text: str, allowed: set[str]) -> set[str]:
    return claimed_numbers(text) - allowed


def check_card_numbers(rec: dict, before: set[str], after: set[str]) -> list[str]:
    """Return problems: every number on the card must be on the captured page."""
    both = before | after
    problems = []
    for label, b, a in rec["rows"]:
        for name, text, allowed in (("label", label, both), ("before", b, before), ("after", a, after)):
            bad = untraceable(text, allowed)
            if bad:
                problems.append(f"row {label!r} {name}: {', '.join(sorted(bad))} not on the page")
    for f in ("delta", "deltaSub", "short", "headline"):
        bad = untraceable(rec.get(f) or "", both)
        if bad:
            problems.append(f"{f}: {', '.join(sorted(bad))} not on the page")
    return problems


def check_line_numbers(rec: dict, both: set[str]) -> list[str]:
    problems = []
    for f in ("delta", "short"):
        bad = untraceable(rec.get(f) or "", both)
        if bad:
            problems.append(f"{f}: {', '.join(sorted(bad))} not on the page")
    return problems


def clean_magnitude(m, group: str):
    """Keep a magnitude only if it is well-formed and agrees with the change direction."""
    if not isinstance(m, dict) or m.get("basis") not in MAGNITUDE_BASIS:
        return None
    lo, hi = m.get("low"), m.get("high")
    if not all(isinstance(x, (int, float)) and not isinstance(x, bool) for x in (lo, hi)) or lo > hi:
        return None
    if (group == "up" and hi <= 0) or (group == "down" and lo >= 0):
        return None
    return {"low": lo, "high": hi, "basis": m["basis"]}


def is_duplicate(desk: dict, slug: str, rec: dict) -> bool:
    """Same company already has a record with the same summary or the same after-values (D18)."""
    short = (rec.get("short") or "").lower()
    rows = {tuple(r) for r in rec.get("rows") or []}
    for c in desk["changes"]:
        if c.get("company") != slug:
            continue
        if (c.get("short") or "").lower() == short:
            return True
        if rows and rows == {tuple(r) for r in c.get("rows") or []}:
            return True
    return False


# ---------------------------------------------------------------- changes
def build_change(item: dict, event: dict, entry: dict, slug: str, desk: dict, taken: set[str]) -> dict:
    rec = {k: tidy(v) if isinstance(v, str) else v for k, v in (item.get("record") or {}).items()}
    detail = item.get("detail", "card")
    if detail not in ("card", "line"):
        raise Rejected("detail must be card or line")
    required = CARD_REQUIRED if detail == "card" else LINE_REQUIRED
    missing = [f for f in required if rec.get(f) in (None, "", [])]
    if missing:
        raise Rejected(f"missing fields: {', '.join(missing)}")
    check_enums(rec)
    check_prose(rec)
    if len(rec.get("delta", "")) > MAX_LEN["delta"]:
        raise Rejected("delta too long")

    before_text = (ROOT / event["before_file"]).read_text(encoding="utf-8")
    after_text = (ROOT / event["after_file"]).read_text(encoding="utf-8")
    if event.get("alt_file"):
        after_text += "\n" + (ROOT / event["alt_file"]).read_text(encoding="utf-8")
    before, after = numbers_in(before_text), numbers_in(after_text)

    if detail == "card":
        rows = rec["rows"]
        if not (isinstance(rows, list) and 1 <= len(rows) <= MAX_ROWS
                and all(isinstance(r, list) and len(r) == 3 and all(isinstance(x, str) for x in r) for r in rows)):
            raise Rejected(f"rows must be 1–{MAX_ROWS} lists of [label, before, after]")
        rec["rows"] = [[tidy(x) for x in r] for r in rows]
        for f, allowed in (("model", None), ("modelBefore", MODELS), ("modelAfter", MODELS), ("appliesTo", APPLIES_TO)):
            v = rec[f]
            ok = (v in MODELS or re.fullmatch(r"(Seat|Usage|Flat|Hybrid) → (Seat|Usage|Flat|Hybrid)", v or "")) \
                if allowed is None else v in allowed
            if not ok:
                raise Rejected(f"{f}={v!r} not allowed")
        if item["kind"] in ("price_increase", "price_cut") and not any(numbers_in(r[1]) for r in rec["rows"]):
            raise Rejected("no before price: this is a price reveal (dropped by the keep rule)")
        problems = check_card_numbers(rec, before, after)
        if problems:
            log(f"  {slug}: card downgraded to a line ({'; '.join(problems)})")
            detail = "line"
    if detail == "line":
        problems = check_line_numbers(rec, before | after)
        if problems:
            raise Rejected("held back, numbers not on the page: " + "; ".join(problems))

    if is_duplicate(desk, slug, rec):
        raise Rejected("duplicate of an existing record (keep rule)")

    week = event["week"]
    first_new = dt.datetime.fromisoformat(event["first_new_at"]).date()
    tier = 1 if slug in WATCHLIST else entry.get("tier") or 3
    out = {
        "id": change_id(slug, week, taken), "week": week, "rank": None, "co": entry["name"], "company": slug,
        "tier": tier, "group": rec["group"], "delta": rec["delta"], "short": rec["short"],
        "pattern": rec["pattern"], "seg": rec["seg"], "ai": rec["ai"], "planLevel": rec["planLevel"],
        "reach": rec.get("reach") or 2, "magnitude": None,
        "seen": week_start(week).isoformat(), "seenLabel": week_range_label(week), "when": short_date(first_new),
        "src": SRC_CAPTURE, "url": entry["pricing_urls"][0],
        "evidence": {"before": event["before_file"], "after": event["after_file"], "diff": event["diff_id"]},
    }
    if event.get("unstable"):
        out["evidence"]["alt"] = event["alt_file"]
    if detail == "line":
        out["detail"] = "line"
        return out

    stated, stated_url = rec.get("stated"), rec.get("statedUrl")
    domains = entry.get("domains") or [domain_of(u) for u in entry["pricing_urls"]]
    if stated and not (is_http_url(stated_url) and same_site(stated_url, domains)):
        log(f"  {slug}: 'They say' removed (no link on the company's own site)")
        stated, stated_url = None, None
    out.update({
        "plan": rec["plan"], "deltaSub": rec["deltaSub"], "headline": rec["headline"], "rows": rec["rows"],
        "who": rec["who"], "stated": stated or None, "read": rec["read"],
        "model": rec["model"], "modelBefore": rec["modelBefore"], "modelAfter": rec["modelAfter"],
        "appliesTo": rec["appliesTo"], "magnitude": clean_magnitude(rec.get("magnitude"), rec["group"]),
    })
    if stated_url and stated:
        out["statedUrl"] = stated_url
    for opt in ("caveat", "announced", "effective"):
        if rec.get(opt):
            out[opt] = rec[opt]
    return out


def build_promo(item: dict, event: dict, entry: dict, slug: str, desk: dict) -> dict:
    p = item.get("promo") or {}
    if p.get("kind") not in PROMO_KINDS:
        raise Rejected(f"promo kind must be one of {sorted(PROMO_KINDS)}")
    text = tidy(p.get("text") or "")
    if not text or len(text) > 240 or "http" in text:
        raise Rejected("promo text missing, too long or contains a URL")
    pages = (ROOT / event["before_file"]).read_text(encoding="utf-8") + (ROOT / event["after_file"]).read_text(encoding="utf-8")
    bad = claimed_numbers(text) - numbers_in(pages)
    if bad:
        raise Rejected(f"promo numbers not on the page: {', '.join(sorted(bad))}")
    week = event["week"]
    base = f"{slug}-promo-{week.lower().replace('-', '')}"
    taken = {x["id"] for x in desk["promos"]}
    pid, n = base, 2
    while pid in taken:
        pid, n = f"{base}-{n}", n + 1
    return {"id": pid, "week": week, "company": slug, "co": entry["name"], "kind": p["kind"], "text": text,
            "src": SRC_CAPTURE}


def apply_changes(desk: dict, registry: dict, proposal: dict, inputs: dict, result: dict) -> None:
    events = {e["diff_id"]: e for e in inputs.get("changes", [])}
    taken = {c["id"] for c in desk["changes"]}
    touched_weeks = set()
    for item in proposal.get("items", []):
        diff_id = item.get("diff_id")
        try:
            event = events.get(diff_id)
            if not event:
                raise Rejected("unknown diff_id")
            kind = item.get("kind")
            if kind not in ALL_KINDS:
                raise Rejected(f"kind={kind!r} unknown")
            slug = event["company"]
            entry = registry["companies"][slug]
            if kind in DROP_KINDS:
                result["dropped"].append({"diff_id": diff_id, "kind": kind, "why": item.get("why", "")})
                continue
            if kind == PROMO_KIND:
                promo = build_promo(item, event, entry, slug, desk)
                ensure_week(desk, promo["week"])
                desk["promos"].append(promo)
                if slug not in desk["companies"]:
                    sync_company(desk, registry, slug)
                    desk["companies"][slug]["tier"] = None   # promo-only companies have no tier
                result["promos"].append(promo["id"])
                continue
            assert kind in KEEP_KINDS
            rec = build_change(item, event, entry, slug, desk, taken)
            ensure_week(desk, rec["week"])
            sync_company(desk, registry, slug)
            desk["companies"][slug]["tier"] = rec["tier"]
            desk["changes"].append(rec)
            taken.add(rec["id"])
            touched_weeks.add(rec["week"])
            result["added"].append(rec["id"])
            log(f"  + {rec['id']} ({'line' if rec.get('detail') else 'card'})")
        except Rejected as e:
            result["rejected"].append({"diff_id": diff_id, "why": str(e)})
            log(f"  - {diff_id}: {e}")
    for w in touched_weeks:
        rerank(desk, w)


# ---------------------------------------------------------------- registry
def slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def valid_pricing_urls(urls, domains) -> bool:
    return (isinstance(urls, list) and 1 <= len(urls) <= 3 and all(is_http_url(u) for u in urls)
            and not any(domain_of(u) in AGGREGATOR_DOMAINS for u in urls)
            and all(same_site(u, domains) for u in urls))


def apply_registry(desk: dict, registry: dict, proposal: dict, result: dict) -> None:
    companies = registry["companies"]
    categories = {c["name"] for c in desk["categories"]}
    for item in proposal.get("urls", []):
        slug = item.get("slug")
        entry = companies.get(slug)
        if not entry or entry["status"] != "needs_url":
            result["rejected"].append({"registry": slug, "why": "not a needs_url company"})
            continue
        domains = item.get("domains") or []
        if not (isinstance(domains, list) and domains and valid_pricing_urls(item.get("pricing_urls"), domains)):
            entry["url_attempts"] = entry.get("url_attempts", 0) + 1
            result["rejected"].append({"registry": slug, "why": "bad pricing_urls / domains"})
            continue
        entry.update(pricing_urls=item["pricing_urls"], domains=domains, status="candidate")
        result["registry"].append(f"url:{slug}")
    known_domains = {d for e in companies.values() for d in e.get("domains", [])}
    for item in proposal.get("new_companies", []):
        name = tidy(item.get("name") or "")
        slug = slugify(name)
        domains = item.get("domains") or []
        if not name or slug in companies or any(d in known_domains for d in domains):
            continue
        if item.get("category") not in categories:
            result["rejected"].append({"registry": slug, "why": f"category {item.get('category')!r} unknown"})
            continue
        urls = item.get("pricing_urls") or []
        has_urls = bool(urls) and bool(domains) and valid_pricing_urls(urls, domains)
        companies[slug] = {
            "name": name, "tier": 2 if item.get("tier") == 2 else 3, "category": item["category"],
            "segment": item.get("segment") if item.get("segment") in SEGMENTS else None,
            "watch": False, "pricing_urls": urls if has_urls else [], "domains": domains,
            "capture": "static", "status": "candidate" if has_urls else "needs_url",
            "aiNative": item.get("aiNative") if isinstance(item.get("aiNative"), bool) else None,
            "ownership": None, "hq": None, "funding": None, "employees": None,
            "ignore_patterns": [], "added": now().date().isoformat(), "source": f"agent {run_id()}",
            "source_url": item.get("source_url") if is_http_url(item.get("source_url")) else None,
            "url_attempts": 0, "notes": tidy(item.get("why") or "")[:200],
        }
        result["registry"].append(f"new:{slug}")


# ---------------------------------------------------------------- edition
def _nums_ok(nums) -> bool:
    return isinstance(nums, list) and all(isinstance(n, list) and len(n) == 2 and all(isinstance(x, str) for x in n)
                                          for n in nums)


def apply_edition(desk: dict, registry: dict, proposal: dict, result: dict) -> None:
    due = load_json(RUN / f"edition_due_{run_id()}.json")
    if not due or proposal.get("week") != due["week"]:
        raise Rejected(f"edition week {proposal.get('week')!r} is not the week due")
    week = due["week"]
    week_ids = {c["id"] for c in desk["changes"] if c["week"] == week}
    all_ids = {c["id"] for c in desk["changes"]}
    allowed_figs = stats_numbers(week_stats(desk, week))

    news, seen_ids = [], set()
    for n in proposal.get("news", []):
        n = {k: tidy(v) if isinstance(v, str) and k != "url" else v for k, v in n.items()}
        ok = (isinstance(n.get("id"), str) and re.fullmatch(r"[a-z0-9-]{3,60}", n["id"]) and n["id"] not in seen_ids
              and all(isinstance(n.get(k), str) and n[k] for k in ("src", "date", "topic", "title", "gist", "why"))
              and is_http_url(n.get("url")) and domain_of(n["url"]) not in {"g2.com", "capterra.com"}
              and isinstance(n.get("lead"), bool) and isinstance(n.get("rel"), bool) and _nums_ok(n.get("nums", [])))
        if ok:
            seen_ids.add(n["id"])
            news.append(n)
        else:
            result["rejected"].append({"edition": f"news {n.get('id')}", "why": "malformed"})
    patterns = [p for p in proposal.get("patterns", [])
                if isinstance(p.get("t"), str) and isinstance(p.get("p"), str) and p.get("ids")
                and set(p["ids"]) <= week_ids]
    stats = []
    for s in proposal.get("stats_analysis", []):
        if not (isinstance(s.get("t"), str) and isinstance(s.get("p"), str) and isinstance(s.get("fig"), str)
                and set(s.get("ids") or []) <= week_ids):
            continue
        bad = set(re.findall(r"\d+", s["fig"])) - allowed_figs
        if bad:
            result["rejected"].append({"edition": f"stat {s['t']}", "why": f"figure not in week stats: {bad}"})
            continue
        stats.append(s)
    trends = [t for t in proposal.get("news_trends", [])
              if isinstance(t.get("t"), str) and isinstance(t.get("p"), str) and _nums_ok(t.get("nums", []))
              and set(t.get("news") or []) <= seen_ids and set(t.get("changes") or []) <= all_ids]

    total = len(week_ids)
    if len(news) < 3 or (total >= 3 and (not patterns or not stats)):
        raise Rejected(f"edition too thin after checks (news {len(news)}, patterns {len(patterns)}, stats {len(stats)})")

    for p in patterns + stats + trends:
        for k in ("t", "p", "figNote", "fig"):
            if isinstance(p.get(k), str):
                p[k] = tidy(p[k])
    st = week_stats(desk, week)
    active = sum(e["status"] == "active" for e in registry["companies"].values())
    today = now().date()
    desk.update({
        "current_week": week, "edition_date": today.isoformat(), "today": today.isoformat(),
        "period": week_range_label(week),
        "news": news, "patterns": patterns, "stats_analysis": stats, "news_trends": trends,
        "market_context": {
            "source": f"Pricing Desk, {active} tracked pricing pages", "total": st["total"],
            "increases": st["by_group"].get("up", 0), "cuts": st["by_group"].get("down", 0),
            "other": st["by_group"].get("pack", 0),
            "note": (f"Of {st['total']} changes kept from {active} tracked pricing pages this week, "
                     f"{st['by_group'].get('up', 0)} raised prices, {st['by_group'].get('down', 0)} cut them "
                     f"and {st['by_group'].get('pack', 0)} restructured plans or limits."),
        },
    })
    ensure_week(desk, week)
    for w in desk["weeks"]:
        if w["week"] == week:
            w.update(coverage="tracked", source_week="Pricing Desk capture",
                     note=(f"Captured from {active} tracked pricing pages, twice a day. "
                           f"We kept {st['total']} changes this week."))
    for m in proposal.get("missed", []):          # companies the news or PricingSaaS mentioned that we don't track
        if isinstance(m, dict) and m.get("name"):
            apply_registry(desk, registry, {"new_companies": [m]}, result)
    result["edition"] = week
    result["news_added"] = [n["id"] for n in news]


# ---------------------------------------------------------------- main
def load_proposal(run: str, kind: str):
    """The agent's proposal file, or None if missing or not valid JSON (reported, never fatal)."""
    path = PROPOSALS / f"{run}.{kind}.json"
    try:
        data = load_json(path)
    except ValueError as e:
        report_problem(f"{path.name} is not valid JSON ({e}); ignored.", "merge")
        return None
    if data is not None and data.get("type") != kind:
        report_problem(f"{path.name} has type {data.get('type')!r}; ignored.", "merge")
        return None
    return data


def update_backlog(proposal, result: dict) -> None:
    """Remove every change the agent decided on; give up on changes that waited too long."""
    backlog = load_json(BACKLOG, {"changes": []})
    decided = {i.get("diff_id") for i in (proposal or {}).get("items", [])}
    keep = []
    for e in backlog["changes"]:
        if e["diff_id"] in decided:
            continue
        if e.get("attempts", 0) >= BACKLOG_MAX_ATTEMPTS:
            report_problem(f"{e['diff_id']}: no agent decision after {e['attempts']} runs; given up "
                           f"(evidence kept in {e['after_file']}).", "merge")
            result["rejected"].append({"diff_id": e["diff_id"], "why": "no decision, given up"})
            continue
        keep.append(e)
    backlog["changes"] = keep
    save_json(BACKLOG, backlog)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run", default=run_id())
    args = ap.parse_args()
    run = args.run
    desk, registry = load_json(DESK), load_json(REGISTRY)
    result = {"run": run, "added": [], "promos": [], "dropped": [], "rejected": [], "registry": [], "edition": None}

    changes = load_proposal(run, "changes")
    if changes is not None:
        apply_changes(desk, registry, changes, load_json(PROPOSALS / f"{run}.input.json", {}), result)
    update_backlog(changes, result)
    reg = load_proposal(run, "registry")
    if reg is not None:
        apply_registry(desk, registry, reg, result)
    edition = load_proposal(run, "edition")
    if edition is not None:
        try:
            apply_edition(desk, registry, edition, result)
        except Rejected as e:
            report_problem(f"Edition not published: {e}. It will be retried on the next run.", "edition")

    desk["today"] = now().date().isoformat()
    save_json(DESK, desk)
    save_json(REGISTRY, registry)
    save_json(RUN / f"merge_{run}.json", result)
    if result["rejected"]:
        log(f"merge: {len(result['rejected'])} items rejected (see .run/merge_{run}.json)")
    log(f"merge: +{len(result['added'])} changes, +{len(result['promos'])} promos, "
        f"{len(result['dropped'])} dropped, registry {len(result['registry'])}, edition {result['edition']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
