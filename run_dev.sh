#!/usr/bin/env bash
# Launches AgentPilot for development with unbuffered output tee'd to a logfile.
# Usage:
#   ./run_dev.sh           # run in foreground, also writes run_dev.log
#   ./run_dev.sh --tail    # tail the existing logfile (does not launch)
#   ./run_dev.sh --kill    # kill any running instance started by this script

set -u

cd "$(dirname "$0")"

LOG_FILE="run_dev.log"
PID_FILE="run_dev.pid"

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

export PYTHONUNBUFFERED=1
export PYTHONPATH="$PWD/src${PYTHONPATH:+:$PYTHONPATH}"

: > "$LOG_FILE"
poetry run python src/__main__.py 2>&1 | tee "$LOG_FILE" &
echo $! > "$PID_FILE"
wait
