#!/usr/bin/env bash
# SessionStart hook — non-blocking.
#
# Claude Code waits for this to exit before continuing, so we detach the
# notifier and return immediately. The worker emits a macOS notification for
# any dose still pending past its scheduled time today — and stays silent if
# today's state.json hasn't been published yet, or if nothing is pending.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_FILE="${MEDICATION_LOG_FILE:-${HOME}/.medication/check.log}"
mkdir -p "$(dirname "$LOG_FILE")"

# Fire and forget — detach so this hook returns exit 0 to Claude Code instantly.
nohup python3 "${SCRIPT_DIR}/tada.py" notify >>"$LOG_FILE" 2>&1 &
disown

exit 0
