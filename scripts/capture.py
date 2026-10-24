"""Step 1: capture every tracked pricing page and find confirmed changes.

For each company in data/registry.json with status active or candidate:
  1. fetch its pricing page(s) (static first, browser if needed) and normalize to text;
  2. compare with the confirmed version;
  3. a new version must be seen DEBOUNCE_CAPTURES runs in a row before it counts;
     a page that flips between versions within one run is reported as a possible price test.

Outputs:
  data/snapshots/<slug>/<run>.txt      confirmed versions (the evidence for every card)
  data/capture_state.json              per-company state (hashes, failures, timestamps)
  data/backlog.json                    confirmed changes waiting for an agent decision
  proposals/<run>.input.json           the backlog handed to the agent this run (committed for audit)
  .run/diffs/<diff_id>.diff            unified diffs for the agent to read

Usage:
  python3 scripts/capture.py                 # all companies
  python3 scripts/capture.py --company notion --dry-run
"""
from __future__ import annotations

import argparse
import difflib
import time

from common import (BACKLOG, CAPTURE_STATE, DEBOUNCE_CAPTURES, DELAY_BETWEEN_COMPANIES_SEC, FAIL_RUNS_TO_ALERT,
                    FAIL_RUNS_TO_PAUSE, PROPOSALS, REGISTRY, ROOT, RUN, SNAPSHOTS, UNSTABLE_RUNS_TO_REPORT,
                    URL_ATTEMPTS_MAX, AGGREGATOR_DOMAINS, append_check, domain_of, load_json, log, now,
                    report_problem, run_id, save_json, sha, week_label)
from fetch import Blocked, FetchError, fetch_html
from normalize import html_to_text, looks_like_pricing


# ---------------------------------------------------------------- fetching
def fetch_company_text(entry: dict, browser_factory) -> tuple[str, bool]:
    """Fetch all pricing URLs of one company and return (combined text, switched_to_browser).

    Static fetch first. If the static text shows no prices, try the browser once and,
    if that shows prices, switch the company to browser mode for future runs.
    """
    parts, switched = [], False
    for url in entry["pricing_urls"]:
        if domain_of(url) in AGGREGATOR_DOMAINS:
            raise FetchError(f"aggregator URL not allowed: {url}")
        ignore = entry.get("ignore_patterns", [])
        if entry.get("capture") == "browser":
            text = html_to_text(browser_factory().fetch_html(url), ignore)
        else:
            text = html_to_text(fetch_html(url), ignore)
            if not looks_like_pricing(text):
                try:
                    rendered = html_to_text(browser_factory().fetch_html(url), ignore)
                except FetchError as e:
                    log(f"  browser fallback failed for {url}: {e}")
                    rendered = ""
                if looks_like_pricing(rendered):
                    text, switched = rendered, True
        parts.append(f"=== {url} ===\n{text}")
    return "\n\n".join(parts), switched


# ---------------------------------------------------------------- state machine
def blank_state() -> dict:
    return {"confirmed_hash": None, "confirmed_file": None, "confirmed_at": None,
            "last_old_at": None, "pending_hash": None, "pending_count": 0, "pending_first_at": None,
            "unstable_runs": 0, "unstable_reported": False, "fail_runs": 0, "last_ok_at": None,
            "last_error": None}


def snapshot_path(slug: str, stamp: str):
    return SNAPSHOTS / slug / f"{stamp}.txt"


def step_company(st: dict, slug: str, text: str, text_again: str | None, stamp: str, at: str) -> dict | None:
    """Advance one company's state with this run's capture. Returns a diff event or None.

    `text_again` is a second fetch made only when the page differs from the confirmed
    version; if it differs from `text`, the page is flipping (likely an A/B price test).
    Pure apart from writing snapshot files, so it is easy to unit-test.
    """
    h = sha(text)
    st["fail_runs"], st["last_error"], st["last_ok_at"] = 0, None, at

    if st["confirmed_hash"] is None:                        # first capture: baseline, no change
        path = snapshot_path(slug, stamp)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        st.update(confirmed_hash=h, confirmed_file=str(path.relative_to(ROOT)), confirmed_at=at, last_old_at=at)
        return None

    if h == st["confirmed_hash"]:                           # unchanged
        st.update(last_old_at=at, pending_hash=None, pending_count=0, pending_first_at=None,
                  unstable_runs=0, unstable_reported=False)
        return None

    if text_again is not None and sha(text_again) != h:     # flipping within one run
        st["unstable_runs"] += 1
        if st["unstable_runs"] >= UNSTABLE_RUNS_TO_REPORT and not st["unstable_reported"]:
            st["unstable_reported"] = True
            a, b = snapshot_path(slug, stamp + "_a"), snapshot_path(slug, stamp + "_b")
            a.parent.mkdir(parents=True, exist_ok=True)
            a.write_text(text, encoding="utf-8")
            b.write_text(text_again, encoding="utf-8")
            return {"diff_id": f"{slug}-{stamp}", "company": slug, "unstable": True,
                    "before_file": st["confirmed_file"], "after_file": str(a.relative_to(ROOT)),
                    "alt_file": str(b.relative_to(ROOT)), "last_old_at": st["last_old_at"], "first_new_at": at,
                    "week": week_label(_date(st["last_old_at"]))}
        return None

    if h == st["pending_hash"]:
        st["pending_count"] += 1
    else:
        st.update(pending_hash=h, pending_count=1, pending_first_at=at)

    if st["pending_count"] < DEBOUNCE_CAPTURES:
        return None

    path = snapshot_path(slug, stamp)                       # confirmed new version
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    event = {"diff_id": f"{slug}-{stamp}", "company": slug, "unstable": False,
             "before_file": st["confirmed_file"], "after_file": str(path.relative_to(ROOT)),
             "last_old_at": st["last_old_at"], "first_new_at": st["pending_first_at"],
             # The change happened after the last capture that still showed the old page.
             "week": week_label(_date(st["last_old_at"]))}
    st.update(confirmed_hash=h, confirmed_file=event["after_file"], confirmed_at=at,
              last_old_at=at, pending_hash=None, pending_count=0, pending_first_at=None)
    return event


