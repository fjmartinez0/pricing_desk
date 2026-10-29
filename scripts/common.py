"""Shared paths, rules, enums and small helpers for Pricing Desk.

Every rule that decides what enters the data lives in this file, so changing a
rule means editing one place. Standard library only.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import re
import sys
from pathlib import Path
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

# ---------------------------------------------------------------- paths
ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
DESK = DATA / "desk.json"                 # everything the page shows (injected into pd-data)
REGISTRY = DATA / "registry.json"         # companies we track, owned by us
CAPTURE_STATE = DATA / "capture_state.json"
BACKLOG = DATA / "backlog.json"            # confirmed changes waiting for an agent decision
SNAPSHOTS = DATA / "snapshots"            # confirmed page text, one file per version
CHECKS = DATA / "checks.jsonl"            # append-only log of every external check
META = DATA / "meta.json"
PROPOSALS = ROOT / "proposals"
AGENT = ROOT / "agent"
SITE = ROOT / "site"
RUN = ROOT / ".run"                       # per-run scratch files (gitignored)
LOGS = ROOT / "logs"
PS_DIR = DATA / "pricingsaas"             # PricingSaaS pages we read (hybrid, D39): evidence for reported records
PS_INDEX = PS_DIR / "index.json"           # every PricingSaaS URL seen, with its status
REPORTS = DATA / "reports.json"            # PricingSaaS diff pages waiting for a decision or for our own capture

# ---------------------------------------------------------------- time
TZ = ZoneInfo("America/Toronto")

# Edition: a week runs Monday–Sunday. It can be closed once this long has
# passed after the week ends (Monday 00:00), so Sunday changes are confirmed.
EDITION_READY_AFTER = dt.timedelta(hours=42)   # Tue 19:00: PricingSaaS posts its weekly batch on Monday (D49)
# Weeks before this one were built by hand from PricingSaaS; never auto-close them.
FIRST_AUTO_EDITION = "2026-W44"
CAPTURES_STARTED = dt.date(2026, 10, 24)   # first day of our own pricing-page captures

# ---------------------------------------------------------------- capture rules
USER_AGENT = "PricingDesk/1.0 (personal software price tracker)"
REQUEST_TIMEOUT_SEC = 30
DELAY_BETWEEN_COMPANIES_SEC = float(os.environ.get("CAPTURE_DELAY_SEC", "2"))
DEBOUNCE_CAPTURES = 2        # a new page version must be seen this many captures in a row
UNSTABLE_RUNS_TO_REPORT = 3  # page flips between versions this many runs → report as a possible price test
FAIL_RUNS_TO_ALERT = 4       # failed captures in a row before a problem alert (2 days)
FAIL_RUNS_TO_PAUSE = 14      # failed captures in a row before the company is paused (7 days)
URL_ATTEMPTS_MAX = 3         # agent URL suggestions that failed before we give up (status "dead")
REGISTRY_BATCH = 30          # needs_url entries handed to the agent per run
MIN_CAPTURE_OK_RATIO = 0.9   # below this, coverage_check sends a quiet alert
BACKLOG_MAX_ATTEMPTS = 4     # agent runs a change may wait for a decision before it is given up (2 days)

# ---------------------------------------------------------------- PricingSaaS reports (hybrid, D39–D42)
PS_BASE = "https://pricingsaas.com"
PS_NEWS_URL = PS_BASE + "/news"                       # daily briefings, "Load more" goes back about 9 days
PS_REVIEW_URL = PS_BASE + "/news/week/{year}W{week:02d}"   # weekly review; same week numbers as ours
PS_FEED_URL = PS_BASE + "/feed"                       # move explorer: every change of the last 7 days (one weekly batch)
PS_LOAD_MORE_MAX = 40          # "Load more" clicks per run at most
PS_MAX_FETCHES = 150           # PricingSaaS pages fetched per run at most (polite; the rest wait)
PS_DELAY_SEC = float(os.environ.get("PS_DELAY_SEC", "2"))
REPORTS_BATCH = 40             # reports handed to the agent per agent call (one "part")
REPORTS_PARTS = int(os.environ.get("PD_REPORTS_PARTS", "3"))   # agent calls per run for reports, while the queue lasts
REPORT_MAX_ATTEMPTS = 4        # agent runs a report may wait for a decision before it is given up
REPORT_WAIT_RUNS = 4           # a change at a company we already capture waits this many runs for our own capture
REPORTS_PER_COMPANY_WEEK = 3   # reported records per company per week at most
# Text after these lines on a PricingSaaS diff page is about other changes (history, peers, FAQ): cut it,
# so a reported record's numbers must come from this change only.
PS_CUT_MARKERS = [r"^\S.*\b\d+-day history\b", r"^Related\b", r"^Frequently asked\b", r"^FAQ\b",
                  r"^Ask the Pulse Agent\b", r"^Current .* plans\b"]

# Sites that copy other companies' prices. Never accepted as a pricing page. PricingSaaS diff pages are the
# one exception as proof: they back records marked "reported" (SRC_REPORTED), never our own captures.
AGGREGATOR_DOMAINS = {
    "pricingsaas.com", "g2.com", "capterra.com", "getapp.com", "softwareadvice.com",
    "saasworthy.com", "trustradius.com", "saaspricepulse.com", "vendr.com", "producthunt.com",
}

# ---------------------------------------------------------------- record enums
GROUPS = {"up", "down", "pack"}                       # pay more / pay less / restructured
SEGMENTS = {"B2B", "B2C", "Both"}
PLAN_LEVELS = {"free", "entry", "mid", "top", "enterprise", "all", "add-on"}
APPLIES_TO = {"all", "new", "existing", "unknown"}
MODELS = {"Seat", "Usage", "Flat", "Hybrid"}          # "A → B" is allowed for `model` only
MAGNITUDE_BASIS = {"list price", "unit price", "allowance", "minimum"}
TIERS = {1, 2, 3}
REACH = {1, 2, 3}                                     # 1 few customers, 2 some, 3 most
PROMO_KINDS = {"new", "changed", "ended"}
PATTERNS = [
    "Price increase", "Price cut",
    "Bundling", "Unbundling", "Tier consolidation", "New tier", "Rename & reposition",
    "Limits tighten", "Limits loosen", "Minimums",
    "Billing terms", "New billing units",
    "AI gets a meter", "AI moves between tiers", "AI costs pass through",
    "Free plans as funnels",
]
MAX_ROWS = 5

# Keep rule (D18). The agent classifies every page change into one kind;
# the merger keeps or drops it by this table, never by the agent's say-so.
KEEP_KINDS = {
    "price_increase", "price_cut", "limit_change", "plan_change", "feature_move",
    "metering", "free_plan", "became_paid",
}
DROP_KINDS = {
    "new_feature", "wording", "price_reveal", "price_hidden", "trial", "support",
    "non_software", "duplicate", "noise",
}
PROMO_KIND = "promo"
ALL_KINDS = KEEP_KINDS | DROP_KINDS | {PROMO_KIND}

REGISTRY_STATUS = {"active", "candidate", "needs_url", "paused", "blocked", "dead"}
CAPTURE_MODES = {"static", "browser"}

# Watchlist (D15/D16): always tier 1.
WATCHLIST = [
    "notion", "canva", "slack", "hubspot", "figma", "1password", "duolingo", "zoom",
    "atlassian", "microsoft-365", "adobe", "openai", "linear", "airtable", "calendly",
    "dropbox", "salesforce", "intercom", "zapier", "grammarly",
]

SRC_CAPTURE = "Pricing Desk capture"
SRC_REPORTED = "PricingSaaS report"       # change reported by PricingSaaS; numbers checked against their diff page


# ---------------------------------------------------------------- weeks
def now() -> dt.datetime:
    return dt.datetime.now(TZ)


def week_label(day: dt.date) -> str:
    """Week label used by the page, e.g. 2026-10-05 → "2026-W42".

    The page inherited PricingSaaS's numbering, which is one ahead of ISO:
    week N here is ISO week N−1 (Monday–Sunday). Keep it for continuity.
    """
    iso = (day + dt.timedelta(days=7)).isocalendar()
    return f"{iso.year}-W{iso.week:02d}"


def week_start(label: str) -> dt.date:
    year, week = label.split("-W")
    return dt.date.fromisocalendar(int(year), int(week), 1) - dt.timedelta(days=7)


def ps_period_week(period: str) -> tuple[str, dt.date | None]:
    """PricingSaaS diff period → (our week label, change date or None).

    "2026W43" is a week (same numbering as ours). "2026D294" is day 294 of 2026 (21 Oct): the page shows
    the change between day 293 and day 294, so the change belongs to the week of day 293, the last day
    that still showed the old page (same rule as our captures, D28).
    """
    m = re.fullmatch(r"(\d{4})([WD])(\d{1,3})", period or "")
    if not m:
        raise ValueError(f"not a PricingSaaS period: {period!r}")
    year, kind, n = int(m.group(1)), m.group(2), int(m.group(3))
    if kind == "W":
        return f"{year}-W{n:02d}", None
    day = dt.date(year, 1, 1) + dt.timedelta(days=n - 1)
    return week_label(day - dt.timedelta(days=1)), day


def short_date(day: dt.date) -> str:
    return f"{day.day} {day.strftime('%b')}"


def week_range_label(label: str) -> str:
    """"5–11 Oct" or "28 Sep–4 Oct"."""
    start = week_start(label)
    end = start + dt.timedelta(days=6)
    if start.month == end.month:
        return f"{start.day}–{end.day} {end.strftime('%b')}"
    return f"{short_date(start)}–{short_date(end)}"


def week_key(label: str) -> tuple[int, int]:
    year, week = label.split("-W")
    return int(year), int(week)


def change_id(slug: str, week: str, taken: set[str]) -> str:
    base = f"{slug}-{week.lower().replace('-', '')}"
    if base not in taken:
        return base
    n = 2
    while f"{base}-{n}" in taken:
        n += 1
    return f"{base}-{n}"


# ---------------------------------------------------------------- files
def load_json(path: Path, default=None):
    if not path.exists():
        return default
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def save_json(path: Path, obj) -> None:
    """Write JSON atomically, one key per line so git diffs stay readable."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)
        f.write("\n")
    tmp.replace(path)


