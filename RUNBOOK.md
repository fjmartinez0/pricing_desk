# Runbook

## Where to look
- Today's log: `logs/YYYY-MM-DD.log` (each run starts with `######## run …`).
- What the merge accepted or rejected: `.run/merge_<run>.json`; what the agent proposed: `proposals/<run>.*.json`.
- Every external check: `data/checks.jsonl` (`grep '"ok": false' data/checks.jsonl | tail`).

## Alerts on the iPhone
| Title | Meaning | What to do |
|---|---|---|
| `<Company> +20%` / `N market-leader price changes` | New changes from market leaders or watchlist companies | Tap to read |
| `Edition 2026-Wnn published` | Monday 19:00 edition is live | Tap to read |
| `Pricing Desk: N problems` | Something needs attention; the list says which step | See below |
| `Pricing Desk problem: Run … stopped at: …` | A step failed; nothing was published | Read the log; fix; `PD_LOG_TO_TERMINAL=1 bash scripts/run_daily.sh` |
| `Pricing Desk: Mac mini silent` | No run in 36 hours (from GitHub) | Power, login, network; `launchctl print gui/$(id -u)/com.fmz.pricing_desk` |

Common problems:
- **`<Company>: 4 failed captures in a row`**: the page moved or blocks us. Open the URL; fix with
  `python3 scripts/add_company.py --slug <slug> --url <new url>`, or `--browser` if it needs JavaScript,
  or `--status paused`.
- **`robots.txt blocks …`**: the site forbids automated access. Leave it blocked (principle 7).
- **`Only N of M pricing pages captured`**: network or site outage; usually fixes itself.
- **`Agent wrote no change proposal`**: Claude failed or hit limits. The changes stay in
  `data/backlog.json` and are retried; check `claude auth status` if it repeats.
- **`Edition not published: …`**: retried every run until it succeeds; the reason says which check failed.
- **`validate` failure**: the run's changes are stashed (`git stash list`), nothing is published.
  Inspect with `git stash show -p stash@{0}`; drop it with `git stash drop` once understood.

## Everyday tasks
- **Add or fix a company:** `python3 scripts/add_company.py …` (see `--help`), then commit and push, or
  wait for the next run to commit it.
- **Change a rule:** edit `scripts/common.py` (enums, keep rule, thresholds), add a test in
  `tests/test_pipeline.py`, run `python3 -m unittest discover -s tests -v`, commit.
- **Edit the agent's instructions:** `agent/*.md`. News sources: `agent/sources.json`.
- **Fix a published record by hand:** edit `data/desk.json`, run `python3 scripts/validate.py`, commit, push.
  Records are append-only by convention: correct fields, don't delete records.
- **Preview the page:** `python3 scripts/build_site.py --out preview.html && open preview.html`.
- **Pause everything:** `launchctl bootout gui/$(id -u)/com.fmz.pricing_desk`; resume with `bash scripts/install_mac.sh`.
- **Update the dashboard design:** edit `site/template.html` only; keep the single `__PD_DATA__` placeholder.
