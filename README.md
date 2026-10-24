# Pricing Desk

A phone-friendly newspaper of software price changes. A Mac mini captures the pricing pages of
every tracked company twice a day, Claude (headless Claude Code) classifies and writes up what
changed, Python code decides what is published, and GitHub Pages serves the page. Alerts go to
the iPhone through ntfy (topic `fmz_pricing_desk`).

**The AI proposes; code decides.** Every number on a card must appear in the captured page text,
"They say" quotes must be found on the company's own site, and two validation gates (on the Mac
and in GitHub Actions) stop anything broken from going live.

- Install and first run: `docs/PROJECT_CONTEXT.md`, section "Install and first run".
- Everyday operations and alerts: `RUNBOOK.md`.
- How the page and code are built: `docs/BUILD_GUIDE.md`.

## A run (07:00 and 19:00, America/Toronto)
```
launchd → scripts/run_daily.sh
  1 pull, snapshot desk.json        6 recheck.py      quotes and news numbers checked online
  2 capture.py   pricing pages      7 validate.py     integrity rules (abort + alert)
  3 Claude       changes / registry / edition (writes proposals/ only)
  4 coverage_check.py (quiet alerts) 8 stamp, commit, push → GitHub Actions validates and deploys
  5 apply_proposals.py (the rules)  9 notify.py       iPhone alerts
```

## Layout
```
site/template.html        the dashboard, unchanged, with its data block as __PD_DATA__
data/desk.json            everything the page shows (injected at publish time)
data/registry.json        the companies we track: our own list, with pricing URLs
data/capture_state.json   per-company capture state;  data/backlog.json  changes awaiting a decision
data/snapshots/<slug>/    confirmed page texts: the evidence behind every card
data/checks.jsonl         append-only log of every external check;  data/meta.json  last run
proposals/                every agent output and input, committed for audit
agent/                    prompts for the three agent tasks + news sources
scripts/                  one script per step (see docstrings); common.py holds every rule
tests/                    unit tests on known cases (python3 -m unittest discover -s tests -v)
launchd/                  the schedule;  .github/workflows/  publish + watchdog
```

## Handy commands
```bash
python3 scripts/capture.py --company slack --dry-run     # see what we capture for one company
python3 scripts/add_company.py --name "Loom" --url https://www.loom.com/pricing --category "Collaboration & Productivity"
python3 scripts/build_site.py --out preview.html         # open the page offline
python3 scripts/validate.py                              # integrity check
python3 scripts/notify.py --test                         # test the iPhone notification
PD_LOG_TO_TERMINAL=1 bash scripts/run_daily.sh           # a full run in the terminal
```
Standard-library Python except `scripts/browser_capture.py` (Playwright), used only for pages that
need JavaScript.
