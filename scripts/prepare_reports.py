"""Write the batch of PricingSaaS reports that need an agent decision (agent/reports_prompt.md).

Each report comes with a guess at the matching registry company and the records we already have for
that company and week, so the agent can map the company and avoid duplicates.

The queue is split into parts of REPORTS_BATCH reports, at most REPORTS_PARTS per run, one agent call each
(a backfill drains faster while each call stays small):
  prepare_reports.py           writes proposals/<run>.reports_input.<n>.json; exit 0 = work, 10 = nothing to do
  (run_daily.sh runs the agent on each part → proposals/<run>.reports.<n>.json)
  prepare_reports.py --merge   joins the parts the agent answered into proposals/<run>.reports_input.json and
                               proposals/<run>.reports.json (what apply_proposals.py reads), then removes the parts.
A part the agent did not answer (usage limit, invalid JSON) is left out of both files, so its reports cost no
attempt and simply wait for the next run (D46).
"""
from __future__ import annotations

import sys

from apply_proposals import slugify
from common import (DESK, PROPOSALS, REGISTRY, REPORTS, REPORTS_BATCH, REPORTS_PARTS, RUN, load_json, log,
                    report_problem, run_id, save_json)

NOTHING = 10


def guess_company(ps_slug: str, title: str, companies: dict) -> str | None:
    """Registry slug for a PricingSaaS company slug ("atlassian.bitbucket", "acuityscheduling"), if obvious."""
    for slug, e in companies.items():
        if ps_slug in (e.get("ps_slugs") or []):
            return slug
    head = ps_slug.split(".")[0]
    for slug, e in companies.items():
        names = {slug, slug.replace("-", ""), slugify(e["name"]), slugify(e["name"]).replace("-", "")}
        if head in names or ps_slug.replace(".", "-") in names:
            return slug
    return None


def part_files(run: str) -> list[tuple[int, object, object]]:
    """(n, input path, output path) of every part written for this run, in order."""
    out = []
    for f in sorted(PROPOSALS.glob(f"{run}.reports_input.*.json"), key=lambda f: int(f.name.split(".")[-2])):
        n = int(f.name.split(".")[-2])
        out.append((n, f, PROPOSALS / f"{run}.reports.{n}.json"))
    return out


def merge(run: str) -> int:
    handed, items, missing = [], [], 0
    for n, fin, fout in part_files(run):
        part = load_json(fin, {}).get("reports", [])
        try:
            prop = load_json(fout)
        except ValueError as e:
            report_problem(f"{fout.name} is not valid JSON ({e}); its {len(part)} reports wait for the next run.", "merge")
            prop = None
        if isinstance(prop, dict) and prop.get("type") == "reports" and isinstance(prop.get("items"), list):
            handed += part
            items += prop["items"]
        else:
            missing += len(part)
        fin.unlink()
        if fout.exists():
            fout.unlink()
    if handed:
        save_json(PROPOSALS / f"{run}.reports_input.json", {"run": run, "reports": handed})
        save_json(PROPOSALS / f"{run}.reports.json", {"type": "reports", "run": run, "items": items})
    if missing and not (RUN / f"agent_limited_{run}").exists():   # a usage limit has its own alert
        report_problem(f"Agent wrote no decision for {missing} PricingSaaS reports; they wait for the next run.",
                       "coverage")
    log(f"reports: {len(handed)} handed and answered, {len(items)} decisions, {missing} waiting")
    return 0


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    run = run_id()
    if "--merge" in argv:
        return merge(run)
    for _, fin, fout in part_files(run):     # a second run in the same hour starts clean (D47)
        fin.unlink()
        if fout.exists():
            fout.unlink()
    reports = load_json(REPORTS, {"reports": []})
    todo = [r for r in reports["reports"] if r["status"] == "todo"]
    if not todo:
        return NOTHING
    todo.sort(key=lambda r: (r["week"], r["report_id"]), reverse=True)     # newest weeks first
    batch = todo[:REPORTS_BATCH * max(1, REPORTS_PARTS)]
    companies = load_json(REGISTRY)["companies"]
    desk = load_json(DESK)
    out = []
    for r in batch:
        guess = guess_company(r["ps_slug"], r.get("title") or "", companies)
        existing = [{"id": c["id"], "short": c.get("short"), "src": c.get("src")} for c in desk["changes"]
                    if guess and c.get("company") == guess and c["week"] == r["week"]]
        out.append({"report_id": r["report_id"], "week": r["week"], "change_date": r.get("change_date"),
                    "urls": r["urls"], "files": r["files"], "article_files": r["article_files"],
                    "title": r.get("title"), "registry_guess": guess,
                    "registry_name": companies[guess]["name"] if guess else None,
                    "existing_records": existing})
    for n in range(0, len(out), REPORTS_BATCH):
        save_json(PROPOSALS / f"{run}.reports_input.{n // REPORTS_BATCH}.json",
                  {"run": run, "reports": out[n:n + REPORTS_BATCH]})
    log(f"reports: {len(out)} of {len(todo)} waiting handed to the agent in {-(-len(out) // REPORTS_BATCH)} part(s)")
    save_json(REPORTS, reports)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
