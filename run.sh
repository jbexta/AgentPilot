#!/usr/bin/env bash
# Run AgentPilot from source.
# Finds the Poetry virtualenv; if there isn't one, locks deps and creates it.
# Then activates the venv and launches the app.

set -euo pipefail

cd "$(dirname "$0")"

# Load environment variables from .env if present.
if [[ -f .env ]]; then
    set -a
    # shellcheck disable=SC1091
    source .env
    set +a
fi

# Look for an existing Poetry virtualenv.
VENV_PATH="$(poetry env info --path 2>/dev/null || true)"

if [[ -z "$VENV_PATH" || ! -d "$VENV_PATH" ]]; then
    echo "No virtualenv found — locking dependencies and creating one..."
    poetry lock
    poetry install
    VENV_PATH="$(poetry env info --path)"
fi

echo "Using virtualenv: $VENV_PATH"

# Activate the venv and run the app's __main__.
# shellcheck disable=SC1091
source "$VENV_PATH/bin/activate"

export PYTHONUNBUFFERED=1
export PYTHONPATH="$PWD/src${PYTHONPATH:+:$PYTHONPATH}"

exec python src/__main__.py "$@"
