---
name: healthkit-medication-bridge
description: iOS companion app that syncs Apple Health medication data to iCloud Drive so the Mac medication-reminder plugin can do per-medication adherence checks
status: backlog
created: 2026-04-30T21:04:13Z
---

# PRD: healthkit-medication-bridge

## Executive Summary

A small iOS companion app for the `medication-reminder` Claude Code plugin. It subscribes to Apple HealthKit's medication-dose events on iPhone via `HKObserverQuery` + background delivery, and writes a single `state.json` file to a shared iCloud Drive folder describing today's scheduled medications and which ones have been taken or skipped. The Mac plugin reads that file in place of (or alongside) its current zero-byte flag-file fallback, gaining per-medication adherence visibility it cannot get on macOS directly because HealthKit-on-macOS is gated behind an Apple Capability Request that has no clear path to approval.

The bridge is the minimum-viable iOS half of a two-piece architecture: it does not replace the Mac plugin, does not provide its own UI for medication management, and does not duplicate Apple Health's medication-tracking feature. Its only job is to expose the user's existing Apple Health medication state to the Mac side via a shared file.

## Problem Statement

The `medication-reminder` plugin runs on macOS and currently uses a binary "did the user take their meds today?" flag, written either manually or by an iOS Shortcut tap. Two limitations follow:

1. **Coarse-grained state.** A single `taken_YYYY-MM-DD` flag covers all medications. If the user takes one of three configured meds, the flag is set and the plugin stops nagging about the other two.
2. **Manual signal.** The user must remember to tap the iOS Shortcut after taking medication; if they take meds and forget the Shortcut, the Mac plugin doesn't know.

Both limitations stem from a single architectural gap: HealthKit medication data is recorded on iPhone (in Apple Health) but isn't accessible on macOS. Apple's macOS supported-capabilities list does not include HealthKit, so the Mac plugin cannot read `HKMedicationDoseEvent` directly. The 4-year-long developer community ask for a HealthKit Medications API was finally answered at WWDC 2025 — but Apple's announcement explicitly listed iOS, iPadOS, and visionOS only, omitting macOS.

The standard workaround pattern (used by Health Auto Export and similar apps) is a two-piece system: an iOS app reads HealthKit on iPhone and exports state to a Mac-readable surface. This PRD proposes that pattern, scoped narrowly to medication adherence.

## User Stories

### US-1: Plugin user with multiple medications wants per-med Mac reminders

**As** an ADHD developer using the `medication-reminder` plugin with three configured medications,
**I want** the Mac plugin to know which specific medications I've already taken today,
**so that** it stops nagging me about the ones I've taken while still reminding me about the ones I haven't.

**Acceptance criteria:**
- After installing the bridge on iPhone and granting HealthKit access for each configured medication, taking medication A in Apple Health (or a third-party HealthKit-aware app) within 30 seconds causes the Mac plugin's next session-start check to know A is taken and B/C are not.
- If only A is taken, only A is suppressed; B and C continue to fire reminders per their priority/window rules.

### US-2: Plugin user wants Mac to see medication state automatically

**As** a user who already logs medications in Apple Health on iPhone,
**I want** the Mac plugin to pick up that state without me tapping any Shortcut,
**so that** I don't have to remember a second action after taking medication.

