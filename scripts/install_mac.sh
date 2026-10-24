#!/bin/bash
# Install (or reinstall) the launchd job that runs Pricing Desk at 07:00 and 19:00.
# Usage: bash scripts/install_mac.sh [--run-now]
set -euo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
LABEL="com.fmz.pricing_desk"
DEST="$HOME/Library/LaunchAgents/$LABEL.plist"
mkdir -p "$HOME/Library/LaunchAgents" "$REPO/logs"
sed "s|__REPO__|$REPO|g" "$REPO/launchd/$LABEL.plist" > "$DEST"
launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$DEST"
echo "Installed $DEST (runs at 07:00 and 19:00)."
if [ "${1:-}" = "--run-now" ]; then
  launchctl kickstart -k "gui/$(id -u)/$LABEL"
  echo "Started a run now. Follow it with: tail -f \"$REPO/logs/$(date +%Y-%m-%d).log\""
fi
