"""Step 2b: read PricingSaaS (hybrid, D39–D42) and queue the changes it reports.

Our own captures stay the primary source. PricingSaaS watches far more companies, so we read it to
  * find changes at companies we don't capture yet (they become "reported" records, D40), and
  * find companies to add to the registry (from then on we capture them ourselves).

What one run does:
  1. Daily briefings: open https://pricingsaas.com/news in the browser and click "Load more" until the
     list ends (about 9 days back) or until it only shows pages we read on an earlier run.
  2. Weekly reviews: fetch the review of this week and last week (or the weeks given with --review).
  3. Fetch every new article and every new "diff" page (one company's before/after for one day or week),
     politely: robots.txt, our user agent, a pause between pages, at most PS_MAX_FETCHES per run.
     A weekly diff page of a week that hasn't ended yet is deferred: it still grows.
  4. Save each page's text in data/pricingsaas/pages/ (the evidence) and queue each diff page in
     data/reports.json, grouped by PricingSaaS company and week. prepare_reports.py hands the queue to
     the agent; apply_proposals.py decides.

Usage:
  python3 scripts/pricingsaas_capture.py                          # normal run (run_daily.sh)
  python3 scripts/pricingsaas_capture.py --review 2026-W35 2026-W36 2026-W37 --max-fetches 400   # backfill
  python3 scripts/pricingsaas_capture.py --no-browser             # first page of briefings only
  python3 scripts/pricingsaas_capture.py --dry-run                # list what would be fetched
"""
from __future__ import annotations

import argparse
import datetime as dt
import html as htmllib
import re
import time
from pathlib import Path
from urllib.parse import urljoin, urlparse

from common import (PS_BASE, PS_CUT_MARKERS, PS_DELAY_SEC, PS_DIR, PS_INDEX, PS_LOAD_MORE_MAX, PS_MAX_FETCHES,
                    PS_NEWS_URL, PS_REVIEW_URL, REPORTS, ROOT, RUN, append_check, load_json, log, now, ps_period_week,
                    report_problem, run_id, save_json, week_label, week_start)
from fetch import Blocked, FetchError, fetch_html
from normalize import html_to_text

ARTICLE_RX = re.compile(r"^https://pricingsaas\.com/news/article/([a-z0-9][a-z0-9-]*)$")
DIFF_RX = re.compile(r"^https://pricingsaas\.com/companies/([a-z0-9][a-z0-9.\-]*)/diffs/(\d{4}[WD]\d{1,3})$")
LINK_PATTERN = r"pricingsaas\.com/(news/article/|companies/[^/]+/diffs/)"


# ---------------------------------------------------------------- parsing (pure, unit-tested)
def canon(url: str) -> str:
    """https, no www, no query or fragment, no trailing slash."""
    p = urlparse(url)
    host = (p.hostname or "").lower()
    host = host[4:] if host.startswith("www.") else host
    return f"https://{host}{p.path.rstrip('/')}"


def classify(url: str) -> tuple[str, re.Match] | None:
    u = canon(url)
    m = DIFF_RX.match(u)
    if m:
        return "diff", m
    m = ARTICLE_RX.match(u)
    if m:
        return "article", m
    return None


def parse_links(html: str, base: str = PS_BASE) -> list[str]:
    """Article and diff links in a page, canonical, in page order, no duplicates."""
    out, seen = [], set()
    for href in re.findall(r"""href\s*=\s*["']([^"']+)["']""", html or "", re.I):
        u = canon(urljoin(base + "/", htmllib.unescape(href)))
        if classify(u) and u not in seen:
            seen.add(u)
            out.append(u)
    return out


def meta(html: str, name: str) -> str | None:
    for pat in (rf"""<meta[^>]+(?:property|name)\s*=\s*["']{re.escape(name)}["'][^>]*content\s*=\s*["']([^"']*)["']""",
                rf"""<meta[^>]+content\s*=\s*["']([^"']*)["'][^>]*(?:property|name)\s*=\s*["']{re.escape(name)}["']"""):
        m = re.search(pat, html or "", re.I)
        if m:
            return htmllib.unescape(m.group(1)).strip()
    return None


def title_of(html: str) -> str:
    t = meta(html, "og:title")
    if not t:
        m = re.search(r"<title[^>]*>(.*?)</title>", html or "", re.I | re.S)
        t = htmllib.unescape(m.group(1)).strip() if m else ""
    return re.sub(r"\s+[—–-]\s+PricingSaaS.*$", "", t).strip()


def cut_text(text: str) -> str:
    """Keep the part of a diff page about this change; drop history, peers, FAQ and plan lists."""
    lines = text.splitlines()
    markers = [re.compile(p, re.I) for p in PS_CUT_MARKERS]
    for i, line in enumerate(lines):
        if i >= 5 and any(m.search(line) for m in markers):
            return "\n".join(lines[:i])
    return text


