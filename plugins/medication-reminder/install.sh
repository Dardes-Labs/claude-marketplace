#!/usr/bin/env bash
# One-shot installer for medication-reminder (Plan B: iCloud-flag architecture).
#
#   1. Seeds ~/.medication/medications.toml from the example if missing.
#   2. Creates the iCloud Drive folder the iOS Shortcut writes flags into.
#   3. Prints next-step instructions for setting up the Shortcut.
#
# This installer intentionally does NOT build the Swift HealthKit CLI. HealthKit
# on macOS is a managed capability that requires an Apple Capability Request
# approval (see swift/Sources/MedicationCheck/main.swift for the dormant code).
# Until/unless that's granted, the runtime path uses an iCloud-synced flag file
# instead — written by an iOS Shortcut on the phone, read by the Mac worker.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

STATE_DIR="${MEDICATION_STATE_DIR:-${HOME}/.medication}"
CONFIG="${STATE_DIR}/medications.toml"
EXAMPLE="${SCRIPT_DIR}/config/medications.example.toml"

ICLOUD_FLAG_DIR="${MEDICATION_ICLOUD_DIR:-${HOME}/Library/Mobile Documents/com~apple~CloudDocs/MedicationCheck}"

echo "==> Ensuring config directory: $STATE_DIR"
mkdir -p "$STATE_DIR"
if [[ ! -f "$CONFIG" ]]; then
    cp "$EXAMPLE" "$CONFIG"
    echo "    Seeded $CONFIG (edit to match your regimen)."
else
    echo "    $CONFIG already exists — leaving it alone."
fi

echo "==> Ensuring iCloud Drive flag folder: $ICLOUD_FLAG_DIR"
if mkdir -p "$ICLOUD_FLAG_DIR" 2>/dev/null; then
    echo "    Folder ready. iOS Shortcut should write into iCloud Drive → MedicationCheck/."
else
    cat <<MSG
    WARNING: could not create $ICLOUD_FLAG_DIR.
    iCloud Drive may be disabled. Either enable it (System Settings → Apple ID
    → iCloud → iCloud Drive), or set MEDICATION_ICLOUD_DIR to a different
    directory the iOS Shortcut can also reach.
MSG
fi

cat <<DONE

Done. Next step — set up the iOS Shortcut on your iPhone:

  1. Open Shortcuts.app on iPhone → + (new shortcut).
  2. Add action: "Get Current Date" → "Format Date" (Date format: yyyy-MM-dd).
  3. Add action: "Text" with the literal value "" (empty body — we just want
     a zero-byte flag file).
  4. Add action: "Save File":
       Service:        iCloud Drive
       Destination:    Shortcuts → MedicationCheck (create if missing)
       File name:      taken_<formatted-date>
       Overwrite:      on
       Don't Ask:      on
  5. Name it "Mark meds taken" and add to your morning routine, Home screen,
     or trigger from a Health automation.

When you tap the Shortcut, it writes a zero-byte file
\`taken_YYYY-MM-DD\` into iCloud Drive → MedicationCheck. Your Mac worker
sees that file, treats today as done, and stops nagging.

Manual alternative (no Shortcut):
    touch "$ICLOUD_FLAG_DIR/taken_\$(date +%Y-%m-%d)"
or, for local-only suppression:
    touch "$STATE_DIR/taken_\$(date +%Y-%m-%d)"
DONE
