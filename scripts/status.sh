#!/bin/sh
# Is yojobs running right now? Shows the current run (if any), today's runs, when the
# next automatic run is due, and the state of the launchd agent.
#   ./scripts/status.sh
REPO="$(cd "$(dirname "$0")/.." && pwd)"
LOG="$HOME/Library/Logs/yojobs.log"
PY="$REPO/.venv/bin/python"

echo "== Current run"
PIDS="$(/usr/bin/pgrep -f 'python.* -m yojobs' || true)"
if [ -z "$PIDS" ]; then
  echo "No yojobs run in progress."
else
  for pid in $PIDS; do
    ARGS="$(/bin/ps -o args= -p "$pid" 2>/dev/null | sed 's/.*-m yojobs//')"
    ELAPSED="$(/bin/ps -o etime= -p "$pid" 2>/dev/null | tr -d ' ')"
    case "$ARGS" in
      *--scheduled*) KIND="automatic run" ;;
      *) KIND="manual run (its output is in the terminal that started it)" ;;
    esac
    echo "Running: $KIND, pid $pid, for $ELAPSED${ARGS:+, options:$ARGS}"
  done
  case "$(/bin/ps -o args= -p $PIDS 2>/dev/null)" in
    *--scheduled*) echo "Latest log lines:"; tail -n 3 "$LOG" | sed 's/^/  /' ;;
  esac
fi

echo
echo "== Today"
"$PY" - "$REPO/schedule_state.json" <<'PYEOF'
import json, sys
from datetime import datetime
try:
    runs = json.load(open(sys.argv[1])).get("runs", [])
except (OSError, ValueError):
    runs = []
today = [r[11:16] for r in runs if r[:10] == datetime.now().strftime("%Y-%m-%d")]
print("Automatic runs today: " + (", ".join(today) if today else "none yet"))
PYEOF
(cd "$REPO" && "$PY" -m yojobs --check-schedule 2>&1 | sed 's/^[0-9:]*  //')

echo
echo "== Background job (launchd)"
INFO="$(launchctl print "gui/$(id -u)/local.yojobs" 2>/dev/null)"
if [ -z "$INFO" ]; then
  echo "Not installed: run ./scripts/install-launchd.sh"
else
  INTERVAL="$(echo "$INFO" | sed -n 's/.*run interval = \([0-9]*\) seconds.*/\1/p' | head -1)"
  LAST="$(echo "$INFO" | sed -n 's/.*last exit code = \(.*\)/\1/p' | head -1)"
  echo "Installed; checks every $((INTERVAL / 60)) minutes; last check exited with code ${LAST:-?}."
  [ "$INTERVAL" -gt 600 ] 2>/dev/null && echo "(Run ./scripts/install-launchd.sh to switch to 10-minute checks.)"
fi
echo "Log: $LOG"
