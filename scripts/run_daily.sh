#!/bin/bash
# Pricing Desk: one run (launchd starts it at 07:00 and 19:00, Toronto time).
#
#   1. pull; snapshot desk.json               5. merge proposals (code decides)
#   2. capture pricing pages                  6. recheck today's additions online
#   2b. read PricingSaaS (reports, D39)       7. validate (abort + alert on failure)
#   3. agent: changes / reports / registry /  8. stamp, commit, push
#      edition                                9. notify
#   4. coverage check (quiet alerts)
#
# Manual run: bash scripts/run_daily.sh        (logs go to logs/<date>.log)
set -uo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO"
export PATH="/Library/Frameworks/Python.framework/Versions/Current/bin:$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"
[ -f config.env ] && { set -a; . ./config.env; set +a; }
export PD_RUN_ID="$(date +%Y-%m-%dT%H)"
RUN="$PD_RUN_ID"
mkdir -p logs .run
LOG="logs/$(date +%Y-%m-%d).log"
[ "${PD_LOG_TO_TERMINAL:-0}" = "1" ] || exec >>"$LOG" 2>&1
echo; echo "######## run $RUN ($(date))"

LOCK=".run/lock"
if ! mkdir "$LOCK" 2>/dev/null; then
  age=$(( $(date +%s) - $(stat -f %m "$LOCK" 2>/dev/null || echo 0) ))
  if [ "$age" -gt 21600 ]; then echo "removing stale lock"; rm -rf "$LOCK"; mkdir "$LOCK"
  else echo "another run is active; exiting"; exit 0; fi
fi
trap 'rm -rf "$LOCK"' EXIT

fail() {
  echo "FAILED at: $1"
  python3 scripts/notify.py --problem "Run $RUN stopped at: $1. Details in $LOG on the Mac mini."
  exit 1
}
step() { echo "== $1"; }
agent() {   # run one agent task unless this run already hit the Claude usage limit
  if [ -f ".run/agent_limited_$RUN" ]; then echo "agent: skipped ($(basename "$1" .md)): usage limit"; return 0; fi
  bash scripts/run_agent.sh "$@"
}
has() { python3 -c "import json,sys; d=json.load(open('$1')); sys.exit(0 if d.get('$2') else 1)" 2>/dev/null; }

step "1 pull"
git pull --ff-only || fail "git pull"
cp data/desk.json .run/desk_before.json

step "2 capture"
python3 scripts/capture.py || fail "capture"

step "2b pricingsaas"
python3 scripts/pricingsaas_capture.py || python3 scripts/notify.py --problem "PricingSaaS reading failed in run $RUN; own captures unaffected."

step "3 agent"
if has "proposals/$RUN.input.json" changes; then
  agent agent/changes_prompt.md "proposals/$RUN.input.json" "proposals/$RUN.changes.json"
fi
if python3 scripts/prepare_reports.py; then     # PricingSaaS diff pages waiting for a decision
  agent agent/reports_prompt.md "proposals/$RUN.reports_input.json" "proposals/$RUN.reports.json"
fi
if python3 scripts/prepare_registry.py; then   # until every company has a pricing URL
  agent agent/registry_prompt.md ".run/registry_todo_$RUN.json" "proposals/$RUN.registry.json"
fi
if python3 scripts/close_week.py; then
  WEEK="$(python3 -c "import json; print(json.load(open('.run/edition_due_$RUN.json'))['week'])")"
  LABEL="$(cd scripts && python3 -c "from common import week_range_label; print(week_range_label('$WEEK'))")"
  agent agent/edition_prompt.md "data/desk.json" "proposals/$RUN.edition.json" \
    "$WEEK" "$LABEL" ".run/week_stats_$RUN.json"
fi

step "4 coverage"
python3 scripts/coverage_check.py

step "5 merge"
python3 scripts/apply_proposals.py || fail "merge"

step "6 recheck"
python3 scripts/recheck.py || python3 scripts/notify.py --problem "Recheck failed in run $RUN; records kept unchecked."

step "7 validate"
if ! python3 scripts/validate.py; then
  git stash push --include-untracked -m "failed validation $RUN" -- data proposals >/dev/null 2>&1
  fail "validate (changes stashed as 'failed validation $RUN'; nothing published)"
fi

step "8 commit"
python3 scripts/stamp_meta.py
git add data proposals
if ! git diff --cached --quiet; then
  added=$(python3 -c "import json; d=json.load(open('.run/merge_$RUN.json')); print(len(d['added']))" 2>/dev/null || echo 0)
  git commit -q -m "run $RUN: +$added changes" || fail "git commit"
  git push -q || { git pull --rebase -q && git push -q; } || fail "git push"
fi

step "9 notify"
python3 scripts/notify.py --before .run/desk_before.json
echo "######## done $RUN ($(date))"
