#!/bin/sh
# Remove the login question installed by install-ollama-prompt.sh.
set -eu
LABEL="local.yojobs.ollama-prompt"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
rm -f "$PLIST"
echo "Removed $LABEL; you won't be asked at login any more."
