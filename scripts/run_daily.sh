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
rm -f ".run/problems_$RUN.jsonl" ".run/agent_limited_$RUN" ".run/agent_auth_$RUN" .run/agent_error_"$RUN"_*   # a 2nd run in the same hour starts clean

fail() {
  echo "FAILED at: $1"
  # send the problems already raised in this run (e.g. a company failing to load); step 9 won't run
  [ -f .run/desk_before.json ] && python3 scripts/notify.py --before .run/desk_before.json || true
  python3 scripts/notify.py --problem "Run $RUN stopped at: $1. Details in $LOG on the Mac mini."
  exit 1
}
step() { echo "== $1"; }
# Time limits (D57): launchd never starts a run while the last one is still going, so a step that never
# returns would silently stop every later run. Each step that waits on the network, a browser or Claude
# runs under scripts/limit.py (exit 124 = stopped). Override in config.env; values in seconds.
L_GIT="${PD_LIMIT_GIT:-300}"; L_CAPTURE="${PD_LIMIT_CAPTURE:-5400}"; L_PRICINGSAAS="${PD_LIMIT_PRICINGSAAS:-2400}"
L_AGENT="${PD_LIMIT_AGENT:-2700}"; L_RECHECK="${PD_LIMIT_RECHECK:-1200}"; L_PAGECHECK="${PD_LIMIT_PAGECHECK:-600}"
lim() { python3 scripts/limit.py "$@"; }
mins() { echo "$(( $1 / 60 )) min"; }
agent() {   # run one agent task unless this run already hit the Claude usage limit
  if [ -f ".run/agent_limited_$RUN" ]; then echo "agent: skipped ($(basename "$1" .md)): usage limit or login"; return 0; fi
  lim "$L_AGENT" bash scripts/run_agent.sh "$@"
  if [ $? -eq 124 ]; then
    python3 scripts/notify.py --problem "Agent task $(basename "$1" .md) stopped after $(mins "$L_AGENT") in run $RUN; its items stay queued for the next run."
  fi
  return 0
}
has() { python3 -c "import json,sys; d=json.load(open('$1')); sys.exit(0 if d.get('$2') else 1)" 2>/dev/null; }

step "1 pull"
lim "$L_GIT" git pull --ff-only || fail "git pull"
cp data/desk.json .run/desk_before.json

step "2 capture"
lim "$L_CAPTURE" python3 scripts/capture.py; rc=$?
if [ $rc -ne 0 ]; then
  git clean -fdq -- data/snapshots     # snapshots of an unfinished capture: their state was never saved
  [ $rc -eq 124 ] && fail "capture (stopped after $(mins "$L_CAPTURE"); the next run starts it again)"
  fail "capture"
fi

step "2b pricingsaas"
lim "$L_PRICINGSAAS" python3 scripts/pricingsaas_capture.py || python3 scripts/notify.py --problem "PricingSaaS reading failed or took over $(mins "$L_PRICINGSAAS") in run $RUN; own captures unaffected."

step "3 agent"
if has "proposals/$RUN.input.json" changes; then
  agent agent/changes_prompt.md "proposals/$RUN.input.json" "proposals/$RUN.changes.json"
fi
if python3 scripts/prepare_reports.py; then     # PricingSaaS diff pages waiting for a decision, in parts
  n=0
  while [ -f "proposals/$RUN.reports_input.$n.json" ]; do
    agent agent/reports_prompt.md "proposals/$RUN.reports_input.$n.json" "proposals/$RUN.reports.$n.json"
    n=$((n + 1))
  done
  python3 scripts/prepare_reports.py --merge
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
lim "$L_RECHECK" python3 scripts/recheck.py || python3 scripts/notify.py --problem "Recheck failed or took over $(mins "$L_RECHECK") in run $RUN; records kept unchecked."

step "7 validate"
if ! python3 scripts/validate.py; then
  git stash push --include-untracked -m "failed validation $RUN" -- data proposals >/dev/null 2>&1
  fail "validate (changes stashed as 'failed validation $RUN'; nothing published)"
fi
lim "$L_PAGECHECK" python3 scripts/check_page.py   # a JavaScript error on the page → alert (D53); data still published
[ $? -eq 124 ] && python3 scripts/notify.py --problem "Page check took over $(mins "$L_PAGECHECK") in run $RUN; data published unchecked."

step "8 commit"
python3 scripts/stamp_meta.py
git add data proposals
if ! git diff --cached --quiet; then
  added=$(python3 -c "import json; d=json.load(open('.run/merge_$RUN.json')); print(len(d['added']))" 2>/dev/null || echo 0)
  git commit -q -m "run $RUN: +$added changes" || fail "git commit"
  lim "$L_GIT" git push -q || { lim "$L_GIT" git pull --rebase -q && lim "$L_GIT" git push -q; } || fail "git push"
fi

step "9 notify"
python3 scripts/notify.py --before .run/desk_before.json
echo "######## done $RUN ($(date))"
