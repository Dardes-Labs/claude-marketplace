# medication-reminder

Priority-aware medication reminder for Claude Code. Runs as a SessionStart hook, checks an iCloud-synced flag for today's logged dose, and sends a macOS notification if anything is overdue — respecting per-medication priority and time windows so it doesn't cry wolf.

Built because ADHD + "just remember to take it" don't mix.

---

## How it works

```
SessionStart hook (session-start.sh)
    └── nohup medication-check.sh &  (detached, Claude Code keeps going)
            ├── local fast-path:    ~/.medication/taken_YYYY-MM-DD          → exit silently
            ├── iCloud-synced flag: iCloud/MedicationCheck/taken_YYYY-MM-DD → copy to local, exit silently
            └── evaluate-priority.py <medications.toml>     → emits actions
                    └── osascript display notification ...
```

Non-blocking by design: the hook detaches the worker and returns exit 0 instantly. If iCloud isn't reachable or the flag doesn't exist, the worker falls through to the priority evaluator — your session is never delayed or disrupted.

The "did I take it" signal is a zero-byte file named `taken_YYYY-MM-DD` written into iCloud Drive by an iOS Shortcut on your phone. When you tap the Shortcut after taking your meds, the file syncs to the Mac within seconds and the worker treats today as done.

---

## Install

```bash
cd plugins/medication-reminder
./install.sh
```

`install.sh` seeds `~/.medication/medications.toml` from the example (if missing), creates the `iCloud Drive/MedicationCheck/` folder, and prints Shortcut setup instructions. No code signing, no Apple Developer Program required.

Then in Claude Code:

```
/plugin marketplace add <repo>
/plugin install medication-reminder@dardes
```

### Set up the iOS Shortcut

**Quick install (recommended):** on your iPhone, tap this iCloud link to add the pre-built Shortcut: `<paste-your-icloud-shortcut-link-here>`. Shortcuts will open with a preview, tap **Add Shortcut**, and you're done. The Shortcut also propagates automatically to your iPad and Apple Watch via iCloud sync.

On first run, iOS will ask permission to write to iCloud Drive — allow it once and the Shortcut runs silently from then on. Add the Shortcut to your Home Screen, lock-screen widget stack, or wire it into a Health automation that fires when you log a medication.

**Build it yourself (alternative — useful if you want to read what it does, or customize the iCloud Drive folder name):** open Shortcuts.app on iPhone and create a new shortcut with three actions:

