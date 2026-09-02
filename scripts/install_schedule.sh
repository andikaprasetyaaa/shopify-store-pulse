#!/bin/bash
#
# Install (or reinstall) the hourly launchd schedule.
#
#   bash scripts/install_schedule.sh          # install + start
#   bash scripts/install_schedule.sh remove   # uninstall

set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LABEL="com.storepulse.sync"
SOURCE_PLIST="$PROJECT_DIR/scripts/$LABEL.plist"
TARGET_PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
DOMAIN="gui/$(id -u)"

if [ "${1:-install}" = "remove" ]; then
    launchctl bootout "$DOMAIN/$LABEL" 2>/dev/null || true
    rm -f "$TARGET_PLIST"
    echo "Removed hourly schedule: $LABEL"
    exit 0
fi

mkdir -p "$HOME/Library/LaunchAgents"
cp "$SOURCE_PLIST" "$TARGET_PLIST"

launchctl bootout "$DOMAIN/$LABEL" 2>/dev/null || true
launchctl bootstrap "$DOMAIN" "$TARGET_PLIST"
launchctl enable "$DOMAIN/$LABEL"

echo "Installed hourly schedule: $LABEL"
echo "  plist : $TARGET_PLIST"
echo "  logs  : $PROJECT_DIR/logs/sync.log"
echo
echo "Status:"
launchctl print "$DOMAIN/$LABEL" | sed -n '1,12p'
