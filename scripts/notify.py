"""Step 7: push notifications to the iPhone through ntfy (one topic, fmz_pricing_desk).

Results (normal priority): market-leader changes, watchlist companies, "edition published".
More than three results → one summary message. Problems (high priority, ⚠️ tag)
come from .run/problems_<run>.jsonl. Normal days with nothing to say send nothing.
Tapping a notification opens the dashboard.

Usage:
  python3 scripts/notify.py --before .run/desk_before.json
  python3 scripts/notify.py --problem "text"        # used by run_daily.sh when a step fails
  python3 scripts/notify.py --test                  # sends a test message
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import urllib.request
from pathlib import Path

from common import DESK, RUN, WATCHLIST, load_config, load_json, log, now, run_id, week_key, week_label

MAX_SINGLE = 3


def send(title: str, body: str, priority: str = "default", tags: str = "", cfg: dict | None = None) -> None:
    cfg = cfg or load_config()
    url = f"{cfg['NTFY_SERVER'].rstrip('/')}/{cfg['NTFY_TOPIC']}"
    headers = {"Title": title.encode("utf-8"), "Priority": priority}
    if tags:
        headers["Tags"] = tags
    if cfg.get("DASHBOARD_URL"):
        headers["Click"] = cfg["DASHBOARD_URL"]
    req = urllib.request.Request(url, data=body.encode("utf-8"), headers=headers, method="POST")
    try:
        urllib.request.urlopen(req, timeout=20).read()
    except Exception as e:  # a failed notification must never fail the run
        log(f"ntfy send failed: {e}")


def qualifying(before: dict, after: dict) -> list[dict]:
    old = {c["id"] for c in before.get("changes", [])}
    recent = week_key(week_label(now().date() - dt.timedelta(days=14)))   # backfilled reports stay quiet
    return [c for c in after["changes"]
            if c["id"] not in old and (c.get("tier") == 1 or c.get("company") in WATCHLIST)
            and not (c.get("reported") and week_key(c["week"]) < recent)]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--before")
    ap.add_argument("--problem")
    ap.add_argument("--test", action="store_true")
    args = ap.parse_args()

    if args.test:
        send("Pricing Desk test", "Notifications work. Tap to open the dashboard.", tags="white_check_mark")
        return 0
    if args.problem:
        send("Pricing Desk problem", args.problem, priority="high", tags="warning")
        return 0

    after = load_json(DESK)
    before = load_json(Path(args.before) if args.before else RUN / "desk_before.json", {})
    news = qualifying(before, after)
    if len(news) > MAX_SINGLE:
        lines = [f"{c['co']}: {c['delta']}" for c in news[:8]]
        send(f"{len(news)} market-leader price changes", "\n".join(lines), tags="chart_with_upwards_trend")
    else:
        for c in news:
            send(f"{c['co']} {c['delta']}" + (" (reported by PricingSaaS)" if c.get("reported") else ""), c["short"],
                 tags="chart_with_upwards_trend")
    if before and after.get("current_week") != before.get("current_week"):
        mc = after.get("market_context", {})
        send(f"Edition {after['current_week']} published",
             f"{mc.get('total', 0)} changes: {mc.get('increases', 0)} up, {mc.get('cuts', 0)} down.", tags="newspaper")

    path = RUN / f"problems_{run_id()}.jsonl"
    if path.exists():
        items = [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]
        if items:
            body = "\n".join(f"• [{p['step']}] {p['text']}" for p in items[:8])
            send(f"Pricing Desk: {len(items)} problem{'s' if len(items) > 1 else ''}", body, priority="high", tags="warning")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
