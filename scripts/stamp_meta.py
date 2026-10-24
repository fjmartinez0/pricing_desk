"""Record the run time in data/meta.json (the watchdog workflow alerts if it gets stale)."""
from __future__ import annotations

from common import CAPTURE_STATE, META, REGISTRY, load_json, now, run_id, save_json


def main() -> int:
    meta = load_json(META, {"schema_version": 1})
    reg = load_json(REGISTRY)["companies"]
    meta.update(last_run_at=now().isoformat(timespec="seconds"), last_run_id=run_id(),
                tracked_active=sum(e["status"] == "active" for e in reg.values()),
                tracked_total=len(reg), captured_companies=len(load_json(CAPTURE_STATE, {})))
    save_json(META, meta)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
