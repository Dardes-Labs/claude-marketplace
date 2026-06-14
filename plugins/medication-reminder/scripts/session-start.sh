#!/usr/bin/env bash
# SessionStart hook entry point.
#
# Claude Code waits for this script to exit before the session continues, so we
# fire the real work into a detached background process and return immediately.
# The background job will outlive this script and emit a macOS notification if
# medication hasn't been logged for today.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKER="${SCRIPT_DIR}/medication-check.sh"
LOG_FILE="${MEDICATION_LOG_FILE:-${HOME}/.medication/check.log}"

mkdir -p "$(dirname "$LOG_FILE")"

# Fire and forget. `nohup` + `disown` + `&` detaches the worker so this
# hook returns exit 0 to Claude Code instantly.
nohup "$WORKER" >>"$LOG_FILE" 2>&1 &
disown

exit 0
