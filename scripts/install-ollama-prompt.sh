#!/bin/sh
# Install (or reinstall) the login question "Start Ollama for the yojobs CV match?".
# A launchd agent that runs scripts/ollama-prompt.sh once at every login.
# Remove it with scripts/uninstall-ollama-prompt.sh.
set -eu
REPO="$(cd "$(dirname "$0")/.." && pwd)"
LABEL="local.yojobs.ollama-prompt"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"

mkdir -p "$HOME/Library/LaunchAgents"
cat > "$PLIST" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>$LABEL</string>
  <key>ProgramArguments</key>
  <array>
    <string>/bin/sh</string>
    <string>$REPO/scripts/ollama-prompt.sh</string>
  </array>
  <key>RunAtLoad</key><true/>
  <key>LimitLoadToSessionType</key><string>Aqua</string>
</dict>
</plist>
PLIST

launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$PLIST"
echo "Installed $PLIST"
echo "From the next login you'll be asked whether to start Ollama (now too, if it isn't running)."