def page_file(kind: str, m: re.Match) -> Path:
    if kind == "diff":
        return PS_DIR / "pages" / "diffs" / f"{m.group(1)}__{m.group(2)}.txt"
    return PS_DIR / "pages" / "articles" / f"{m.group(1)}.txt"


def weekly_page_final(period: str, today: dt.date) -> bool:
    """A weekly diff page keeps growing until its week has ended."""
    week, day = ps_period_week(period)
    return day is not None or today > week_start(week) + dt.timedelta(days=6)


def diff_week(url: str) -> str | None:
    c = classify(url)
    return ps_period_week(c[1].group(2))[0] if c and c[0] == "diff" else None


def near_weeks(published: str | None) -> set[str] | None:
    """Weeks an article's own change can belong to: its publication week and the one before.
    Articles also link a company's older history; those links are not this article's change."""
    if not published:
        return None
    try:
        day = dt.datetime.fromisoformat(published.replace("Z", "+00:00")).date()
    except ValueError:
        return None
    return {week_label(day), week_label(day - dt.timedelta(days=7))}


def review_url(week: str) -> str:
    year, n = week.split("-W")
    return PS_REVIEW_URL.format(year=int(year), week=int(n))


# ---------------------------------------------------------------- queue
def queue_report(reports: dict, diff_url: str, file: str, article_files: list[str], title: str, run: str) -> str:
    """Add a fetched diff page to data/reports.json. One report per PricingSaaS company and week:
    an undecided report collects every page about that company-week; a page arriving after the decision
    opens a follow-up report (the agent sees the records already made)."""
    _, m = classify(diff_url)
    ps_slug, period = m.group(1), m.group(2)
    week, day = ps_period_week(period)
    base = f"{ps_slug}:{week}"
    items = reports.setdefault("reports", [])
    same = [r for r in items if r["report_id"] == base or r["report_id"].startswith(base + "#")]
    if any(diff_url in r["urls"] for r in same):
        return "known"
    open_ = next((r for r in same if r["status"] == "todo"), None)
    if open_:
        open_["urls"].append(diff_url)
        open_["files"].append(file)
        open_["article_files"] = sorted(set(open_["article_files"]) | set(article_files))
        if day and (not open_.get("change_date") or day.isoformat() < open_["change_date"]):
            open_["change_date"] = day.isoformat()
        return open_["report_id"]
    rid = base if not same else f"{base}#{len(same) + 1}"
    items.append({
        "report_id": rid, "ps_slug": ps_slug, "week": week, "change_date": day.isoformat() if day else None,
        "urls": [diff_url], "files": [file], "article_files": sorted(set(article_files)), "title": title,
        "first_seen_run": run, "status": "todo", "attempts": 0, "waits": 0, "company": None,
        "decision": None, "outcome": None,
    })
    return rid


