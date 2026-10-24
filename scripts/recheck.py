"""Step 4: check today's additions against their sources online. Evidence before claims.

  * "They say": the quoted words must appear on statedUrl (the company's own site).
    If not, the quote is removed; the card stays.
  * Edition news: each article must load, and every number in its "Key numbers"
    must appear in the article. Numbers that don't are removed; an article that
    doesn't load is removed.
Every check is appended to data/checks.jsonl.

Usage: python3 scripts/recheck.py [--run RUN_ID]
"""
from __future__ import annotations

import argparse

from common import DESK, RUN, append_check, claimed_numbers, load_json, log, numbers_in, run_id, save_json
from fetch import Blocked, FetchError, fetch_html
from normalize import comparable, html_to_text

_browser = None


def page_text(url: str) -> str | None:
    """Static fetch, then the browser if the static page has no usable text."""
    global _browser
    try:
        text = html_to_text(fetch_html(url))
        if len(text) > 500:
            return text
    except Blocked:
        return None
    except FetchError:
        pass
    try:
        if _browser is None:
            from browser_capture import BrowserSession
            _browser = BrowserSession()
        return html_to_text(_browser.fetch_html(url))
    except Exception as e:
        log(f"  could not load {url}: {e}")
        return None


def check_stated(desk: dict, added: list[str]) -> int:
    changed = 0
    for c in desk["changes"]:
        if c["id"] not in added or not c.get("stated"):
            continue
        text = page_text(c["statedUrl"])
        quote = comparable(c["stated"]).strip('"')
        ok = bool(text) and quote in comparable(text)
        append_check("stated", c["id"], ok, c["statedUrl"])
        if not ok:
            log(f"  {c['id']}: 'They say' removed, words not found on {c['statedUrl']}")
            c["stated"] = None
            c.pop("statedUrl", None)
            changed += 1
    return changed


def check_news(desk: dict, news_ids: list[str]) -> int:
    changed, keep = 0, []
    for n in desk.get("news", []):
        if n["id"] not in news_ids:
            keep.append(n)
            continue
        text = page_text(n["url"])
        if not text:
            append_check("news", n["url"], False, "did not load")
            changed += 1
            continue
        on_page = numbers_in(text)
        good = [pair for pair in n.get("nums", []) if not (claimed_numbers(pair[0]) - on_page)]
        append_check("news", n["url"], len(good) == len(n.get("nums", [])),
                     f"{len(good)}/{len(n.get('nums', []))} key numbers found")
        if len(good) != len(n.get("nums", [])):
            changed += 1
        n["nums"] = good
        keep.append(n)
    removed = {n["id"] for n in desk.get("news", [])} - {n["id"] for n in keep}
    desk["news"] = keep
    for t in desk.get("news_trends", []):
        t["news"] = [i for i in t.get("news", []) if i not in removed]
    return changed


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run", default=run_id())
    args = ap.parse_args()
    merge = load_json(RUN / f"merge_{args.run}.json")
    if not merge:
        log("recheck: nothing merged this run")
        return 0
    desk = load_json(DESK)
    changed = check_stated(desk, merge.get("added", []))
    if merge.get("edition"):
        changed += check_news(desk, merge.get("news_added", []))
    if _browser:
        _browser.close()
    if changed:
        save_json(DESK, desk)
    log(f"recheck: {changed} corrections")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
