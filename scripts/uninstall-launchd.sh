#!/bin/sh
# Stop and remove the yojobs launchd agent (the log and job database are kept).
set -eu
LABEL="local.yojobs"
launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
rm -f "$HOME/Library/LaunchAgents/$LABEL.plist"
echo "Removed $LABEL"
