#!/bin/bash
# Run Claude Code headless for one task. The agent can read the repo and the web,
# and can only write files under ./proposals/ (its proposal). Code decides the rest.
#
# Usage: scripts/run_agent.sh <prompt-file> <input-file> <output-file> [WEEK] [WEEK_LABEL] [STATS_FILE]
set -uo pipefail
PROMPT_FILE="$1"; INPUT_FILE="$2"; OUTPUT_FILE="$3"
WEEK="${4:-}"; WEEK_LABEL="${5:-}"; STATS_FILE="${6:-}"
TODAY="$(date +%Y-%m-%d)"; WEEKDAY="$(date +%A)"

PROMPT="$(sed -e "s|{{TODAY}}|$TODAY|g" -e "s|{{WEEKDAY}}|$WEEKDAY|g" -e "s|{{RUN}}|$PD_RUN_ID|g" \
  -e "s|{{INPUT_FILE}}|$INPUT_FILE|g" -e "s|{{OUTPUT_FILE}}|$OUTPUT_FILE|g" \
  -e "s|{{WEEK}}|$WEEK|g" -e "s|{{WEEK_LABEL}}|$WEEK_LABEL|g" -e "s|{{STATS_FILE}}|$STATS_FILE|g" "$PROMPT_FILE")"

name="$(basename "$PROMPT_FILE" .md)"
echo "agent: $name → $OUTPUT_FILE"
claude -p "$PROMPT" \
  --model "${CLAUDE_MODEL:-opus}" \
  --tools "WebSearch,WebFetch,Read,Write,Edit,Glob,Grep" \
  --allowedTools "WebSearch,WebFetch,Read,Glob,Grep,Edit(./proposals/**)" \
  --permission-mode dontAsk --permission-prompts none \
  --max-turns "${CLAUDE_MAX_TURNS:-250}" --no-session-persistence \
  --output-format json > ".run/claude_${PD_RUN_ID}_${name}.json" || echo "agent exited $? (tolerated; the merge step checks the proposal)"
