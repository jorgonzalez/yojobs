#!/bin/sh
# Start, stop or check the local Ollama server used by the optional CV match.
#   scripts/ollama-ctl.sh status   -> prints "running" or "stopped"
#   scripts/ollama-ctl.sh start    -> starts `ollama serve` in the background (no-op if running)
#   scripts/ollama-ctl.sh stop     -> stops it
# Used by the Desktop app (make-ollama-app.sh) and the login question (ollama-prompt.sh),
# which run with a minimal PATH, so the ollama binary is looked up explicitly.
set -u
URL="${OLLAMA_URL:-http://localhost:11434}"
LOG="$HOME/Library/Logs/ollama.log"

find_ollama() {
  for p in "$(command -v ollama 2>/dev/null)" /opt/homebrew/bin/ollama /usr/local/bin/ollama \
           /Applications/Ollama.app/Contents/Resources/ollama; do
    [ -n "$p" ] && [ -x "$p" ] && { echo "$p"; return 0; }
  done
  return 1
}

is_running() {
  /usr/bin/curl -s -m 3 -o /dev/null "$URL/api/version"
}

case "${1:-status}" in
  status)
    if is_running; then echo running; else echo stopped; fi
    ;;
  start)
    if is_running; then echo running; exit 0; fi
    OLLAMA="$(find_ollama)" || { echo "ollama not found (brew install ollama)" >&2; exit 1; }
    mkdir -p "$(dirname "$LOG")"
    # detached: survives the caller (Desktop app, login question) and closes its output
    nohup "$OLLAMA" serve >>"$LOG" 2>&1 </dev/null &
    for _ in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 18 19 20; do
      sleep 0.5
      if is_running; then echo running; exit 0; fi
    done
    echo "Ollama didn't start; see $LOG" >&2
    exit 1
    ;;
  stop)
    if ! is_running; then echo stopped; exit 0; fi
    /usr/bin/pkill -f "ollama serve"
    for _ in 1 2 3 4 5 6 7 8 9 10; do
      sleep 0.5
      if ! is_running; then echo stopped; exit 0; fi
    done
    echo "Ollama didn't stop" >&2
    exit 1
    ;;
  *)
    echo "usage: $0 status|start|stop" >&2
    exit 2
    ;;
esac