**Acceptance criteria:**
- A medication logged in Apple Health on iPhone (via Health.app's "Mark as Taken" notification, the Medications widget, or any HealthKit-writing app) propagates to the Mac plugin within 60 seconds in 95% of cases (the remaining 5% covers iCloud sync delays, iOS background-delivery throttling, or device-offline conditions).
- No manual Shortcut tap is required for the automatic path. The existing manual Shortcut continues to work as a fallback when the bridge is not installed or HealthKit access is not granted.

### US-3: Plugin user without iPhone or HealthKit access still has a working plugin

**As** a user who hasn't installed the iOS bridge (e.g., no iPhone, doesn't want HealthKit access, hasn't gotten around to it),
**I want** the Mac plugin to continue working with the manual-Shortcut / manual-touch-flag fallback,
**so that** the bridge is an optional enhancement rather than a blocker.

**Acceptance criteria:**
- The Mac plugin's behavior with no `state.json` present is identical to its current behavior (date-keyed flag file, falls through to evaluator).
- Installing the bridge changes only the Mac side's read path; the existing flag-file path remains valid forever.

### US-4: User who switches medications wants the bridge to follow Apple Health

**As** a user who adds, removes, or changes medication schedules in Apple Health,
**I want** the bridge to reflect those changes without me re-configuring anything,
**so that** Apple Health remains the single source of truth for my medication regimen.

**Acceptance criteria:**
- Adding a new medication in Apple Health and authorizing the bridge to read it causes that medication to appear in `state.json` on the next dose-event or daily refresh, without any user action in the bridge app.
- Archiving or deleting a medication in Apple Health causes it to disappear from `state.json` on the next refresh.
- The bridge displays per-medication authorization status (which meds the user has granted access to) so the user can verify what the Mac plugin sees.

## Functional Requirements

### FR-1: HealthKit authorization

- The app requests authorization for `HKUserAnnotatedMedicationType` (the macOS-26 / iOS-26 medication entry type) using HealthKit's per-object authorization model. Apple Health prompts the user once per medication; the user controls per-med which medications the bridge can read.
- The app surfaces a list of currently-authorized medications and re-prompts when the user adds new medications in Apple Health.

### FR-2: Daily state-file generation

- On launch and once per calendar day via `BGAppRefreshTask`, the bridge queries `HKUserAnnotatedMedication` for today's active medications and emits a fresh `state.json`.
- If `BGAppRefreshTask` is skipped or delayed by iOS scheduling, the next dose-event observer firing rebuilds `state.json` lazily — daily generation has two redundant triggers.

### FR-3: Event-driven dose updates

- An `HKAnchoredObjectQuery` for `HKMedicationDoseEvent` is registered with `HKHealthStore.enableBackgroundDelivery(for:frequency: .immediate)` so iOS wakes the app whenever a dose event is logged or deleted.
- The handler queries today's dose events, rebuilds the full medications list and adherence status, and writes a new `state.json`.

### FR-4: iCloud Drive write

- `state.json` is written to `~/Library/Mobile Documents/com~apple~CloudDocs/MedicationCheck/state.json` (the same iCloud Drive folder the Mac plugin already watches).
- Writes are atomic (write-temp-then-rename) so the Mac plugin never reads a partially-written file.
- The bridge declares the iCloud Drive ubiquity container in its entitlements; iCloud Documents capability is enabled.

### FR-5: state.json schema

The bridge writes JSON in a **source-agnostic shape** so future producers (e.g. an Android Health Connect bridge, a manual web form) can write the same file format without HealthKit-specific vocabulary. The contract is versioned:

```json
{
  "schema_version": "0.1",
  "date": "2026-04-30",
  "generated_at": "2026-04-30T06:14:22Z",
  "producer": "healthkit-medication-bridge/0.1.0",
  "medications": [
    {
      "name": "Adderall XR",
      "scheduled_today": ["08:00"],
      "events": [
        { "kind": "taken",   "at": "2026-04-30T08:14:00Z", "source": "healthkit" },
        { "kind": "skipped", "at": "2026-04-30T13:00:00Z", "source": "healthkit" }
      ]
    }
  ]
}
```

Field semantics:

- **`schema_version`** (string, semver-style) — `"0.1"` for v1; bumped on any breaking change to field names or shapes. Consumers must reject files with an unknown major version. Pre-1.0 minor bumps are still allowed to break compatibility.
- **`date`** — local calendar day the file describes (the user's timezone, taken from the device generating the file).
- **`generated_at`** — ISO 8601 UTC timestamp of the most recent write. Consumers use this to detect staleness.
- **`producer`** — identifier of the writing tool, in the form `<name>/<version>`. Used for telemetry/debugging and to disambiguate when multiple producers might race on the same file (not v1 scope, but the field reserves the option).
- **`medications[].name`** — display name. Match between schema and consumer's TOML config (`~/.medication/medications.toml`) is by string equality on this field.
- **`medications[].scheduled_today`** — array of `HH:MM` local-time strings for today's scheduled doses. Empty array if the medication has no scheduled time (PRN / as-needed).
- **`medications[].events`** — array of dose events for today. Each has `kind` ∈ `{taken, skipped, snoozed}`, `at` (ISO 8601 UTC), and `source` (free-form string identifying the data origin — `healthkit`, `health-connect`, `manual`, etc.).

The HealthKit producer derives `scheduled_today` from `HKUserAnnotatedMedication.schedule`, derives `events` from today's `HKMedicationDoseEvent.logStatus`, and tags every event with `"source": "healthkit"`. Times are local for schedule entries (matches Health.app schedule semantics) and UTC for event timestamps (unambiguous across timezone changes).

The schema deliberately avoids HealthKit-specific identifiers (no `HKMedicationDoseEvent` UUIDs, no RxNorm codes, no Apple-internal metadata). Future producers writing the same shape from non-Apple sources need no schema work.

### FR-6: Mac-side consumer changes (out of scope for this PRD; in scope for the parent epic)

The Mac plugin's `medication-check.sh` and `evaluate-priority.py` will be extended to read `state.json` when present and degrade to the existing flag-file path when absent. Schema design above is chosen for that consumer; behavior changes on the Mac side are tracked in a separate change set under the same epic.

### FR-7: Status UI

The bridge presents a single SwiftUI screen with:
- Authorization status (granted / denied) for each medication
- Last successful state.json write timestamp
- Last observed dose event timestamp
- A "Refresh now" button that forces a state-file rebuild for diagnostic purposes
- App version and a link to the parent plugin's documentation

No medication-management UI. No history charts. No editing of schedules. The user's existing tools (Apple Health, third-party medication apps) remain the place for those.

## Non-Functional Requirements

### Performance

- Background dose-event handler must complete and write `state.json` within iOS's allotted background runtime (typically <30s) under normal conditions; query result payloads are small (single-digit medications, a handful of dose events per day).
- Cold-start time for the foreground UI is not critical — the app is rarely opened.

### Reliability

- iCloud sync from iPhone-write to Mac-read is best-effort and dependent on Apple's infrastructure; the bridge is not responsible for guaranteeing sync. The Mac plugin's read path tolerates stale `state.json` (looks at `date` and `generated_at` fields) and falls back gracefully.
- iOS may throttle background delivery under low-power or low-battery conditions; the daily `BGAppRefreshTask` provides a backstop.
- The app must not crash on missing or malformed HealthKit responses, missing iCloud entitlement, denied authorization, or revoked permissions.

### Privacy

- The bridge does not transmit data over any network, has no analytics SDK, no telemetry, no third-party SDKs.
- Health data flows: HealthKit on iPhone → bridge (in-memory) → iCloud Drive ubiquity container. No other destinations.
- `NSHealthShareUsageDescription` reads: *"This bridge writes today's medication adherence to iCloud Drive so the Mac medication-reminder plugin can show per-medication reminders."*

### Battery

- Background-delivery frequency is `.immediate` for medication dose events. Medication events are sparse (single-digit per day in typical use), so wake frequency is bounded by user behavior, not by polling.
- `BGAppRefreshTask` is scheduled for "earliest at next midnight" with a target frequency of once per calendar day.

### Compatibility

- Minimum iOS / iPadOS version: 26.0 (the minimum version that includes the `HKMedicationDoseEvent` API).
- Apple Watch is not a target. The bridge runs only on iPhone/iPad.
- Visionos is not a target for v1.

## Success Criteria

The bridge is considered successful when, for the maintainer's own personal use case (3 configured medications, daily logging via Apple Health on iPhone):

1. **Per-medication awareness on Mac (US-1, US-4):** the Mac plugin's evaluator can distinguish "Adderall taken, Methylphenidate not yet" rather than "anything taken today / nothing taken today" — measurable by inspecting the evaluator's per-medication output for any test day where 1 of N medications has been logged.
2. **Automatic propagation latency (US-2):** in 95% of dose-event cases, the time between Apple Health logging and the Mac plugin reading the updated `state.json` is under 60 seconds — measurable by instrumenting the bridge's write timestamp and the Mac plugin's read timestamp on a representative week.
3. **Backwards compatibility (US-3):** uninstalling the bridge or revoking its HealthKit access reverts Mac-side behavior to the pre-bridge flag-file path with no plugin errors — measurable by running the Mac plugin's test-mode script before and after bridge install and confirming no new error paths.
4. **Schema stability:** `state.json` is consumed cleanly by the Mac plugin's `evaluate-priority.py` for at least one week of real-world use without parse errors, schema-drift, or incomplete-state edge cases.
5. **Daily refresh reliability:** over a 30-day observation period, at least 25 days have a `BGAppRefreshTask`-driven `state.json` write before the first dose event of the day (validating that the daily backstop is firing). The remaining ≤5 days are covered by the dose-event lazy path; no day has zero `state.json` writes when at least one dose was logged.

## Constraints & Assumptions

### Constraints

- **iOS 26 minimum** for the medication API — assumed acceptable since the maintainer is on current iOS.
- **Personal Apple Developer Program membership** ($99/yr) is already in place. HealthKit and HealthKit-Background-Delivery entitlements are self-service on iOS — no Apple Capability Request required for the iOS side.
- **iCloud Drive must be enabled** on both iPhone and Mac, signed in to the same Apple ID. If iCloud Drive is disabled, the bridge degrades silently (no writes) and the Mac plugin falls back to its flag-file path.
- **Apple's per-object authorization** means the user authorizes each medication individually in Apple Health. Newly-added medications require re-authorization; the bridge surfaces this in its UI.

### Assumptions

- Apple's `HKMedicationDoseEvent` background-delivery infrastructure is stable enough that `.immediate` frequency reliably delivers within seconds. (To be validated on day one of testing — if Apple throttles aggressively in practice, the daily backstop covers the gap.)
- The Mac plugin is the only consumer of `state.json` for v1 — no other apps read it, no API stability beyond the schema_version field is required.
- The maintainer's own use case (3 meds, ADHD context, daily Mac use) is representative enough to validate the architecture before broader distribution.

## Out of Scope

The following are explicitly **not** part of this PRD:

- **Medication-management UI.** No CRUD on medications, no schedule editing, no history charts. Apple Health remains the source of truth.
- **Push notifications.** The bridge does not send any notifications. The Mac plugin handles all user-facing reminders.
- **CloudKit-based sync.** iCloud Drive ubiquity container is the only cross-device surface for v1. CloudKit could be evaluated later if file-based sync proves unreliable.
- **App Store distribution.** v1 ships as a personal Xcode build (or TestFlight if invitees are added). App Store submission is a follow-up consideration once the architecture is proven.
- **Mac App Store version.** The Mac side stays a Claude Code plugin, not a Mac App Store app.
- **HealthKit medication writes.** The bridge is read-only. Logging a dose to Apple Health from the bridge UI is not a feature; users use Apple Health or other HealthKit-writing apps.
- **Watch app.** No watchOS target. Apple Health on the Watch already handles medication reminders; the bridge does not duplicate that.
- **History / adherence analytics.** The bridge writes only today's state. Historical adherence tracking, charts, and trends are out of scope. The Mac plugin's existing log file (`~/.medication/check.log`) is sufficient for retrospective debugging.
- **Multi-user / family sharing.** Single-user only. The HealthKit medication-data ownership model is per-user; multi-user is a future consideration.
- **Mac-side HealthKit integration.** If Apple ever grants the macOS HealthKit Capability Request and the dormant `medication-check` Swift CLI is re-lit, that work is governed by a separate PRD. The bridge stays valuable even after such a grant because the per-object authorization model is iPhone-anchored.

## Dependencies

### Hard dependencies

- **macOS plugin `medication-reminder`** must continue to exist and to read iCloud Drive state. The bridge is meaningless without it.
- **Apple HealthKit Medications API** (iOS 26+, `HKMedicationDoseEvent`, `HKUserAnnotatedMedication`, `HKUserAnnotatedMedicationQueryDescriptor`).
- **iCloud Drive** enabled on both devices, same Apple ID.
- **Personal Apple Developer Program membership** for the iOS app entitlements (already in place).

### Soft dependencies

- **Apple's iCloud Drive sync latency.** Sync delays of >60s would push us past the success-criteria target for US-2; in that case we'd add CloudKit as a second sync surface. Treated as a watch-and-see risk, not a blocker.
- **iOS background-delivery scheduling.** If `.immediate` frequency proves unreliable in practice, fall back to a combination of dose-event-driven and daily-refresh writes (already the design).

### Coordination

- This PRD does not block the Mac plugin's existing Plan B (manual Shortcut → flag file) work. The Mac plugin should land its current iCloud-flag architecture first; the bridge layers on top.
- The Mac-side change to read `state.json` (extending `medication-check.sh` and `evaluate-priority.py`) is part of the parent epic's task breakdown, tracked alongside the iOS bridge tasks but logically separable. Either side can be developed first and tested with stub data on the other side.