def _date(iso: str):
    from datetime import datetime
    return datetime.fromisoformat(iso).date()


def write_diff_file(event: dict) -> None:
    before = (ROOT / event["before_file"]).read_text(encoding="utf-8").splitlines()
    after = (ROOT / event["after_file"]).read_text(encoding="utf-8").splitlines()
    diff = difflib.unified_diff(before, after, event["before_file"], event["after_file"], n=3, lineterm="")
    out = RUN / "diffs" / f"{event['diff_id']}.diff"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(diff) + "\n", encoding="utf-8")
    event["diff_file"] = str(out.relative_to(ROOT))


# ---------------------------------------------------------------- main
def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--company", help="capture only this slug")
    ap.add_argument("--dry-run", action="store_true", help="fetch and print, change nothing")
    args = ap.parse_args()

    registry = load_json(REGISTRY)
    state = load_json(CAPTURE_STATE, {})
    stamp, at = run_id(), now().isoformat(timespec="seconds")
    companies = registry["companies"]
    todo = [s for s, e in companies.items()
            if e["status"] in ("active", "candidate") and e.get("pricing_urls")
            and (not args.company or s == args.company)]

    browser = None

    def browser_factory():
        nonlocal browser
        if browser is None:
            from browser_capture import BrowserSession
            browser = BrowserSession()
        return browser

    events, ok, failed = [], 0, 0
    try:
        for i, slug in enumerate(todo):
            entry = companies[slug]
            st = state.setdefault(slug, blank_state())
            if i:
                time.sleep(DELAY_BETWEEN_COMPANIES_SEC)
            try:
                text, switched = fetch_company_text(entry, browser_factory)
            except Blocked as e:
                entry["status"] = "blocked"
                append_check("capture", slug, False, f"robots.txt disallows {e}")
                report_problem(f"{entry['name']}: robots.txt blocks {e}; company set to blocked", "capture")
                failed += 1
                continue
            except FetchError as e:
                failed += 1
                st["fail_runs"] += 1
                st["last_error"] = str(e)
                append_check("capture", slug, False, str(e))
                if entry["status"] == "candidate":
                    if st["fail_runs"] >= FAIL_RUNS_TO_ALERT:      # a suggested URL gets two days to load
                        _reject_candidate(entry, f"fetch failed {st['fail_runs']} times: {e}")
                        st["fail_runs"] = 0
                elif st["fail_runs"] == FAIL_RUNS_TO_ALERT:
                    report_problem(f"{entry['name']}: {st['fail_runs']} failed captures in a row ({e})", "capture")
                elif st["fail_runs"] >= FAIL_RUNS_TO_PAUSE:
                    entry["status"] = "paused"
                    report_problem(f"{entry['name']}: paused after {st['fail_runs']} failed captures", "capture")
                continue

            if args.dry_run:
                print(f"--- {slug} ({len(text)} chars, prices={looks_like_pricing(text)})\n{text[:1500]}")
                continue

            if entry["status"] == "candidate":                 # first good capture verifies the URL
                if not looks_like_pricing(text):
                    _reject_candidate(entry, "page shows no prices")
                    failed += 1
                    continue
                entry["status"] = "active"
                append_check("registry_url", slug, True, ", ".join(entry["pricing_urls"]))
            if switched:
                entry["capture"] = "browser"
                log(f"  {slug}: switched to browser capture")

            text_again = None
            if st["confirmed_hash"] and sha(text) != st["confirmed_hash"]:
                time.sleep(3)
                try:
                    text_again, _ = fetch_company_text(entry, browser_factory)
                except (FetchError, Blocked):
                    text_again = None
            event = step_company(st, slug, text, text_again, stamp, at)
            append_check("capture", slug, True, "changed" if event else "")
            ok += 1
            if event:
                write_diff_file(event)
                events.append(event)
                log(f"  {slug}: confirmed change → {event['diff_id']}")
    finally:
        if browser:
            browser.close()

    if args.dry_run:
        return 0
    save_json(REGISTRY, registry)
    save_json(CAPTURE_STATE, state)
    report = {"run": stamp, "captured_ok": ok, "failed": failed, "attempted": len(todo), "changes": events}
    backlog = load_json(BACKLOG, {"changes": []})
    for e in events:
        e["attempts"] = 0
    backlog["changes"].extend(events)
    for e in backlog["changes"]:
        e["attempts"] = e.get("attempts", 0) + 1
    save_json(BACKLOG, backlog)
    save_json(PROPOSALS / f"{stamp}.input.json", {"run": stamp, "changes": backlog["changes"]})
    save_json(RUN / f"capture_{stamp}.json", report)
    log(f"capture: {ok} ok, {failed} failed, {len(events)} confirmed changes")
    return 0


def _reject_candidate(entry: dict, why: str) -> None:
    """A suggested pricing URL didn't work: back to needs_url, or dead after URL_ATTEMPTS_MAX tries."""
    entry["url_attempts"] = entry.get("url_attempts", 0) + 1
    entry["notes"] = f"rejected {', '.join(entry['pricing_urls'])}: {why}"
    entry["pricing_urls"] = []
    entry["status"] = "dead" if entry["url_attempts"] >= URL_ATTEMPTS_MAX else "needs_url"
    append_check("registry_url", entry["name"], False, why)


if __name__ == "__main__":
    raise SystemExit(main())
