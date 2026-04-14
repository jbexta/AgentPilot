---
name: run-dev-app
description: Run AgentPilot in dev mode and read its console output via run_dev.sh.
---

Use `./run_dev.sh` from the repo root to launch AgentPilot in dev mode with live console output.

## Commands

- `./run_dev.sh`         — launch the app, tee stdout/stderr to `run_dev.log`.
- `./run_dev.sh --tail`  — follow the existing log without relaunching.
- `./run_dev.sh --kill`  — kill the instance whose PID is in `run_dev.pid`.

## How to use from Claude Code

1. Launch the app with `Bash(run_in_background=true)` invoking `./run_dev.sh`.
2. Read `run_dev.log` (or the background task's output file) to see startup logs.
3. When done, run `./run_dev.sh --kill` — never kill the tee process by hand.

The script sets `PYTHONUNBUFFERED=1` and runs through `poetry run` so the correct virtualenv is used.
