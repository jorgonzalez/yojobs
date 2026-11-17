#!/bin/sh
# Create a small "Ollama" app (default: on the Desktop) to start or stop the local
# Ollama server with a double-click. It shows whether Ollama is running and offers
# Start or Stop. You can also drag it to the Dock.
#   scripts/make-ollama-app.sh                     -> ~/Desktop/Ollama.app
#   scripts/make-ollama-app.sh ~/Applications      -> another folder
set -eu
REPO="$(cd "$(dirname "$0")/.." && pwd)"
DEST="${1:-$HOME/Desktop}"
APP="$DEST/Ollama.app"
CTL="$REPO/scripts/ollama-ctl.sh"

SRC="$(mktemp -t ollama-app).applescript"
cat > "$SRC" <<OSA
set ctl to "/bin/sh " & quoted form of "$CTL"
set state to do shell script ctl & " status"
if state is "running" then
  set r to display dialog "Ollama is running." & return & "(used by the yojobs CV match)" ¬
    with title "Ollama" buttons {"Close", "Stop"} default button "Close" cancel button "Close"
  if button returned of r is "Stop" then
    do shell script ctl & " stop"
    display notification "Ollama stopped." with title "Ollama"
  end if
else
  set r to display dialog "Ollama is stopped." & return & "(used by the yojobs CV match)" ¬
    with title "Ollama" buttons {"Close", "Start"} default button "Start" cancel button "Close"
  if button returned of r is "Start" then
    try
      do shell script ctl & " start"
      display notification "Ollama is running." with title "Ollama"
    on error msg
      display dialog "Ollama could not start:" & return & msg with title "Ollama" buttons {"OK"} default button "OK"
    end try
  end if
end if
OSA

mkdir -p "$DEST"
rm -rf "$APP"
/usr/bin/osacompile -o "$APP" "$SRC"
rm -f "$SRC"
echo "Created $APP (double-click to start/stop Ollama; drag it to the Dock if you like)"