1. **Get Current Date** → **Format Date** (format: `yyyy-MM-dd`).
2. **Text** with an empty value (we just want a zero-byte flag file).
3. **Save File**:
   - Service: **iCloud Drive**
   - Destination: **Shortcuts → MedicationCheck** (create the folder if missing — must match `MEDICATION_ICLOUD_DIR` if you've overridden it)
   - File name: `taken_<formatted-date from step 1>`
   - Overwrite existing file: **on**
   - Don't ask where to save: **on**

Name it **"Mark meds taken"**.

**Verify end-to-end** before the next Claude Code session: tap the Shortcut on iPhone, wait ~10s for iCloud sync, then on Mac:

```bash
ls -la "$HOME/Library/Mobile Documents/com~apple~CloudDocs/MedicationCheck"
```

You should see `taken_YYYY-MM-DD` for today's date.

---

## Configuration

Copy the example and edit:

```bash
cp config/medications.example.toml ~/.medication/medications.toml
```

Each `[[medication]]` entry has four fields — only `name` and `priority` are required:

```toml
[[medication]]
name = "Adderall XR"
priority = "crucial"      # "crucial" | "important" | "optional"
take = "morning"          # keyword or "HH:MM" — default "anytime"
deadline = "15:00"        # optional hard cut-off; past this = skip today
note = "Take ASAP after waking."
```

`take` accepts keywords (`morning`, `noon`, `afternoon`, `evening`, `night`, `anytime`) that expand to sensible windows, or an `HH:MM` target (window extends 2 hours past the target). Past the soft window with **no deadline set**, behavior is driven by priority — `crucial` keeps nagging, `important` and `optional` go quiet.

### Priority semantics

The actual mapping from (priority, window, now) → (action, message) lives in `scripts/evaluate-priority.py`. See the TODO block there — it's intentionally left for the owner to tune, because what counts as "nag me" is personal.

Output actions the worker understands:

| Action | Behavior |
| --- | --- |
| `urgent` | macOS notification with "urgent" title |
| `remind` | macOS notification with "reminder" title |
| `skip` | no notification (explicitly skipped for today) |
| `silent` | no notification (too early / not yet relevant) |

---

## Environment variables

| Var | Default | Purpose |
| --- | --- | --- |
| `MEDICATION_STATE_DIR` | `~/.medication` | Where local flag + config live |
| `MEDICATION_CONFIG` | `$MEDICATION_STATE_DIR/medications.toml` | Config path |
| `MEDICATION_ICLOUD_DIR` | `~/Library/Mobile Documents/com~apple~CloudDocs/MedicationCheck` | iCloud Drive folder watched for the daily flag |
| `MEDICATION_LOG_FILE` | `$MEDICATION_STATE_DIR/check.log` | Worker log (nohup) |

---

## How "taken" state is tracked

Two flag files, both date-keyed by today's local calendar day:

1. **Local fast-path** — `~/.medication/taken_YYYY-MM-DD`. Single-day "everything is done, shut up" override. Worker exits silently as soon as it sees this file. Touch it manually to suppress reminders for the rest of the day.
2. **iCloud-synced flag** — `iCloud Drive/MedicationCheck/taken_YYYY-MM-DD`. Written by the iOS Shortcut on your phone. First time the worker sees it, it copies it to the local fast-path so subsequent checks don't hit iCloud's filesystem at all.

If control reaches `evaluate-priority.py`, neither flag exists. The evaluator treats every configured medication as unfulfilled and decides per-med action purely from `priority + take-window + now`.

### Known gap — per-medication state

Both flags are **binary for the whole day, not per-medication**. If you tap the Shortcut after taking one of three configured meds, the flag is set and the worker stops reminding you about the other two. Options to close this:

- **Per-med Shortcuts** — one Shortcut per medication, each writes `taken_YYYY-MM-DD_<slug>`. Simple but you tap once per med.
- **Single Shortcut with med-name input** — Shortcut prompts for which med, writes the slug-suffixed flag. Slight friction but one icon.
- **Ignore Shortcut taps for some priorities** — keep coarse-grain for `optional`, switch to per-med for `crucial`.

Ships with the coarse-grained model. File an issue on yourself when you decide which variant fits your routine.

---

## Manually marking today done

Without using the Shortcut (e.g. you took the meds on the road, no phone handy):

```bash
# Suppress on this Mac only:
touch ~/.medication/taken_$(date +%Y-%m-%d)

# Or let it propagate to other Macs via iCloud:
touch "$HOME/Library/Mobile Documents/com~apple~CloudDocs/MedicationCheck/taken_$(date +%Y-%m-%d)"
```

---

## HealthKit on macOS — why it's not the data source (yet)

The original design read medication-log samples directly from HealthKit on the Mac. That hit two walls:

1. **Capability gating.** HealthKit isn't in [Apple's macOS supported-capabilities list](https://developer.apple.com/help/account/reference/supported-capabilities-macos/) — for a macOS App ID, the standard capability checkbox is disabled. The only path is a **Capability Request** submitted via the App ID's Capability Requests tab, where Apple reviews a justification form per app. Approval is per-app and not guaranteed.
2. **iOS-vs-macOS SDK divergence.** `HKCategoryTypeIdentifierMedicationLog` (the iOS 16+ identifier most medication-tracking code uses) doesn't exist in the macOS SDK at all. macOS 26 introduces a different API surface — `HKMedicationDoseEvent`, `HKMedicationConcept`, `HKUserAnnotatedMedication` — that does exist on macOS but requires the granted entitlement.

**Net:** HealthKit-on-macOS for this plugin is a combination of (a) waiting for Apple's capability grant and (b) rewriting the Swift CLI to use the macOS-26 medication API. The iCloud Drive flag is the working architecture in the meantime, and it's good enough that the HealthKit path is genuinely *optional* if the request lands.

The dormant Swift CLI source is preserved at `swift/Sources/MedicationCheck/main.swift` — see the header comment for context on what would need to change to re-light it.