# ---------------------------------------------------------------- main
def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--review", nargs="*", metavar="WEEK", help="weekly reviews to read, e.g. 2026-W35")
    ap.add_argument("--no-browser", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--max-fetches", type=int, default=PS_MAX_FETCHES, help="page budget for this run")
    args = ap.parse_args()

    run, today, at = run_id(), now().date(), now().isoformat(timespec="seconds")
    index = load_json(PS_INDEX, {"pages": {}})
    pages = index["pages"]
    reports = load_json(REPORTS, {"reports": []})
    found: list[tuple[str, str]] = []            # (url, found via)
    stats = {"listed": 0, "clicks": 0, "fetched": 0, "deferred": 0, "failed": 0, "queued": 0}

    def note(urls, via):
        for u in urls:
            found.append((u, via))

    # 1. daily briefings
    if args.review is None:
        try:
            if args.no_browser:
                note(parse_links(fetch_html(PS_NEWS_URL)), "news")
            else:
                from browser_capture import BrowserSession
                b = BrowserSession()
                try:
                    links, stats["clicks"] = b.collect_links(PS_NEWS_URL, LINK_PATTERN, max_clicks=PS_LOAD_MORE_MAX,
                                                             known=set(pages))
                finally:
                    b.close()
                note([canon(u) for u in links if classify(u)], "news")
        except Blocked:
            report_problem("pricingsaas.com robots.txt blocks our user agent; PricingSaaS reports skipped.", "pricingsaas")
            return 0
        except (FetchError, ImportError) as e:
            report_problem(f"PricingSaaS briefings not read ({e}); trying the first page without the browser.", "pricingsaas")
            try:
                note(parse_links(fetch_html(PS_NEWS_URL)), "news")
            except (FetchError, Blocked) as e2:
                append_check("pricingsaas", PS_NEWS_URL, False, str(e2))

    # 2. weekly reviews
    weeks = args.review or [week_label(today - dt.timedelta(days=7)), week_label(today)]
    for w in weeks:
        url = review_url(w)
        try:
            note([u for u in parse_links(fetch_html(url)) if classify(u)[0] == "article" or diff_week(u) == w],
                 f"review {w}")
            append_check("pricingsaas", url, True, "review")
        except Blocked:
            report_problem("pricingsaas.com robots.txt blocks our user agent; PricingSaaS reports skipped.", "pricingsaas")
            return 0
        except FetchError as e:
            append_check("pricingsaas", url, False, str(e))        # 404 = not published yet; never fatal
            log(f"  review {w}: {e}")
        time.sleep(PS_DELAY_SEC)
    stats["listed"] = len({u for u, _ in found})

    for u, via in found:
        e = pages.setdefault(u, {"type": classify(u)[0], "status": "new", "first_seen": run, "found_via": []})
        if via not in e["found_via"] and len(e["found_via"]) < 5:
            e["found_via"].append(via)

    if args.dry_run:
        todo = [u for u, e in pages.items() if e["status"] in ("new", "deferred", "failed")]
        print(f"{stats['listed']} links listed, {len(todo)} to fetch:")
        print("\n".join(todo[:200]))
        return 0

    # 3. fetch: articles first (they link diff pages), then diff pages
    budget = args.max_fetches

    def fetch(u: str) -> str | None:
        nonlocal budget
        if budget <= 0:
            return None
        budget -= 1
        time.sleep(PS_DELAY_SEC)
        try:
            html = fetch_html(u)
            append_check("pricingsaas", u, True, "")
            stats["fetched"] += 1
            return html
        except (FetchError, Blocked) as e:
            pages[u]["status"] = "failed"
            pages[u]["error"] = str(e)[:200]
            pages[u]["fail_runs"] = pages[u].get("fail_runs", 0) + 1
            append_check("pricingsaas", u, False, str(e))
            stats["failed"] += 1
            return None

    def retry_ok(e: dict) -> bool:
        return e["status"] == "new" or e["status"] == "deferred" or (e["status"] == "failed" and e.get("fail_runs", 0) < 4)

    for u in [u for u, e in list(pages.items()) if e["type"] == "article" and retry_ok(e)]:
        html = fetch(u)
        if html is None:
            continue
        kind, m = classify(u)
        path = page_file(kind, m)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(html_to_text(html), encoding="utf-8")
        published = meta(html, "article:published_time")
        near = near_weeks(published)
        diffs = [d for d in parse_links(html) if classify(d)[0] == "diff" and (near is None or diff_week(d) in near)]
        pages[u].update(status="fetched", fetched_at=at, file=str(path.relative_to(ROOT)), title=title_of(html),
                        published=published, diffs=diffs)
        for d in diffs:
            e = pages.setdefault(d, {"type": "diff", "status": "new", "first_seen": run, "found_via": []})
            if u not in e.setdefault("articles", []):
                e["articles"].append(u)

    for u in [u for u, e in list(pages.items()) if e["type"] == "diff" and retry_ok(e)]:
        kind, m = classify(u)
        if not weekly_page_final(m.group(2), today):
            pages[u]["status"] = "deferred"
            stats["deferred"] += 1
            continue
        html = fetch(u)
        if html is None:
            continue
        path = page_file(kind, m)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(cut_text(html_to_text(html)), encoding="utf-8")
        art_files = [pages[a]["file"] for a in pages[u].get("articles", []) if pages.get(a, {}).get("file")]
        title = title_of(html)
        pages[u].update(status="fetched", fetched_at=at, file=str(path.relative_to(ROOT)), title=title)
        rid = queue_report(reports, u, pages[u]["file"], art_files, title, run)
        if rid != "known":
            stats["queued"] += 1
        pages[u]["report_id"] = rid

    # articles fetched after their diff pages: attach them to reports not yet decided
    for r in reports["reports"]:
        if r["status"] != "todo":
            continue
        for du in r["urls"]:
            for a in pages.get(du, {}).get("articles", []):
                f = pages.get(a, {}).get("file")
                if f and f not in r["article_files"]:
                    r["article_files"].append(f)

    save_json(PS_INDEX, index)
    save_json(REPORTS, reports)
    save_json(RUN / f"pricingsaas_{run}.json", stats)
    if budget <= 0:
        log("  pricingsaas: fetch budget used up; the rest is fetched on the next run")
    log(f"pricingsaas: {stats['listed']} links listed ({stats['clicks']} 'Load more' clicks), {stats['fetched']} pages "
        f"fetched, {stats['failed']} failed, {stats['deferred']} weekly pages deferred, {stats['queued']} reports queued")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
