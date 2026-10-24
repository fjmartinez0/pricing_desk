"""Write the batch of PricingSaaS reports that need an agent decision (agent/reports_prompt.md).

Each report comes with a guess at the matching registry company and the records we already have for
that company and week, so the agent can map the company and avoid duplicates.

Writes proposals/<run>.reports_input.json (committed for audit). Exit code 0 = there is work, 10 = nothing to do.
"""
from __future__ import annotations

from apply_proposals import slugify
from common import DESK, PROPOSALS, REGISTRY, REPORTS, REPORTS_BATCH, load_json, run_id, save_json

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


def main() -> int:
    reports = load_json(REPORTS, {"reports": []})
    todo = [r for r in reports["reports"] if r["status"] == "todo"]
    if not todo:
        return NOTHING
    todo.sort(key=lambda r: (r["week"], r["report_id"]), reverse=True)     # newest weeks first
    batch = todo[:REPORTS_BATCH]
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
    save_json(PROPOSALS / f"{run_id()}.reports_input.json", {"run": run_id(), "reports": out})
    save_json(REPORTS, reports)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
