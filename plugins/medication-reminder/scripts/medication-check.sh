#!/usr/bin/env bash
# Background worker:
#   1. Fast-path: honor a local "taken today" flag file.
#   2. Honor an iCloud-synced flag written by an iOS Shortcut.
#   3. If still not taken, run the priority evaluator and notify per decision.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

STATE_DIR="${MEDICATION_STATE_DIR:-${HOME}/.medication}"
TODAY="$(date +%Y-%m-%d)"
FLAG_FILE="${STATE_DIR}/taken_${TODAY}"
CONFIG_FILE="${MEDICATION_CONFIG:-${STATE_DIR}/medications.toml}"
ICLOUD_FLAG_DIR="${MEDICATION_ICLOUD_DIR:-${HOME}/Library/Mobile Documents/com~apple~CloudDocs/MedicationCheck}"
ICLOUD_FLAG_FILE="${ICLOUD_FLAG_DIR}/taken_${TODAY}"

mkdir -p "$STATE_DIR"

# 1. Local fast-path — the user (or a Shortcut) already marked today done.
if [[ -f "$FLAG_FILE" ]]; then
  exit 0
fi

# 2. iCloud-synced flag — iOS Shortcut writes this when meds are logged on iPhone.
#    First sighting promotes it to the local fast-path so subsequent checks skip
#    the iCloud filesystem entirely.
if [[ -f "$ICLOUD_FLAG_FILE" ]]; then
  touch "$FLAG_FILE"
  exit 0
fi

# 3. Not taken — consult the priority evaluator.
if [[ ! -f "$CONFIG_FILE" ]]; then
  # No config, nothing to do. Exit silently to stay non-intrusive.
  exit 0
fi

# Evaluator prints one line per medication decision:
#   ACTION|MESSAGE
# where ACTION ∈ {urgent, remind, skip, silent}
DECISIONS="$(python3 "${SCRIPT_DIR}/evaluate-priority.py" --config "$CONFIG_FILE" 2>/dev/null || true)"

[[ -z "$DECISIONS" ]] && exit 0

notify() {
  local title="$1"; local body="$2"
  # Escape double quotes for AppleScript.
  local safe_body="${body//\"/\\\"}"
  local safe_title="${title//\"/\\\"}"
  osascript -e "display notification \"${safe_body}\" with title \"${safe_title}\"" >/dev/null 2>&1 || true
}

while IFS='|' read -r action message; do
  [[ -z "$action" ]] && continue
  case "$action" in
    urgent) notify "Medication (urgent)" "$message" ;;
    remind) notify "Medication reminder" "$message" ;;
    skip|silent) : ;;
    *) : ;;
  esac
done <<<"$DECISIONS"

exit 0
