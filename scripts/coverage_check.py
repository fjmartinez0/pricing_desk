"""Step 2b: quiet alerts when the run did less work than it should. Never blocks the run.

Checks:
  * enough tracked pages captured (MIN_CAPTURE_OK_RATIO);
  * the agent decided on every confirmed change (each diff_id appears once in the proposal);
  * the agent wrote its proposal files when it was asked to.

Usage: python3 scripts/coverage_check.py [--run RUN_ID]
"""
from __future__ import annotations

import argparse

from common import MIN_CAPTURE_OK_RATIO, PROPOSALS, RUN, load_json, log, report_problem, run_id


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", default=run_id())
    run = ap.parse_args().run

    cap = load_json(RUN / f"capture_{run}.json")
    if cap and cap["attempted"]:
        ratio = cap["captured_ok"] / cap["attempted"]
        if ratio < MIN_CAPTURE_OK_RATIO:
            report_problem(f"Only {cap['captured_ok']} of {cap['attempted']} pricing pages captured ({ratio:.0%}).", "coverage")

    inputs = load_json(PROPOSALS / f"{run}.input.json", {})
    wanted = {e["diff_id"] for e in inputs.get("changes", [])}
    if wanted:
        prop = load_json(PROPOSALS / f"{run}.changes.json")
        if prop is None:
            report_problem(f"Agent wrote no change proposal for {len(wanted)} confirmed page changes; they stay in the backlog and are retried.", "coverage")
        else:
            got = {i.get("diff_id") for i in prop.get("items", [])}
            missing = wanted - got
            if missing:
                report_problem(f"Agent skipped {len(missing)} of {len(wanted)} page changes: {', '.join(sorted(missing))[:300]}", "coverage")
    if (RUN / f"edition_due_{run}.json").exists() and not (PROPOSALS / f"{run}.edition.json").exists():
        report_problem("Edition was due but the agent wrote no edition proposal; it will be retried.", "coverage")
    log("coverage check done")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