def run_id() -> str:
    """Identifies this run in file names: set by run_daily.sh, else derived from the clock."""
    return os.environ.get("PD_RUN_ID") or now().strftime("%Y-%m-%dT%H")


def append_check(kind: str, target: str, ok: bool, detail: str = "") -> None:
    """Append one external check to data/checks.jsonl (the audit log)."""
    CHECKS.parent.mkdir(parents=True, exist_ok=True)
    row = {"at": now().isoformat(timespec="seconds"), "run": run_id(), "kind": kind,
           "target": target, "ok": ok, "detail": detail[:300]}
    with CHECKS.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def report_problem(text: str, step: str) -> None:
    """Queue a problem for notify.py (sent once at the end of the run)."""
    RUN.mkdir(parents=True, exist_ok=True)
    with (RUN / f"problems_{run_id()}.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps({"step": step, "text": text}, ensure_ascii=False) + "\n")
    log(f"PROBLEM [{step}] {text}")


def log(msg: str) -> None:
    print(f"{now().strftime('%H:%M:%S')} {msg}", file=sys.stderr, flush=True)


def sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def domain_of(url: str) -> str:
    host = (urlparse(url).hostname or "").lower()
    return host[4:] if host.startswith("www.") else host


def same_site(url: str, domains: list[str]) -> bool:
    """True if url's host is one of domains or a subdomain of one."""
    host = domain_of(url)
    return any(host == d or host.endswith("." + d) for d in domains)


def is_http_url(url) -> bool:
    return isinstance(url, str) and url.startswith(("http://", "https://"))


def load_config() -> dict:
    """Read config.env (KEY=value lines). Environment variables win."""
    cfg = {}
    path = ROOT / "config.env"
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                cfg[k.strip()] = v.strip().strip('"')
    for k in list(cfg) + ["NTFY_SERVER", "NTFY_TOPIC", "DASHBOARD_URL"]:
        if k in os.environ:
            cfg[k] = os.environ[k]
    cfg.setdefault("NTFY_SERVER", "https://ntfy.sh")
    cfg.setdefault("NTFY_TOPIC", "fmz_pricing_desk")
    return cfg


# ---------------------------------------------------------------- numbers
_NUM = re.compile(r"(?<![\w.])(\d{1,3}(?:,\d{3})+|\d+)(?:\.(\d+))?\s?([kKmM](?![a-zA-Z]))?")


def _norm_number(whole: str, frac: str | None, suffix: str | None) -> str:
    value = float(whole.replace(",", "") + ("." + frac if frac else ""))
    if suffix:
        value *= 1_000 if suffix.lower() == "k" else 1_000_000
    return f"{value:.6f}".rstrip("0").rstrip(".")


def numbers_in(text: str) -> set[str]:
    """Every number in a page text, normalized ("$1,200" → "1200", "1.6K" → "1600")."""
    return {_norm_number(*m.groups()) for m in _NUM.finditer(text or "")}


def claimed_numbers(text: str) -> set[str]:
    """Numbers a record claims as facts. Percentages, ×-multipliers and years are
    skipped: they are calculated by us, not printed on the pricing page."""
    out = set()
    for m in _NUM.finditer(text or ""):
        after = text[m.end():m.end() + 2].lstrip()
        before = text[max(0, m.start() - 1):m.start()]
        if after.startswith("%") or before in ("×", "x"):
            continue
        n = _norm_number(*m.groups())
        if n.isdigit() and 2000 <= int(n) <= 2099 and not m.group(3):
            continue
        out.add(n)
    return out
