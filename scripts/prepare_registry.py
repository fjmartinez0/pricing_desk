"""Write the batch of companies that still need a pricing URL, for the registry agent.

Writes .run/registry_todo_<run>.json. Exit code 0 = there is work, 10 = nothing to do.
"""
from __future__ import annotations

from common import REGISTRY, REGISTRY_BATCH, RUN, load_json, run_id, save_json

NOTHING = 10


def main() -> int:
    companies = load_json(REGISTRY)["companies"]
    todo = [{"slug": s, "name": e["name"], "category": e.get("category"), "notes": e.get("notes", "")}
            for s, e in companies.items() if e["status"] == "needs_url"]
    todo.sort(key=lambda x: (companies[x["slug"]].get("tier") or 3, x["slug"]))
    if not todo:
        return NOTHING
    save_json(RUN / f"registry_todo_{run_id()}.json", {"companies": todo[:REGISTRY_BATCH]})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
