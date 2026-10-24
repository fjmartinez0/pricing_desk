#!/bin/bash
# Run Claude Code headless for one task. The agent can read the repo and the web,
# and can only write files under ./proposals/ (its proposal). Code decides the rest.
#
# Usage: scripts/run_agent.sh <prompt-file> <input-file> <output-file> [WEEK] [WEEK_LABEL] [STATS_FILE]
#
# Model per task (config.env can override each): classification tasks use Sonnet, the weekly edition Opus.
#   CLAUDE_MODEL_CHANGES, CLAUDE_MODEL_REPORTS, CLAUDE_MODEL_REGISTRY (default sonnet), CLAUDE_MODEL_EDITION (default opus)
# If Claude answers with a usage or rate limit, .run/agent_limited_<run> is created and run_daily.sh skips
# the remaining agent tasks of this run; nothing is lost, everything waits for the next run.
set -uo pipefail
PROMPT_FILE="$1"; INPUT_FILE="$2"; OUTPUT_FILE="$3"
WEEK="${4:-}"; WEEK_LABEL="${5:-}"; STATS_FILE="${6:-}"
TODAY="$(date +%Y-%m-%d)"; WEEKDAY="$(date +%A)"

PROMPT="$(sed -e "s|{{TODAY}}|$TODAY|g" -e "s|{{WEEKDAY}}|$WEEKDAY|g" -e "s|{{RUN}}|$PD_RUN_ID|g" \
  -e "s|{{INPUT_FILE}}|$INPUT_FILE|g" -e "s|{{OUTPUT_FILE}}|$OUTPUT_FILE|g" \
  -e "s|{{WEEK}}|$WEEK|g" -e "s|{{WEEK_LABEL}}|$WEEK_LABEL|g" -e "s|{{STATS_FILE}}|$STATS_FILE|g" "$PROMPT_FILE")"

name="$(basename "$PROMPT_FILE" .md)"
task="$(echo "${name%_prompt}" | tr '[:lower:]' '[:upper:]')"
var="CLAUDE_MODEL_$task"
default_model="sonnet"; [ "$task" = "EDITION" ] && default_model="opus"
eval "MODEL=\${$var:-}"            # bash 3.2 on macOS, set -u safe
[ -n "$MODEL" ] || MODEL="$default_model"
OUT_JSON=".run/claude_${PD_RUN_ID}_${name}.json"
echo "agent: $name ($MODEL) → $OUTPUT_FILE"
claude -p "$PROMPT" \
  --model "$MODEL" \
  --tools "WebSearch,WebFetch,Read,Write,Edit,Glob,Grep" \
  --allowedTools "WebSearch,WebFetch,Read,Glob,Grep,Edit(./proposals/**)" \
  --permission-mode dontAsk --permission-prompts none \
  --max-turns "${CLAUDE_MAX_TURNS:-250}" --no-session-persistence \
  --output-format json > "$OUT_JSON" || echo "agent exited $? (tolerated; the merge step checks the proposal)"

if python3 - "$OUT_JSON" <<'PY'
import json, re, sys
try:
    d = json.load(open(sys.argv[1]))
except Exception:
    sys.exit(1)
text = str(d.get("result", "")) + " " + str(d.get("subtype", ""))
limited = d.get("is_error") and re.search(r"usage limit|rate limit|limit reached|hit your limit|out of (extra )?usage", text, re.I)
sys.exit(0 if limited else 1)
PY
then
  echo "agent: usage limit reached; remaining agent tasks are skipped this run"
  touch ".run/agent_limited_${PD_RUN_ID}"
fi
