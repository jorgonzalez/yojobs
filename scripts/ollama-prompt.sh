#!/bin/sh
# Asks once after login whether to start Ollama for the yojobs CV match.
# Installed by install-ollama-prompt.sh as a launchd agent that runs at login.
# Does nothing if Ollama is already running. Closes by itself after 2 minutes
# without an answer (counts as "Not now").
set -u
DIR="$(cd "$(dirname "$0")" && pwd)"
CTL="$DIR/ollama-ctl.sh"

[ "$(/bin/sh "$CTL" status)" = "running" ] && exit 0

ANSWER="$(/usr/bin/osascript <<'OSA' 2>/dev/null
try
  set r to display dialog "Start Ollama for the yojobs CV match?" & return & return & ¬
    "Without it, yojobs still emails new jobs, just without CV scores." ¬
    with title "yojobs" buttons {"Not now", "Start"} default button "Start" cancel button "Not now" ¬
    giving up after 120
  if gave up of r then return "later"
  return button returned of r
on error
  return "later"
end try
OSA
)"

if [ "$ANSWER" = "Start" ]; then
  if /bin/sh "$CTL" start >/dev/null; then
    /usr/bin/osascript -e 'display notification "Ollama is running; CV scores are on." with title "yojobs"'
  else
    /usr/bin/osascript -e 'display notification "Ollama could not start; see ~/Library/Logs/ollama.log" with title "yojobs"'
  fi
fi
