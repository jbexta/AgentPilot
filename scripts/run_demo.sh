#!/usr/bin/env bash
# Launches AgentPilot in demo mode: boots normally, auto-triggers
# Main.run_demo() after the event loop is up.
#
# Usage:
#   ./run_demo.sh         # run the demo, tee output to run_demo.log
#   ./run_demo.sh --tail  # tail the existing logfile
#   ./run_demo.sh --kill  # kill any running instance started by this script

set -u
set -o pipefail

cd "$(dirname "$0")/.."

LOG_FILE="run_demo.log"
PID_FILE="run_demo.pid"

case "${1:-}" in
    --tail)
        exec tail -n 200 -f "$LOG_FILE"
        ;;
    --kill)
        if [[ -f "$PID_FILE" ]]; then
            pid="$(cat "$PID_FILE")"
            if kill -0 "$pid" 2>/dev/null; then
                kill "$pid" && echo "killed $pid"
            else
                echo "no live process for pid $pid"
            fi
            rm -f "$PID_FILE"
        else
            echo "no $PID_FILE"
        fi
        exit 0
        ;;
esac

if [[ -f .env ]]; then
    set -a
    # shellcheck disable=SC1091
    source .env
    set +a
fi

export PYTHONUNBUFFERED=1
export PYTHONPATH="$PWD/src${PYTHONPATH:+:$PYTHONPATH}"
export AP_RUN_DEMO=1

: > "$LOG_FILE"

# A backgrounded app does not receive the terminal's Ctrl+C/Ctrl+Z, and Qt
# ignores SIGINT. Trapping these signals lets us tear the app down instead of
# leaving it orphaned (Ctrl+C) or suspended-but-visible (Ctrl+Z).
cleanup() {
    trap - INT TERM TSTP HUP EXIT
    if [[ -n "${APP_PID:-}" ]] && kill -0 "$APP_PID" 2>/dev/null; then
        # SIGCONT first: a Ctrl+Z-suspended process ignores SIGTERM until resumed.
        kill -CONT "$APP_PID" 2>/dev/null
        kill -TERM "$APP_PID" 2>/dev/null
        for _ in $(seq 1 15); do
            kill -0 "$APP_PID" 2>/dev/null || break
            sleep 0.2
        done
        kill -0 "$APP_PID" 2>/dev/null && kill -KILL "$APP_PID" 2>/dev/null
    fi
    rm -f "$PID_FILE"
}
trap cleanup INT TERM TSTP HUP EXIT

# Process substitution (not a pipe) so $! is the python PID, not tee's.
poetry run python src/__main__.py > >(tee "$LOG_FILE") 2>&1 &
APP_PID=$!
echo $APP_PID > "$PID_FILE"
wait "$APP_PID"
EXIT_CODE=$?
exit $EXIT_CODE
